"""The value network: how good is the *end* this state leads to.

One network per metric. Each reads a state exactly as `observation.encode`
describes it and returns a single number in [0, 1] — an estimate of the
metric the run will finally achieve if the search carries on from here,
picking high-value nodes as it always does. It is not a judgement of the
state as it stands: a scattered state the search reliably rescues should
score high, a tidy one that always ends in gridlock should score low.

Shape:

    infrastructure ─► message passing ─► a vector per node ─┬─► network summary
                                                            │
    trains ─► look up the node each is drawn at ────────────┴─► a vector per
              + its own numbers ─► small MLP ─► pooled over trains
                                                    │
    situation numbers ──────────────────────────────┴─► trunk ─► one value

Trains are pooled by mean *and* maximum: they have no order and no fixed
number, so the summary has to be symmetric, and the maximum is what keeps a
single train in trouble from being averaged away.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import torch
from torch import nn

from app.policies.tree_search.observation import (
    EDGE_FEATURES,
    GLOBAL_FEATURES,
    NODE_FEATURES,
    TRAIN_FEATURES,
)


class GraphEncoder(nn.Module):
    """Message passing over the decision-point graph.

    Messages travel both along edges and against them: what a junction is
    worth depends on what feeds into it as much as on where it leads. Node
    meaning is therefore *computed* from position in the network rather than
    looked up in a table, which is what lets one set of weights apply to a
    railway the model has never seen.
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
        node_mask: torch.Tensor,       # (B, N)
        edge_index: torch.Tensor,      # (B, E, 2) long
        edge_features: torch.Tensor,   # (B, E, edge_features)
        edge_mask: torch.Tensor,       # (B, E)
    ) -> torch.Tensor:
        batch, nodes, _ = graph_nodes.shape
        edges = edge_index.shape[1]
        device = graph_nodes.device

        # Flatten the batch so every edge of every graph is one scatter.
        offset = (torch.arange(batch, device=device) * nodes).view(batch, 1)
        source = (edge_index[..., 0] + offset).reshape(-1)
        target = (edge_index[..., 1] + offset).reshape(-1)
        weight = edge_mask.reshape(-1, 1)
        flat_edges = edge_features.reshape(batch * edges, -1)

        state = self.input_projection(graph_nodes).reshape(batch * nodes, -1)
        node_weight = node_mask.reshape(-1, 1)
        incoming = torch.zeros(batch * nodes, 1, device=device)
        incoming.index_add_(0, target, weight)
        outgoing = torch.zeros(batch * nodes, 1, device=device)
        outgoing.index_add_(0, source, weight)

        for round_index in range(self.rounds):
            along = self.forward_messages[round_index](
                torch.cat([state[source], flat_edges], dim=-1)
            ) * weight
            against = self.backward_messages[round_index](
                torch.cat([state[target], flat_edges], dim=-1)
            ) * weight
            gathered_in = torch.zeros_like(state)
            gathered_in.index_add_(0, target, along)
            gathered_out = torch.zeros_like(state)
            gathered_out.index_add_(0, source, against)
            state = state + torch.relu(self.updates[round_index](torch.cat(
                [
                    state,
                    gathered_in / incoming.clamp(min=1.0),
                    gathered_out / outgoing.clamp(min=1.0),
                ],
                dim=-1,
            )))
            state = state * node_weight
        return state.reshape(batch, nodes, -1)


