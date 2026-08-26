"""Neural schedule evaluator.

Judges a schedule without running it: given the infrastructure and every
train's schedule on it, predict

1. whether all trains reach their goal (one probability), and
2. which delay bucket the scenario ends up in (0-4, 5-14, 15-29, 30-44,
   45-59, 60+ minutes — six classes).

Three stages, each solving one part of the variable-size problem:

- `GraphEncoder` runs message passing over the decision-point graph, so every
  node gets a vector *computed from where it sits in the network* rather than
  looked up in a global table. Pooling those gives the fixed-length vector
  describing the infrastructure. Because node meaning is computed, the same
  weights apply to a network the model has never seen.
- `ScheduleEncoder` reads each train's walk — the node vectors it visits, in
  order, each with the wait taken there — through a GRU, giving one
  fixed-length vector per train, then pools the trains (masked mean + max) so
  neither their order nor their number matters.
- `ScheduleEvaluator` puts the two heads on top of graph vector + train vector.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import torch
from torch import nn

from app.policies.goal_based_policies.dataset import (
    EDGE_FEATURES,
    NODE_FEATURES,
    STOP_FLAGS,
    TRAIN_SCALARS,
)
from app.policies.goal_based_policies.rollout import (
    DELAY_BUCKET_LABELS,
    NUM_DELAY_BUCKETS,
)


class GraphEncoder(nn.Module):
    """Message passing over the decision-point graph.

    Messages travel both along edges and against them: a node's situation
    depends on what feeds into it as much as on where it leads.
    """

    def __init__(
        self,
        node_features: int = NODE_FEATURES,
        edge_features: int = EDGE_FEATURES,
        hidden: int = 64,
        rounds: int = 3,
    ):
        super().__init__()
        self.rounds = rounds
        self.hidden = hidden
        self.input_projection = nn.Linear(node_features, hidden)
        self.forward_messages = nn.ModuleList(
            nn.Linear(hidden + edge_features, hidden) for _ in range(rounds)
        )
        self.backward_messages = nn.ModuleList(
            nn.Linear(hidden + edge_features, hidden) for _ in range(rounds)
        )
        self.updates = nn.ModuleList(
            nn.Linear(hidden * 3, hidden) for _ in range(rounds)
        )

    def forward(
        self,
        graph_nodes: torch.Tensor,     # (B, N, node_features)
        graph_node_mask: torch.Tensor,  # (B, N)
        edge_index: torch.Tensor,      # (B, E, 2) long
        edge_features: torch.Tensor,   # (B, E, edge_features)
        edge_mask: torch.Tensor,       # (B, E)
    ) -> torch.Tensor:
        """Per-node embeddings, shape (B, N, hidden)."""
        batch, nodes, _ = graph_nodes.shape
        edges = edge_index.shape[1]
        device = graph_nodes.device

        # Flatten the batch so edges can be scattered with one index_add.
        offset = (torch.arange(batch, device=device) * nodes).view(batch, 1)
        source = (edge_index[..., 0] + offset).reshape(-1)
        target = (edge_index[..., 1] + offset).reshape(-1)
        weight = edge_mask.reshape(-1, 1)
        flat_edge_features = edge_features.reshape(batch * edges, -1)

        state = self.input_projection(graph_nodes).reshape(batch * nodes, -1)
        node_weight = graph_node_mask.reshape(-1, 1)

        # Degrees for mean aggregation; clamped so isolated nodes are safe.
        incoming = torch.zeros(batch * nodes, 1, device=device)
        incoming.index_add_(0, target, weight)
        outgoing = torch.zeros(batch * nodes, 1, device=device)
        outgoing.index_add_(0, source, weight)

        for round_index in range(self.rounds):
            along = self.forward_messages[round_index](
                torch.cat([state[source], flat_edge_features], dim=-1)
            ) * weight
            against = self.backward_messages[round_index](
                torch.cat([state[target], flat_edge_features], dim=-1)
            ) * weight

            gathered_in = torch.zeros_like(state)
            gathered_in.index_add_(0, target, along)
            gathered_out = torch.zeros_like(state)
            gathered_out.index_add_(0, source, against)

            state = state + torch.relu(
                self.updates[round_index](
                    torch.cat(
                        [
                            state,
                            gathered_in / incoming.clamp(min=1.0),
                            gathered_out / outgoing.clamp(min=1.0),
                        ],
                        dim=-1,
                    )
                )
            )
            state = state * node_weight

        return state.reshape(batch, nodes, -1)


def _masked_pool(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Masked mean and max over dim 1, concatenated."""
    weights = mask.unsqueeze(-1)
    mean = (values * weights).sum(dim=1) / weights.sum(dim=1).clamp(min=1.0)
    maximum = values.masked_fill(weights == 0, -1e9).max(dim=1).values
    return torch.cat([mean, torch.nan_to_num(maximum, neginf=0.0)], dim=-1)


