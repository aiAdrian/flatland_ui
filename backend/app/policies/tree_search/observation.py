"""Turning a world state into what the networks read.

Every travelling train is drawn at the node it is heading for, together with
how many steps it still needs to get there. The projection keeps the state
inside the reduced graph — the networks never have to learn a Flatland grid
— while the remaining travel time keeps two situations that snap to the
same nodes but are minutes apart from looking identical.

Nothing here plans. The one derived quantity is `remaining distance`: a
lower bound on the travel a train still has ahead of it, which describes
where the train *is* in its run rather than proposing what it should do.

Three blocks, matching the setup document:

- the infrastructure, which never changes and is therefore encoded once per
  scenario and reused by every node;
- the trains, one row each;
- a handful of numbers about the situation as a whole.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from app.policies.tree_search.scenario import Scenario
from app.policies.tree_search.simulator import WorldState, deciding

NODE_FEATURES = 7
EDGE_FEATURES = 3
TRAIN_FEATURES = 10
GLOBAL_FEATURES = 4

DEGREE_SCALE = 8.0          # observed maximum in/out degree is 7
LOG_TIME_REFERENCE = 128.0  # edge travel times are skewed: median 2, max 90


@dataclass(frozen=True)
class GraphTensors:
    """The infrastructure, encoded once per scenario."""
    nodes: np.ndarray        # (N, NODE_FEATURES) float32
    edge_index: np.ndarray   # (E, 2) int64
    edge_features: np.ndarray  # (E, EDGE_FEATURES) float32

    @property
    def node_count(self) -> int:
        return int(self.nodes.shape[0])


@dataclass(frozen=True)
class Observation:
    """One state, ready for the network."""
    graph: GraphTensors
    train_nodes: np.ndarray   # (T,) int64 — the node each train is drawn at
    train_features: np.ndarray  # (T, TRAIN_FEATURES) float32
    globals: np.ndarray       # (GLOBAL_FEATURES,) float32


def encode_graph(scenario: Scenario) -> GraphTensors:
    """Node and edge features. Cached on the scenario — the infrastructure
    is the same for every node of the tree."""
    cached = getattr(scenario, "_graph_tensors", None)
    if cached is not None:
        return cached

    graph = scenario.graph
    ordered = sorted(graph.nodes)
    index_of = {cell: index for index, cell in enumerate(ordered)}
    horizon = float(scenario.horizon)
    scale = float(max(scenario.env.width, scenario.env.height))

    out_degree = {}
    in_degree = {}
    for edge in graph.edges:
        out_degree[edge.from_cell] = out_degree.get(edge.from_cell, 0) + 1
        in_degree[edge.to_cell] = in_degree.get(edge.to_cell, 0) + 1

    nodes = np.zeros((len(ordered), NODE_FEATURES), dtype=np.float32)
    for index, cell in enumerate(ordered):
        node = graph.nodes[cell]
        nodes[index] = (
            1.0 if "station" in node.kinds else 0.0,
            1.0 if "switch_decision" in node.kinds else 0.0,
            1.0 if "split_decision" in node.kinds else 0.0,
            out_degree.get(cell, 0) / DEGREE_SCALE,
            in_degree.get(cell, 0) / DEGREE_SCALE,
            cell[0] / scale,
            cell[1] / scale,
        )

    alternatives = graph.edges_have_alternative_route()
    edge_index = np.zeros((len(graph.edges), 2), dtype=np.int64)
    edge_features = np.zeros((len(graph.edges), EDGE_FEATURES), dtype=np.float32)
    for position, edge in enumerate(graph.edges):
        edge_index[position] = (
            index_of[edge.from_cell], index_of[edge.to_cell]
        )
        edge_features[position] = (
            edge.travel_time / horizon,
            float(np.log1p(edge.travel_time) / np.log1p(LOG_TIME_REFERENCE)),
            1.0 if alternatives[position] else 0.0,
        )

    tensors = GraphTensors(
        nodes=nodes, edge_index=edge_index, edge_features=edge_features
    )
    object.__setattr__(scenario, "_graph_tensors", tensors)
    return tensors


def _projection(scenario: Scenario, train) -> Tuple[Tuple[int, int], int]:
    """Where a train is drawn, and how many steps until it is really there.

    Standing at a node: that node, in zero steps. Travelling: the node it is
    heading for, in the steps still to drive. Not yet departed: its origin,
    in the steps until its slot comes up.
    """
    if train.edge is not None:
        return train.edge.to_cell, len(train.edge.path) - 1 - train.index
    if not train.departed:
        data = scenario.trains[train.handle]
        return train.cell, max(0, data.earliest_departure - 0)
    return train.cell, 0


def encode(scenario: Scenario, state: WorldState) -> Observation:
    """The full observation of one state."""
    graph = encode_graph(scenario)
    ordered = sorted(scenario.graph.nodes)
    index_of = {cell: index for index, cell in enumerate(ordered)}
    horizon = float(scenario.horizon)
    now = float(state.step)
    choosing = set(deciding(scenario, state))

    count = len(state.trains)
    train_nodes = np.zeros((count,), dtype=np.int64)
    features = np.zeros((count, TRAIN_FEATURES), dtype=np.float32)

    for row, train in enumerate(state.trains):
        data = scenario.trains[train.handle]
        cell, steps_out = _projection(scenario, train)
        if not train.departed:
            steps_out = max(0, data.earliest_departure - state.step)
        train_nodes[row] = index_of.get(cell, 0)

        remaining_stops = data.stops[train.stop_index:]
        heading = (
            train.edge.in_direction if train.edge is not None else train.heading
        )
        distance = scenario.remaining_distance(cell, heading, remaining_stops)
        features[row] = (
            steps_out / horizon,
            train.wait_left / horizon,
            (data.latest_arrival - now) / horizon,
            max(0.0, now - data.latest_arrival) / horizon,
            len(remaining_stops) / max(1, len(data.stops)),
            (horizon if distance is None else distance) / horizon,
            0.0 if distance is None else 1.0,   # is the run still possible
            1.0 if train.departed else 0.0,
            1.0 if train.done else 0.0,
            1.0 if train.handle in choosing else 0.0,
        )

    done = sum(1 for t in state.trains if t.done)
    departed = sum(1 for t in state.trains if t.departed)
    globals_ = np.array([
        now / horizon,
        done / max(1, count),
        departed / max(1, count),
        len(choosing) / max(1, count),
    ], dtype=np.float32)

    return Observation(
        graph=graph, train_nodes=train_nodes, train_features=features,
        globals=globals_,
    )


def stack(observations: Sequence[Observation]):
    """Batch observations into the nine arrays the network reads.

    States of one scenario share a graph and states of different scenarios
    do not, so every block is padded to the batch's largest and carries a
    mask. Padded nodes, edges and trains are then excluded from message
    passing and from every pooling, which is what lets a batch mix
    scenarios of different sizes without one bleeding into another.
    """
    if not observations:
        raise ValueError("nothing to stack")
    batch = len(observations)
    nodes = max(o.graph.nodes.shape[0] for o in observations)
    edges = max(1, max(o.graph.edge_index.shape[0] for o in observations))
    trains = max(o.train_features.shape[0] for o in observations)

    graph_nodes = np.zeros((batch, nodes, NODE_FEATURES), dtype=np.float32)
    node_mask = np.zeros((batch, nodes), dtype=np.float32)
    edge_index = np.zeros((batch, edges, 2), dtype=np.int64)
    edge_features = np.zeros((batch, edges, EDGE_FEATURES), dtype=np.float32)
    edge_mask = np.zeros((batch, edges), dtype=np.float32)
    train_nodes = np.zeros((batch, trains), dtype=np.int64)
    features = np.zeros((batch, trains, TRAIN_FEATURES), dtype=np.float32)
    train_mask = np.zeros((batch, trains), dtype=np.float32)
    globals_ = np.zeros((batch, GLOBAL_FEATURES), dtype=np.float32)

    for row, observation in enumerate(observations):
        graph = observation.graph
        node_count = graph.nodes.shape[0]
        edge_count = graph.edge_index.shape[0]
        train_count = observation.train_features.shape[0]
        graph_nodes[row, :node_count] = graph.nodes
        node_mask[row, :node_count] = 1.0
        edge_index[row, :edge_count] = graph.edge_index
        edge_features[row, :edge_count] = graph.edge_features
        edge_mask[row, :edge_count] = 1.0
        train_nodes[row, :train_count] = observation.train_nodes
        features[row, :train_count] = observation.train_features
        train_mask[row, :train_count] = 1.0
        globals_[row] = observation.globals

    return (
        graph_nodes, node_mask, edge_index, edge_features, edge_mask,
        train_nodes, features, train_mask, globals_,
    )


# Which of `stack`'s slots hold indices rather than measurements.
LONG_SLOTS = (2, 5)


__all__ = [
    "EDGE_FEATURES",
    "GLOBAL_FEATURES",
    "NODE_FEATURES",
    "TRAIN_FEATURES",
    "GraphTensors",
    "Observation",
    "encode",
    "encode_graph",
    "stack",
]