def _masked_pool(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Masked mean and maximum over dim 1, concatenated."""
    weights = mask.unsqueeze(-1)
    mean = (values * weights).sum(dim=1) / weights.sum(dim=1).clamp(min=1.0)
    maximum = values.masked_fill(weights == 0, -1e9).max(dim=1).values
    return torch.cat([mean, torch.nan_to_num(maximum, neginf=0.0)], dim=-1)


class StateValueNet(nn.Module):
    """Predicts one metric's final value from a partial state."""

    def __init__(
        self,
        hidden: int = 64,
        rounds: int = 3,
        trunk_layers: int = 3,
        dropout: float = 0.0,
        metric: str = "punctuality",
    ):
        super().__init__()
        self.metric = metric
        self.graph_encoder = GraphEncoder(hidden=hidden, rounds=rounds)
        self.train_projection = nn.Sequential(
            nn.Linear(hidden + TRAIN_FEATURES, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        regulariser = [nn.Dropout(dropout)] if dropout > 0 else []
        trunk_input = hidden * 4 + GLOBAL_FEATURES
        trunk = [nn.Linear(trunk_input, hidden), nn.ReLU(), *regulariser]
        for _ in range(trunk_layers - 1):
            trunk += [nn.Linear(hidden, hidden), nn.ReLU(), *regulariser]
        self.trunk = nn.Sequential(*trunk)
        self.head = nn.Linear(hidden, 1)
        self._config = {
            "hidden": hidden, "rounds": rounds, "trunk_layers": trunk_layers,
            "dropout": dropout, "metric": metric,
        }

    def forward(
        self,
        graph_nodes: torch.Tensor,     # (B, N, NODE_FEATURES)
        node_mask: torch.Tensor,       # (B, N)
        edge_index: torch.Tensor,      # (B, E, 2)
        edge_features: torch.Tensor,   # (B, E, EDGE_FEATURES)
        edge_mask: torch.Tensor,       # (B, E)
        train_nodes: torch.Tensor,     # (B, T) long
        train_features: torch.Tensor,  # (B, T, TRAIN_FEATURES)
        train_mask: torch.Tensor,      # (B, T)
        globals_: torch.Tensor,        # (B, GLOBAL_FEATURES)
    ) -> torch.Tensor:
        """-> one logit per state, shape (B,). Inputs are exactly what
        `observation.stack` returns, in that order."""
        node_embeddings = self.graph_encoder(
            graph_nodes, node_mask, edge_index, edge_features, edge_mask)
        batch, trains = train_nodes.shape
        hidden = node_embeddings.shape[-1]

        where = torch.gather(
            node_embeddings, 1,
            train_nodes.unsqueeze(-1).expand(batch, trains, hidden).clamp(min=0),
        )
        per_train = self.train_projection(
            torch.cat([where, train_features], dim=-1))
        fleet = _masked_pool(per_train, train_mask)
        network = _masked_pool(node_embeddings, node_mask)
        trunk = self.trunk(torch.cat([network, fleet, globals_], dim=-1))
        return self.head(trunk).squeeze(-1)

    @torch.no_grad()
    def predict(self, *inputs) -> torch.Tensor:
        """Values in [0, 1], one per state."""
        self.eval()
        return torch.sigmoid(self(*inputs))

    def save(self, path: str | Path) -> str:
        torch.save(
            {"state_dict": self.state_dict(), "config": self._config},
            Path(path),
        )
        return str(path)

    @classmethod
    def load(
        cls, path: str | Path, map_location: Optional[str] = "cpu"
    ) -> "StateValueNet":
        payload = torch.load(path, map_location=map_location, weights_only=False)
        model = cls(**payload["config"])
        model.load_state_dict(payload["state_dict"])
        model.eval()
        return model


def evaluate_states(
    models: Dict[str, StateValueNet], observations, device: str = "cpu"
) -> Dict[str, list]:
    """Every model's value for every observation, batched in one pass."""
    from app.policies.tree_search.observation import LONG_SLOTS, stack

    if not observations:
        return {}
    tensors = [
        torch.tensor(
            array,
            dtype=torch.long if index in LONG_SLOTS else torch.float32,
            device=device,
        )
        for index, array in enumerate(stack(observations))
    ]
    return {
        name: model.predict(*tensors).cpu().tolist()
        for name, model in models.items()
    }


__all__ = ["GraphEncoder", "StateValueNet", "evaluate_states"]