class ScheduleEncoder(nn.Module):
    """Compresses the schedules into one fixed-length vector."""

    def __init__(
        self,
        node_hidden: int = 64,
        hidden: int = 64,
        train_scalars: int = TRAIN_SCALARS,
        layers: int = 2,
        dropout: float = 0.0,
        stop_flags: int = STOP_FLAGS,
    ):
        super().__init__()
        # Per visited node: its graph embedding, the wait taken there, and
        # the stop flags (is it a booked stop, is it the terminus). Only the
        # terminus ends the run, so the two cannot be one flag.
        self.sequence = nn.GRU(
            node_hidden + 1 + stop_flags, hidden, num_layers=layers,
            batch_first=True, dropout=dropout if layers > 1 else 0.0,
        )
        # Dropout layers only exist when asked for, so a model saved without
        # them (dropout adds no parameters, but shifts Sequential indices)
        # still loads.
        regulariser = [nn.Dropout(dropout)] if dropout > 0 else []
        self.train_projection = nn.Sequential(
            nn.Linear(hidden + train_scalars, hidden),
            nn.ReLU(),
            *regulariser,
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.output_features = hidden * 2

    def forward(
        self,
        node_embeddings: torch.Tensor,  # (B, N, node_hidden)
        schedule_nodes: torch.Tensor,   # (B, T, S) long, local node indices
        waits: torch.Tensor,            # (B, T, S)
        node_mask: torch.Tensor,        # (B, T, S)
        stop_flags: torch.Tensor,       # (B, T, S, STOP_FLAGS)
        train_scalars: torch.Tensor,    # (B, T, TRAIN_SCALARS)
        train_mask: torch.Tensor,       # (B, T)
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

        outputs, _ = self.sequence(tokens.reshape(batch * trains, steps, -1))
        lengths = node_mask.reshape(batch * trains, steps).sum(dim=1)
        last = (lengths.long() - 1).clamp(min=0)
        encoded = outputs[torch.arange(outputs.shape[0], device=outputs.device), last]
        encoded = encoded * (lengths > 0).float().unsqueeze(-1)

        per_train = self.train_projection(
            torch.cat([encoded, train_scalars.reshape(batch * trains, -1)], dim=-1)
        ).reshape(batch, trains, -1)

        return _masked_pool(per_train, train_mask)


class ScheduleEvaluator(nn.Module):
    def __init__(
        self,
        hidden: int = 64,
        rounds: int = 3,
        trunk_layers: int = 3,
        sequence_layers: int = 2,
        num_buckets: int = NUM_DELAY_BUCKETS,
        dropout: float = 0.0,
    ):
        super().__init__()
        self.graph_encoder = GraphEncoder(hidden=hidden, rounds=rounds)
        self.schedule_encoder = ScheduleEncoder(
            node_hidden=hidden, hidden=hidden, layers=sequence_layers,
            dropout=dropout,
        )
        regulariser = [nn.Dropout(dropout)] if dropout > 0 else []
        trunk_input = hidden * 2 + self.schedule_encoder.output_features
        trunk: list[nn.Module] = [
            nn.Linear(trunk_input, hidden), nn.ReLU(), *regulariser
        ]
        for _ in range(trunk_layers - 1):
            trunk += [nn.Linear(hidden, hidden), nn.ReLU(), *regulariser]
        self.trunk = nn.Sequential(*trunk)
        self.arrival_head = nn.Linear(hidden, 1)
        self.delay_head = nn.Linear(hidden, num_buckets)
        # Share of planned connections a passenger still gets. A ratio in
        # [0, 1], so it is trained as a logit and squashed, not regressed
        # raw — that keeps it inside the range by construction.
        self.connection_head = nn.Linear(hidden, 1)
        self._config = {
            "hidden": hidden,
            "rounds": rounds,
            "trunk_layers": trunk_layers,
            "sequence_layers": sequence_layers,
            "num_buckets": num_buckets,
            "dropout": dropout,
        }

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
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """-> `(arrival_logit, delay_logits, connection_logit)`."""
        node_embeddings = self.graph_encoder(
            graph_nodes, graph_node_mask, edge_index, edge_features, edge_mask
        )
        graph_vector = _masked_pool(node_embeddings, graph_node_mask)
        schedule_vector = self.schedule_encoder(
            node_embeddings, schedule_nodes, waits, node_mask, stop_flags,
            train_scalars, train_mask,
        )
        hidden = self.trunk(torch.cat([graph_vector, schedule_vector], dim=-1))
        return (
            self.arrival_head(hidden).squeeze(-1),
            self.delay_head(hidden),
            self.connection_head(hidden).squeeze(-1),
        )

    @torch.no_grad()
    def predict(self, *inputs) -> Dict[str, torch.Tensor]:
        """Probabilities, the most likely delay bucket, and connections kept."""
        self.eval()
        arrival_logit, delay_logits, connection_logit = self(*inputs)
        return {
            "all_arrived_probability": torch.sigmoid(arrival_logit),
            "delay_bucket_probabilities": torch.softmax(delay_logits, dim=-1),
            "delay_bucket": delay_logits.argmax(dim=-1),
            "connections_kept_ratio": torch.sigmoid(connection_logit),
        }

    def save(self, path: str | Path) -> str:
        torch.save(
            {
                "state_dict": self.state_dict(),
                "config": self._config,
                "bucket_labels": list(DELAY_BUCKET_LABELS),
            },
            Path(path),
        )
        return str(path)

    @classmethod
    def load(
        cls, path: str | Path, map_location: Optional[str] = "cpu"
    ) -> "ScheduleEvaluator":
        payload = torch.load(path, map_location=map_location, weights_only=False)
        model = cls(**payload["config"])
        model.load_state_dict(payload["state_dict"])
        model.eval()
        return model


__all__ = ["GraphEncoder", "ScheduleEncoder", "ScheduleEvaluator"]
