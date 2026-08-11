"""Per-connection transformer: will this passenger transfer survive?

The delay evaluator (`evaluator.ScheduleEvaluator`) answers questions about
a scenario as a whole, and its schedule encoder ends in a masked mean/max
pool over trains. That pooling is symmetric, so pairwise facts — "train A
is booked through this station before train B" — cannot survive it. A
connection *is* such a fact, so no head bolted onto that model can reason
about one; at best it correlates the scenario's connection ratio with
congestion.

This model makes the connection a first-class object instead. Every
planned transfer becomes its own token, alongside a token per train and
per graph node, and self-attention lets a connection token look at the two
trains it joins, the station it happens at, and the other connections
competing for the same track. Each connection token then carries a binary
head: did this transfer survive?

Encoder-only with a per-token head, rather than generating the surviving
subset as a sequence:

- the answer stays aligned — token *i* is connection *i*, so there is no
  risk of losing track of which transfer a prediction refers to;
- every connection contributes gradient every step, instead of the sparser
  and order-dependent signal of autoregressive decoding;
- it yields a calibrated probability per transfer, which is what ranking
  "which connections are at risk" needs, and the scenario ratio is then
  just the masked mean of those probabilities.

The cost is that predictions are marginals: the model represents that two
transfers fail together (attention sees both) but does not emit a joint
distribution over them. That is the right trade for predicting a ratio and
ranking risk.

The infrastructure is read by the same `GraphEncoder` the delay model
uses, so varying networks are handled the way they already are, and the
graph work is not duplicated.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import torch
from torch import nn

from app.policies.goal_based_policies.dataset import (
    CONNECTION_FEATURES,
    STOP_FLAGS,
    TRAIN_SCALARS,
)
from app.policies.goal_based_policies.evaluator import GraphEncoder


class ConnectionTransformer(nn.Module):
    """Judges every planned transfer in a scenario at once.

    Tokens, all projected to the same width and concatenated into one
    sequence the encoder attends over:

    - **graph nodes** — embeddings from `GraphEncoder`, so a connection can
      see where in the network it sits;
    - **trains** — timetable and how the plan sits inside it, plus a
      summary of the schedule the train is booked to run;
    - **connections** — the planned gap and the two planned times, with the
      embeddings of its feeder, its connector and its station added in.
      That addition is what ties the token to *its* trains: the features
      alone would be identical for two different pairs with the same gap.
    """

    def __init__(
        self,
        hidden: int = 96,
        rounds: int = 3,
        layers: int = 4,
        heads: int = 4,
        dropout: float = 0.1,
        train_scalars: int = TRAIN_SCALARS,
        connection_features: int = CONNECTION_FEATURES,
        stop_flags: int = STOP_FLAGS,
    ):
        super().__init__()
        self.hidden = hidden
        self.graph_encoder = GraphEncoder(hidden=hidden, rounds=rounds)

        # A train token summarises its timetable and its booked schedule.
        self.schedule_summary = nn.GRU(
            hidden + 1 + stop_flags, hidden, batch_first=True
        )
        self.train_token = nn.Sequential(
            nn.Linear(hidden + train_scalars, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden),
        )
        self.node_token = nn.Linear(hidden, hidden)
        self.connection_token = nn.Sequential(
            nn.Linear(connection_features, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden),
        )
        # Learned per-kind offsets, so attention can tell a train token from
        # a node token from a connection token.
        self.kind = nn.Parameter(torch.zeros(3, hidden))

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden, nhead=heads, dim_feedforward=hidden * 4,
            dropout=dropout, batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=layers)
        self.head = nn.Sequential(
            nn.Linear(hidden, hidden), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(hidden, 1),
        )
        self._config = {
            "hidden": hidden, "rounds": rounds, "layers": layers,
            "heads": heads, "dropout": dropout,
            "train_scalars": train_scalars,
            "connection_features": connection_features,
            "stop_flags": stop_flags,
        }

    def _train_tokens(
        self, node_embeddings, schedule_nodes, waits, node_mask, stop_flags,
        train_scalars,
    ) -> torch.Tensor:
        batch, trains, steps = schedule_nodes.shape
        hidden = node_embeddings.shape[-1]
        visited = torch.gather(
            node_embeddings.unsqueeze(1).expand(batch, trains, -1, hidden),
            2,
            schedule_nodes.unsqueeze(-1).expand(batch, trains, steps, hidden),
        )
        tokens = torch.cat([visited, waits.unsqueeze(-1), stop_flags], dim=-1)
        tokens = tokens * node_mask.unsqueeze(-1)
        outputs, _ = self.schedule_summary(tokens.reshape(batch * trains, steps, -1))
        lengths = node_mask.reshape(batch * trains, steps).sum(dim=1)
        last = (lengths.long() - 1).clamp(min=0)
        encoded = outputs[torch.arange(outputs.shape[0], device=outputs.device), last]
        encoded = encoded * (lengths > 0).float().unsqueeze(-1)
        return self.train_token(
            torch.cat([encoded, train_scalars.reshape(batch * trains, -1)], dim=-1)
        ).reshape(batch, trains, -1)

    def forward(
        self,
        graph_nodes: torch.Tensor,
        graph_node_mask: torch.Tensor,
        edge_index: torch.Tensor,
        edge_features: torch.Tensor,
        edge_mask: torch.Tensor,
        schedule_nodes: torch.Tensor,
        waits: torch.Tensor,
        node_mask: torch.Tensor,
        stop_flags: torch.Tensor,
        train_scalars: torch.Tensor,
        train_mask: torch.Tensor,
        connection_features: torch.Tensor,
        connection_index: torch.Tensor,
        connection_mask: torch.Tensor,
    ) -> torch.Tensor:
        """-> logit per connection, shape (B, MAX_CONNECTIONS)."""
        node_embeddings = self.graph_encoder(
            graph_nodes, graph_node_mask, edge_index, edge_features, edge_mask
        )
        node_tokens = self.node_token(node_embeddings) + self.kind[0]
        train_tokens = self._train_tokens(
            node_embeddings, schedule_nodes, waits, node_mask, stop_flags,
            train_scalars,
        ) + self.kind[1]

        # Tie each connection to the trains and station it actually joins.
        feeder = connection_index[..., 0]
        connector = connection_index[..., 1]
        station = connection_index[..., 2]
        gather = lambda source, index: torch.gather(  # noqa: E731
            source, 1,
            index.unsqueeze(-1).expand(-1, -1, source.shape[-1]).clamp(min=0),
        )
        connection_tokens = (
            self.connection_token(connection_features)
            + gather(train_tokens, feeder)
            + gather(train_tokens, connector)
            + gather(node_tokens, station)
            + self.kind[2]
        )

        sequence = torch.cat([node_tokens, train_tokens, connection_tokens], dim=1)
        # `True` marks a position attention must ignore, so padding cannot
        # leak into a real token's representation.
        pad = torch.cat([graph_node_mask, train_mask, connection_mask], dim=1) <= 0
        encoded = self.encoder(sequence, src_key_padding_mask=pad)
        connections = encoded[:, -connection_tokens.shape[1]:]
        return self.head(connections).squeeze(-1)

    @torch.no_grad()
    def predict(self, *inputs) -> Dict[str, torch.Tensor]:
        """Per-connection probabilities and the scenario's kept ratio."""
        self.eval()
        logits = self(*inputs)
        connection_mask = inputs[-1]
        probability = torch.sigmoid(logits) * connection_mask
        counted = connection_mask.sum(dim=1)
        return {
            "connection_probability": probability,
            # Scenarios with no connections score 1.0: nothing was broken.
            "kept_ratio": torch.where(
                counted > 0, probability.sum(dim=1) / counted.clamp(min=1.0),
                torch.ones_like(counted),
            ),
        }

    def save(self, path: str | Path) -> str:
        torch.save({"state_dict": self.state_dict(), "config": self._config}, Path(path))
        return str(path)

    @classmethod
    def load(
        cls, path: str | Path, map_location: Optional[str] = "cpu"
    ) -> "ConnectionTransformer":
        payload = torch.load(path, map_location=map_location, weights_only=False)
        model = cls(**payload["config"])
        model.load_state_dict(payload["state_dict"])
        model.eval()
        return model


__all__ = ["ConnectionTransformer"]
