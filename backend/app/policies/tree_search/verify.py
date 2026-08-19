"""Ground truth for a plan: play it in Flatland itself.

The search plans in a fast model of the railway. This is where that model
is held to account — the committed schedules are replayed in the real
environment, one step at a time, and what actually happened is reported.

Used by the Director's verify endpoint, and by the tests that check the
model and the environment still agree.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from flatland.envs.rail_env import RailEnv

from app.policies.goal_based_policies.connections import (
    evaluate_connections,
    observed_times,
    planned_connections,
    station_watch_cells,
)
from app.policies.goal_based_policies.infrastructure_graph import (
    DecisionPointGraph,
)
from app.policies.goal_based_policies.rollout import run_schedules
from app.policies.goal_based_policies.safety import SafetyParams, assess_safety
from app.policies.goal_based_policies.schedule import TrainSchedule
from app.policies.tree_search import metrics as metric_model


def verify_plan(
    env: RailEnv,
    graph: DecisionPointGraph,
    stations: Sequence,
    schedules: Sequence[TrainSchedule],
    safety_params: SafetyParams = SafetyParams(),
) -> Dict[str, object]:
    """Run one full episode under these schedules and report the outcome.

    Steps `env` to its end — hand in a freshly built environment, not one
    another rollout has already used.

    `punctuality` is the same utility the search maximises, computed from
    what the episode actually did, so a predicted score and a verified one
    are directly comparable.
    """
    connections = planned_connections(env, stations)
    result = run_schedules(
        env, graph, schedules, watch_cells=station_watch_cells(stations)
    )
    report = evaluate_connections(
        connections, observed_times(stations, result.occupancy)
    )
    safety = assess_safety(env, graph, schedules, params=safety_params)
    trains = max(1, len(env.agents))
    arrived = sum(1 for step in result.arrivals.values() if step is not None)
    return {
        "total_delay": int(result.total_delay),
        "all_arrived": bool(result.all_arrived),
        "arrived": int(arrived),
        "trains": int(trains),
        "band": int(metric_model.delay_band(result.total_delay)),
        "punctuality": float(
            metric_model.ARRIVAL_SHARE * (arrived / trains)
            + (1.0 - metric_model.ARRIVAL_SHARE)
            * metric_model.BAND_VALUES[
                metric_model.delay_band(result.total_delay)]
        ),
        "connections_total": int(report.total),
        "connections_kept": int(report.kept),
        "kept_ratio": float(report.kept_ratio),
        "safety": float(safety.safety),
        "steps": int(result.steps),
    }


__all__ = ["verify_plan"]
