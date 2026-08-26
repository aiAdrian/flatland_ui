"""Goal-based policies: reduced decision-point graph over Flatland infrastructure.

Preprocessing for goal-oriented agents: compress the rail grid of a running
session env into a graph whose nodes are only the cells where a decision can
be made (station stops + the wait cells in front of each switch), connected
by the plain track runs between them. On top of that graph, a train's run is
a schedule of `[node_id, wait, ...]` pairs that `SchedulePlayer` can execute.

The learned schedule judges live in `evaluator`, `connection_model`,
`ensemble` and `priors` (plus the `train_*` scripts) — they need torch and
are therefore imported on demand, not from this package's top level.
"""
from app.policies.goal_based_policies.infrastructure_graph import (
    DecisionPointGraph,
    GraphEdge,
    GraphNode,
    SwitchApproach,
    build_decision_point_graph,
    find_switch_cells,
    find_switch_decision_cells,
    station_cells_from_env,
)
from app.policies.goal_based_policies.rollout import (
    DELAY_BUCKET_LABELS,
    NUM_DELAY_BUCKETS,
    RolloutResult,
    delay_bucket,
    run_schedules,
)
from app.policies.goal_based_policies.connections import (
    PlannedConnection,
    StationCall,
    planned_connections,
    planned_order,
    station_calls,
)
from app.policies.goal_based_policies.schedule import (
    ScheduleEntry,
    SchedulePlayer,
    TrainSchedule,
    plan_avoiding_overlaps,
    line_stops,
    plan_line,
    plan_shortest_path,
)
from app.policies.goal_based_policies.stations import (
    Station,
    resolve_stations,
    stations_from_agent_missions,
    stations_from_ecml_fixture,
    stations_from_scene,
)
from app.policies.goal_based_policies.visualization import (
    render_decision_point_graph,
    render_decision_point_graph_on_flatland,
    save_decision_point_graph,
)

__all__ = [
    "DELAY_BUCKET_LABELS",
    "NUM_DELAY_BUCKETS",
    "DecisionPointGraph",
    "GraphEdge",
    "GraphNode",
    "RolloutResult",
    "ScheduleEntry",
    "SchedulePlayer",
    "Station",
    "SwitchApproach",
    "TrainSchedule",
    "build_decision_point_graph",
    "delay_bucket",
    "find_switch_cells",
    "find_switch_decision_cells",
    "plan_avoiding_overlaps",
    "PlannedConnection",
    "StationCall",
    "line_stops",
    "planned_connections",
    "planned_order",
    "station_calls",
    "plan_line",
    "plan_shortest_path",
    "resolve_stations",
    "run_schedules",
    "station_cells_from_env",
    "stations_from_agent_missions",
    "stations_from_ecml_fixture",
    "stations_from_scene",
    "render_decision_point_graph",
    "render_decision_point_graph_on_flatland",
    "save_decision_point_graph",
]
