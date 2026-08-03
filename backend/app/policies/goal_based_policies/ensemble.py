"""Weighted three-axis scoring of candidate schedule sets.

The Director's value function: a candidate plan is scored
on punctuality, connections and stability, each as a utility in [0, 1], and
the three are combined with the user's weights into one number the search
maximises. Punctuality and connections come from the learned models
(`ScheduleEvaluator`, `ConnectionTransformer`); stability comes from the
static safety measure (`assess_safety`) — computed, not predicted.

What "punctuality" means here, precisely:

    U_delay = 0.5 * P(all trains arrive)
            + 0.5 * sum_b p_b * BUCKET_UTILITIES[b]

with `BUCKET_UTILITIES = (1.0, 0.8, 0.6, 0.4, 0.2, 0.0)` over the six delay
buckets (0-4, 5-14, 15-29, 30-44, 45-59, 60+ minutes). The blend keeps both
failure modes visible: a plan that arrives but very late, and a plan that is
punctual for whoever arrives while losing trains. Revisit if a future weight sweep argues otherwise.

What "connections" means:

    U_conn = geometric mean of the per-transfer kept probabilities
           = exp(mean(log p_i)),  1.0 when there is nothing to keep

An arithmetic mean does not steer: it saturates
near 1 on scenarios whose transfers are mostly robust, so candidates stop
being distinguishable exactly when the dial is turned up. The geometric
mean is the per-transfer-normalized probability that *all* transfers
survive — one doomed transfer moves it the way a broken connection is
actually experienced, and a 0.5 among 0.99s is no longer averaged away.
The transformer's plain mean stays in the breakdown as `kept_ratio`; it
is the number to *report*, not the one to optimise.

The combination is a weighted *sum* of the three utilities — deliberately,
so the sliders behave predictably (the
geometric mean's veto semantics live inside the safety score already).

Scoring N candidates of one scenario shares everything that does not depend
on the schedules: stations, planned connections and the network's bypass
analysis are resolved once per scenario (`ScenarioContext`), and the model
passes are batched. Connection *features* are timetable-planned quantities,
identical for every candidate — the models see a candidate's schedules
through the train tokens and the crowding features, which `encode_sample`
derives per candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np
import torch

from flatland.envs.rail_env import RailEnv

from app.policies.goal_based_policies.connection_model import ConnectionTransformer
from app.policies.goal_based_policies.connections import (
    ConnectionOutcome,
    PlannedConnection,
    planned_connections,
)
from app.policies.goal_based_policies.dataset import (
    encode_connections,
    encode_sample,
    stack_samples,
)
from app.policies.goal_based_policies.evaluator import ScheduleEvaluator
from app.policies.goal_based_policies.infrastructure_graph import (
    DecisionPointGraph,
)
from app.policies.goal_based_policies.rollout import NUM_DELAY_BUCKETS
from app.policies.goal_based_policies.safety import (
    SafetyParams,
    SafetyReport,
    assess_safety,
    corridor_alternatives,
)
from app.policies.goal_based_policies.schedule import TrainSchedule
from app.policies.goal_based_policies.stations import resolve_stations

# Utility of landing in each delay bucket, best to worst. Length must match
# the bucket count; linear steps until a sweep says otherwise.
BUCKET_UTILITIES: Tuple[float, ...] = (1.0, 0.8, 0.6, 0.4, 0.2, 0.0)
assert len(BUCKET_UTILITIES) == NUM_DELAY_BUCKETS

# Share of the punctuality utility carried by P(all arrived); the rest is
# the expected bucket utility.
ARRIVAL_BLEND = 0.5

# Model input slots that hold indices, not measurements (the connection
# index block is collated separately in `_input_tensors`).
_LONG_INPUTS = {2, 5}  # edge_index, schedule_nodes
_MODEL_INPUTS = 11     # graph + schedule fields, in stack_samples order


@dataclass(frozen=True)
class DirectorWeights:
    """How much the Director values each axis. Any non-negative scale;
    scoring normalises to sum 1 so sliders need no coupling in the UI."""
    punctuality: float = 1.0
    connections: float = 1.0
    stability: float = 1.0

    def __post_init__(self) -> None:
        values = (self.punctuality, self.connections, self.stability)
        if any(v < 0 for v in values):
            raise ValueError(f"weights must be non-negative, got {values}")
        if sum(values) <= 0:
            raise ValueError("at least one weight must be positive")

    def normalized(self) -> Tuple[float, float, float]:
        total = self.punctuality + self.connections + self.stability
        return (
            self.punctuality / total,
            self.connections / total,
            self.stability / total,
        )


def punctuality_utility(
    arrival_probability: float, bucket_probabilities: Sequence[float]
) -> float:
    """See the module docstring — this defines "punctuality"."""
    expected = float(
        sum(p * u for p, u in zip(bucket_probabilities, BUCKET_UTILITIES))
    )
    return ARRIVAL_BLEND * float(arrival_probability) + (1 - ARRIVAL_BLEND) * expected


def weighted_utility(
    punctuality: float, connections: float, stability: float,
    weights: DirectorWeights,
) -> float:
    w_punct, w_conn, w_safe = weights.normalized()
    return w_punct * punctuality + w_conn * connections + w_safe * stability


def connection_utility(probabilities: Sequence[float]) -> float:
    """See the module docstring — this defines "connections".

    Probabilities are clamped away from zero so a single hopeless
    transfer scores near-zero utility instead of collapsing to exactly
    0.0 and erasing every other transfer from the comparison.
    """
    values = np.asarray(probabilities, dtype=np.float64)
    if values.size == 0:
        return 1.0
    return float(np.exp(np.log(np.clip(values, 1e-4, 1.0)).mean()))


@dataclass(frozen=True)
class CandidateScore:
    """One candidate's three utilities, their weighted combination, and the
    evidence behind them. `breakdown` is JSON-able — it is the payload the
    Director HMI shows as the explanation for a choice."""
    punctuality: float
    connections: float
    stability: float
    weighted: float
    safety_report: SafetyReport
    breakdown: Dict[str, object]


@dataclass
class ScenarioContext:
    """Everything scoring needs that does not depend on the candidate.

    Build once per scenario, score any number of candidate schedule sets
    against it. Stations, planned connections and the network bypass
    analysis are all functions of (env, timetable, infrastructure) alone.
    """
    env: RailEnv
    graph: DecisionPointGraph
    stations: List[object]
    connections: List[PlannedConnection]
    pseudo_outcomes: List[ConnectionOutcome]
    local_nodes: Dict[int, int]
    alternatives: Dict[frozenset, bool]
    layout: int = 0

    @classmethod
    def build(
        cls, env: RailEnv, graph: DecisionPointGraph, layout: int = 0
    ) -> "ScenarioContext":
        stations = resolve_stations(env)
        connections = planned_connections(env, stations)
        # encode_connections reads only `.connection` and ignores `.kept` at
        # inference; the placeholder outcome carries the plan, not a result.
        pseudo = [
            ConnectionOutcome(
                connection=c, kept=False, reason="planned",
                feeder_time=None, connector_time=None,
            )
            for c in connections
        ]
        ordered = sorted(graph.nodes)
        local = {graph.nodes[c].node_id: i for i, c in enumerate(ordered)}
        return cls(
            env=env,
            graph=graph,
            stations=stations,
            connections=connections,
            pseudo_outcomes=pseudo,
            local_nodes=local,
            alternatives=corridor_alternatives(graph),
            layout=layout,
        )


def _encode_candidate(
    context: ScenarioContext, schedules: Sequence[TrainSchedule]
):
    sample = encode_sample(
        context.env, context.graph, context.layout, schedules,
        source="candidate",
    )
    rows = {s.handle: r for r, s in enumerate(schedules)}
    (
        sample.connection_features, sample.connection_index,
        sample.connection_kept, sample.connection_mask,
    ) = encode_connections(
        context.env, context.graph, context.stations,
        context.pseudo_outcomes, context.local_nodes, rows,
    )
    return sample


def _input_tensors(samples, device: str):
    stacked = stack_samples(samples)
    inputs = [
        torch.tensor(
            stacked[i],
            dtype=torch.long if i in _LONG_INPUTS else torch.float32,
            device=device,
        )
        for i in range(_MODEL_INPUTS)
    ]
    connection_inputs = [
        torch.tensor(stacked[14], dtype=torch.float32, device=device),
        torch.tensor(stacked[15], dtype=torch.long, device=device),
        torch.tensor(stacked[17], dtype=torch.float32, device=device),
    ]
    return inputs, connection_inputs


def score_candidates(
    context: ScenarioContext,
    candidates: Sequence[Sequence[TrainSchedule]],
    weights: DirectorWeights,
    evaluator: ScheduleEvaluator,
    connection_model: ConnectionTransformer,
    safety_params: SafetyParams = SafetyParams(),
    device: str = "cpu",
    batch_size: int = 64,
) -> List[CandidateScore]:
    """Score candidate schedule sets for one scenario, batched.

    Returns one `CandidateScore` per candidate, in order. The caller keeps
    the argmax; everything needed to *explain* the ranking is in each
    score's breakdown.
    """
    scores: List[CandidateScore] = []
    for start in range(0, len(candidates), batch_size):
        chunk = candidates[start:start + batch_size]
        samples = [_encode_candidate(context, c) for c in chunk]
        inputs, connection_inputs = _input_tensors(samples, device)

        evaluated = evaluator.predict(*inputs)
        predicted = connection_model.predict(*inputs, *connection_inputs)

        arrival = evaluated["all_arrived_probability"].cpu().numpy()
        buckets = evaluated["delay_bucket_probabilities"].cpu().numpy()
        kept_ratio = predicted["kept_ratio"].cpu().numpy()
        per_connection = predicted["connection_probability"].cpu().numpy()
        connection_mask = np.stack([s.connection_mask for s in samples])

        for row, schedules in enumerate(chunk):
            report = assess_safety(
                context.env, context.graph, schedules,
                params=safety_params, alternatives=context.alternatives,
            )
            u_delay = punctuality_utility(arrival[row], buckets[row])
            real = connection_mask[row] > 0
            u_conn = connection_utility(per_connection[row][real])
            u_safe = report.safety
            breakdown: Dict[str, object] = {
                "all_arrived_probability": float(arrival[row]),
                "delay_bucket_probabilities": [
                    float(p) for p in buckets[row]
                ],
                "kept_ratio": float(kept_ratio[row]),
                "connection_probabilities": [
                    float(p) for p in per_connection[row][real]
                ],
                "safety": {
                    "safety": report.safety,
                    "slack_score": report.slack_score,
                    "deadlock_score": report.deadlock_score,
                    "track_score": report.track_score,
                    "cascade_score": report.cascade_score,
                },
                "utilities": {
                    "punctuality": u_delay,
                    "connections": u_conn,
                    "stability": u_safe,
                },
                "weights": dict(zip(
                    ("punctuality", "connections", "stability"),
                    weights.normalized(),
                )),
            }
            scores.append(CandidateScore(
                punctuality=u_delay,
                connections=u_conn,
                stability=u_safe,
                weighted=weighted_utility(u_delay, u_conn, u_safe, weights),
                safety_report=report,
                breakdown=breakdown,
            ))
    return scores


__all__ = [
    "ARRIVAL_BLEND",
    "BUCKET_UTILITIES",
    "CandidateScore",
    "DirectorWeights",
    "ScenarioContext",
    "connection_utility",
    "punctuality_utility",
    "score_candidates",
    "weighted_utility",
]
