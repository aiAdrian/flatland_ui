"""Training data for the schedule evaluator.

Samples are `(schedules) -> (all trains arrived, delay bucket)`, labelled by
actually running the schedules in Flatland.

The observation is the decision-point graph **plus** the schedules on it:

- the graph as node features and an edge list carrying travel times, so the
  model can see what the network actually looks like;
- each train's schedule as the sequence of graph nodes it visits (as local
  indices into that graph) and the wait taken at each;
- each train's timetable and how its plan sits inside it (earliest
  departure, deadline, planned duration, slack, total hold).

Giving the graph itself is what makes varying infrastructure workable: node
meaning is *computed* from structure rather than looked up in a global
embedding table, so the same model applies to a network it has never seen,
and nothing depends on ids meaning the same thing across layouts.

By default **every scenario gets its own freshly generated network**, so no
layout is ever seen twice. That makes memorising a particular network
impossible and turns any held-out split into a direct measure of transfer.
Pass an explicit `layouts` pool to go back to reusing a fixed set.

Which networks and scenarios get drawn is a `ScenarioMix`. `TRAINING_MIX`
is the default and is what the shipped models were fitted on; `EVAL_MIXES`
are held-out distributions that push one knob each past where training went,
drawing their layout seeds from a range training never touched so an eval
set provably shares no infrastructure with it (see `eval_set`).

Networks vary in grid size and city count, scenarios in their number of
trains, and schedules come from three sources:

- shortest path per train, conflict-blind (the naive plan),
- shortest path plus the holds the repo's `DeadLockAvoidancePolicy` takes
  when it runs the same scenario (reactive overlap avoidance),
- prioritised planning with cell reservations (`plan_avoiding_overlaps`),
- any of those with random holds layered on.

Measured on this generator, none of the three dominates: the reactive
policy gets ~90% of trains home but freezing its stops into fixed holds
loses that advantage, and reservation planning trims mean delay while
costing arrivals, because a hold can only sit on a decision node — which is
on the running line and therefore blocks the trains behind it. The mix is
there to give the evaluator different *styles* of plan to tell apart, not
because one of them is the good one.
"""
from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from flatland.envs.rail_env import RailEnv
from flatland.envs.step_utils.states import TrainState

from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy
from app.policies.goal_based_policies.infrastructure_graph import (
    DecisionPointGraph,
    _get_transitions,
    build_decision_point_graph,
)
from app.policies.goal_based_policies.connections import (
    evaluate_connections,
    observed_times,
    planned_connections,
    station_calls,
    station_watch_cells,
)
from app.policies.goal_based_policies.rollout import (
    NUM_DELAY_BUCKETS,
    RolloutResult,
    run_schedules,
)
from app.policies.goal_based_policies.stations import resolve_stations
from app.policies.goal_based_policies.schedule import (
    ScheduleEntry,
    TrainSchedule,
    line_stops,
    plan_avoiding_overlaps,
    plan_line,
    plan_shortest_path,
)
from app.policies.goal_based_policies.visualization import build_demo_env

MAX_TRAINS = 8            # rows in the per-train tensor
# Decision points per train fed to the encoder. Measured over multi-stop
# lines (`line_length=4`): median 15, p99 38, max 42 — a 4-leg line is
# several times longer than the single origin->target route this was first
# sized for, so 64 leaves headroom without padding most schedules to waste.
MAX_SCHEDULE_NODES = 64
TRAIN_SCALARS = 5         # timetable features per train
NUM_LAYOUTS = 16          # size of the layout pool
# Graph tensors. Measured on the layout pool: <= 55 nodes and <= 104 edges,
# growing a little with the train count because stations are train targets.
MAX_NODES = 96
MAX_EDGES = 256
NODE_FEATURES = 7
# Edge features: 0 travel/horizon, 1 log travel, 2 has-alternative-route,
# 3 crowding (how many trains route through this edge), 4 peak occupancy
# (how many of those are planned to be on it at the same time). The first
# three are structural and filled by encode_graph; the last two depend on
# the schedules and are filled by encode_sample.
EDGE_FEATURES = 5
STRUCTURAL_EDGE_FEATURES = 3
# Per schedule node: (is a scheduled stop, is the terminus).
STOP_FLAGS = 2
# Planned connections kept per scenario, for the per-connection model.
# Measured over the generated set: median 7, p99 63, max 68 — 96 clears the
# observed maximum with room, and encoding refuses rather than truncates.
MAX_CONNECTIONS = 96
# Per connection: planned gap, feeder planned time, connector planned time
# (all as a fraction of the horizon). Who the connection joins is carried by
# the index tensors, not here.
CONNECTION_FEATURES = 3

# Normalisation constants, all set from measurements over the layout pool
# rather than guessed. Durations are divided by the episode horizon so every
# time-like feature is in the same unit — "fraction of the time available" —
# and comparable with the deadlines in `train_scalars`.
DEGREE_SCALE = 8.0        # observed max in/out degree is 7
APPROACH_SCALE = 2.0      # a wait cell guards at most 2 switch approaches
LOG_TIME_REFERENCE = 128.0  # edge travel times are skewed: median 2, max 90
CROWD_SCALE = float(MAX_TRAINS)  # at most every train routes through an edge


@dataclass(frozen=True)
class Layout:
    """One infrastructure the model gets to learn over many scenarios."""
    index: int
    seed: int
    size: int
    cities: int
    line_length: int = 4   # cities a train's line calls at; UI uses 4


@dataclass(frozen=True)
class ScenarioMix:
    """The distribution a generated scenario is drawn from.

    Grouped rather than passed as loose arguments because the knobs are only
    meaningful together: difficulty is a *combination* of how tight the
    network is, how many trains share it and how far each one runs, and a
    named mix is what lets an eval set be reproduced from its name.

    `seed_range` is the interval layout seeds are drawn from. Two mixes with
    disjoint ranges can never build the same infrastructure, which is how an
    eval set is kept provably free of the networks a model trained on —
    stronger than trusting that a different generator seed happened not to
    collide.

    The defaults are exactly the distribution the shipped models were
    trained on; `TRAINING_MIX` names it.

    `name` is stamped onto every sample it produces and survives into the
    cache, so a set built from several mixes can still be scored per mix —
    "the model lost four AUC points" is far less useful than knowing which
    kind of scenario cost them.
    """
    name: str = "training"
    sizes: Tuple[int, ...] = (30, 35, 40, 45, 50, 60)
    cities: Tuple[int, ...] = (2, 3, 4)
    min_trains: int = 2
    max_trains: int = MAX_TRAINS
    line_length: int = 4
    seed_range: Tuple[int, int] = (1, 10_000_000)

    def __post_init__(self) -> None:
        if not self.sizes or not self.cities:
            raise ValueError("a mix needs at least one size and one city count")
        if self.max_trains > MAX_TRAINS:
            raise ValueError(
                f"max_trains={self.max_trains} exceeds MAX_TRAINS={MAX_TRAINS}; "
                "the per-train tensors have no room for more"
            )
        if not 1 <= self.min_trains <= self.max_trains:
            raise ValueError(
                f"need 1 <= min_trains <= max_trains, got "
                f"{self.min_trains}..{self.max_trains}"
            )
        low, high = self.seed_range
        if low > high:
            raise ValueError(f"empty seed_range {self.seed_range}")

    def overlaps_seeds(self, other: "ScenarioMix") -> bool:
        """Could the two mixes ever draw the same layout seed?"""
        return (self.seed_range[0] <= other.seed_range[1]
                and other.seed_range[0] <= self.seed_range[1])


# The distribution the shipped models were trained on.
TRAINING_MIX = ScenarioMix()

# Layout seeds for held-out evaluation. Disjoint from the training range
# (1..10_000_000) so an eval scenario provably cannot be built on a network
# either model was trained on.
EVAL_SEED_RANGE = (10_000_001, 20_000_000)

# Evaluation mixes, each turning one knob past where training went. Chosen
# by measuring the trained connection model on 150 scenarios of each
# candidate rather than by assuming bigger means harder — `control` is the
# training distribution on unseen networks and scored 0.945 AUC, within
# noise of the 0.947 held-out validation, so whatever the others lose is
# attributable to the knob and not to the network being new:
#
#   mix       trains  conn/scen  kept   AUC     vs control
#   control     5.0      15.4    0.33   0.945       —
#   crowded     8.0      34.8    0.35   0.937     -0.9
#   dense       7.0      15.4    0.52   0.932     -1.3
#   long        6.4      45.6    0.18   0.915     -3.0
#   sprawl      7.0      38.0    0.23   0.896     -4.9
#
# Note `long` scores *better* on accuracy and Brier than the control while
# losing 3 AUC points: only 18% of its transfers survive, so guessing
# "broken" is cheap there. That is the reason the eval report leads with
# AUC — the ranking is what degrades, and it is what the HMI needs.
EVAL_MIXES: Tuple[ScenarioMix, ...] = (
    # The training distribution on unseen networks. Not harder — it is the
    # reference the others are read against, and without it "the model
    # scores worse here" cannot be separated from "these networks are new".
    ScenarioMix(name="control", seed_range=EVAL_SEED_RANGE),
    # Small grid, few cities, always many trains: maximum contention per
    # length of track.
    ScenarioMix(
        name="dense", sizes=(30, 35), cities=(2, 3),
        min_trains=6, max_trains=8, seed_range=EVAL_SEED_RANGE,
    ),
    # Training networks run at the very top of the train range, which
    # training only sampled a seventh of the time.
    ScenarioMix(
        name="crowded", min_trains=8, max_trains=8, seed_range=EVAL_SEED_RANGE,
    ),
    # Six-city lines against training's four: more legs to accumulate
    # delay, and three times the transfers per scenario.
    ScenarioMix(
        name="long", sizes=(35, 40, 45), cities=(4, 5),
        min_trains=5, max_trains=8, line_length=6, seed_range=EVAL_SEED_RANGE,
    ),
    # Networks larger than any in training, in grid and in city count.
    ScenarioMix(
        name="sprawl", sizes=(50, 60, 70), cities=(4, 5, 6),
        min_trains=6, max_trains=8, seed_range=EVAL_SEED_RANGE,
    ),
)


@dataclass
class Sample:
    """One encoded scenario with its measured labels.

    The first four fields are the infrastructure, the next four the
    schedules running on it.
    """
    graph_nodes: np.ndarray    # (MAX_NODES, NODE_FEATURES) float32
    graph_node_mask: np.ndarray  # (MAX_NODES,) float32
    edge_index: np.ndarray     # (MAX_EDGES, 2) int64 — (source, target) nodes
    edge_features: np.ndarray  # (MAX_EDGES, EDGE_FEATURES) float32
    edge_mask: np.ndarray      # (MAX_EDGES,) float32
    schedule_nodes: np.ndarray  # (MAX_TRAINS, MAX_SCHEDULE_NODES) int64, local
    waits: np.ndarray          # (MAX_TRAINS, MAX_SCHEDULE_NODES) float32
    node_mask: np.ndarray      # (MAX_TRAINS, MAX_SCHEDULE_NODES) float32
    # (MAX_TRAINS, MAX_SCHEDULE_NODES, STOP_FLAGS) float32. Per visited node:
    # is it a scheduled stop, and is it the train's terminus. A train may be
    # diverted to another platform of a city, but only its *final* city ends
    # the run, so the model has to be able to tell the two apart.
    stop_flags: np.ndarray
    train_scalars: np.ndarray  # (MAX_TRAINS, TRAIN_SCALARS) float32
    train_mask: np.ndarray     # (MAX_TRAINS,) float32
    layout: int                # bookkeeping only — never fed to the model
    all_arrived: float
    bucket: int
    total_delay: int
    connections_total: int = 0   # planned connections in this scenario
    connections_kept: int = 0    # of those, kept in the measured run
    # Per-connection detail, for the model that judges each transfer rather
    # than the scenario as a whole. Aligned rows across all four:
    #   connection_features (MAX_CONNECTIONS, CONNECTION_FEATURES) float32
    #   connection_index    (MAX_CONNECTIONS, 3) int64 — feeder train row,
    #                       connector train row, station node (local index)
    #   connection_kept     (MAX_CONNECTIONS,) float32 — the label
    #   connection_mask     (MAX_CONNECTIONS,) float32
    connection_features: Optional[np.ndarray] = None
    connection_index: Optional[np.ndarray] = None
    connection_kept: Optional[np.ndarray] = None
    connection_mask: Optional[np.ndarray] = None
    source: str = "shortest_path"
    # Which `ScenarioMix` drew this scenario. Kept so a mixed eval set can
    # be scored per mix rather than only in aggregate.
    mix: str = "training"

    @property
    def connections_kept_ratio(self) -> float:
        """How likely a passenger was to get their connection; 1.0 if none."""
        if self.connections_total <= 0:
            return 1.0
        return self.connections_kept / self.connections_total


def default_layouts(count: int = NUM_LAYOUTS, seed: int = 0) -> List[Layout]:
    """A pool of layouts varying in grid size and city count."""
    rng = random.Random(seed)
    return [
        Layout(
            index=index,
            seed=rng.randint(1, 9999),
            size=rng.choice((30, 35, 40, 45, 50, 60)),
            cities=rng.choice((2, 3, 4)),
        )
        for index in range(count)
    ]


def build_layout_env(layout: Layout, number_of_agents: int) -> RailEnv:
    """Env for a layout. The rail is a function of (seed, size, cities), so
    the same layout keeps the same infrastructure — and the same node ids —
    however many trains run on it.

    Built with a flexible terminus so a train may finish at any platform of
    its final city; the dispatching agent is meant to be able to divert to a
    free platform, and without this Flatland would never mark such a train
    arrived.
    """
    return build_demo_env(
        seed=layout.seed,
        width=layout.size,
        height=layout.size,
        number_of_agents=number_of_agents,
        max_num_cities=layout.cities,
        line_length=layout.line_length,
        flexible_terminus=True,
    )


def plan_all_lines(
    env: RailEnv, graph: DecisionPointGraph, dwell: int = 1
) -> Optional[List[TrainSchedule]]:
    """Multi-stop schedule per train, calling at every city on its line.

    Shortest path per leg, chained — still conflict-blind, which is the
    baseline the other sources are built from.
    """
    schedules: List[TrainSchedule] = []
    for handle in range(len(env.agents)):
        schedule = plan_line(graph, env, handle, dwell=dwell)
        if schedule is None or len(schedule.entries) < 2:
            return None
        schedules.append(schedule)
    return schedules


def plan_all_trains(
    env: RailEnv, graph: DecisionPointGraph
) -> Optional[List[TrainSchedule]]:
    """Shortest-path schedule per train, ignoring the other trains."""
    schedules: List[TrainSchedule] = []
    for handle, agent in enumerate(env.agents):
        schedule = plan_shortest_path(
            graph,
            env,
            tuple(int(v) for v in agent.initial_position),
            int(agent.initial_direction),
            tuple(int(v) for v in agent.target),
            handle=handle,
        )
        if schedule is None or len(schedule.entries) < 2:
            return None
        schedules.append(schedule)
    return schedules


def start_heading_of(env: RailEnv, schedule: TrainSchedule) -> int:
    """The heading a schedule starting at the train's origin begins with."""
    return int(env.agents[schedule.handle].initial_direction)


def _schedule_edges(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedule: TrainSchedule,
    start_heading: Optional[int] = None,
) -> List:
    """The graph edges the plan traverses, in order.

    Resolves each consecutive node pair to the edge the player would take
    (feasible from the arrival heading, shortest first). Stops early if a
    pair cannot be resolved, mirroring how playback would fail there.

    `start_heading` is which way the train points at the schedule's *first*
    node, and it is required rather than derivable: a cell offers completely
    different onward edges — often none — depending on the orientation the
    train stands in, because a train cannot turn around. It defaults to the
    agent's initial direction, which is right only when the schedule starts
    at the train's origin. A schedule for a later leg of a multi-stop line
    begins at a station the train reached pointing some other way; passing
    the wrong heading there matches no edge, and this returns a truncated
    list (silently, since an unroutable plan is a legitimate outcome here).
    """
    heading = (
        start_heading_of(env, schedule) if start_heading is None
        else int(start_heading)
    )
    cells = [graph.cell_of(e.node_id) for e in schedule.entries]
    edges: List = []
    for cell, nxt in zip(cells, cells[1:]):
        usable = [
            e for e in graph.edges_from(cell)
            if e.to_cell == nxt
            and _get_transitions(env, cell, heading)[e.out_direction]
        ]
        if not usable:
            break
        edge = min(usable, key=lambda e: (e.travel_time, e.out_direction))
        edges.append(edge)
        heading = edge.in_direction
    return edges


def _node_of_cell(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedule: TrainSchedule,
    handle: int,
    start_heading: Optional[int] = None,
) -> Dict[Tuple[int, int], int]:
    """Map every cell the plan drives over to the schedule index of the last
    decision node at or before it."""
    owner: Dict[Tuple[int, int], int] = {}
    for index, edge in enumerate(
        _schedule_edges(env, graph, schedule, start_heading)
    ):
        for path_cell in edge.path[:-1]:
            owner.setdefault(path_cell, index)
    last = graph.cell_of(schedule.entries[-1].node_id)
    owner.setdefault(last, len(schedule.entries) - 1)
    return owner


def _schedule_cells(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedule: TrainSchedule,
    start_heading: Optional[int] = None,
) -> set:
    """Every grid cell the train's plan drives over, ignoring timing.

    Purely spatial: which track the train uses, regardless of when. That is
    what a crowding count needs — how many trains share a stretch of line,
    not whether they are there simultaneously.
    """
    covered: set = set()
    for edge in _schedule_edges(env, graph, schedule, start_heading):
        covered.update(edge.path)
    return covered


def edge_time_windows(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedule: TrainSchedule,
    start_heading: Optional[int] = None,
) -> List[Tuple[object, float, float]]:
    """Per traversed edge, the planned `(edge, enter, exit)` time window.

    Open-loop timing: the train departs at its earliest departure, sits out
    each scheduled wait at the node before moving on, and crosses an edge in
    its travel time. No interaction with other trains — this is what the
    *plan* claims will happen, which is exactly the input the evaluator gets.
    """
    agent = env.agents[schedule.handle]
    clock = float(getattr(agent, "earliest_departure", 0) or 0)
    windows: List[Tuple[object, float, float]] = []
    for index, edge in enumerate(
        _schedule_edges(env, graph, schedule, start_heading)
    ):
        clock += schedule.entries[index].wait
        windows.append((edge, clock, clock + edge.travel_time))
        clock += edge.travel_time
    return windows


def _headings_for(
    env: RailEnv,
    schedules: Sequence[TrainSchedule],
    start_headings: Optional[Sequence[Optional[int]]],
) -> List[Optional[int]]:
    """Per-schedule starting heading, defaulting to each train's origin."""
    if start_headings is None:
        return [None] * len(schedules)
    if len(start_headings) != len(schedules):
        raise ValueError(
            f"got {len(start_headings)} start headings for "
            f"{len(schedules)} schedules; they are positional"
        )
    return list(start_headings)


def edge_peak_occupancy(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedules: Sequence[TrainSchedule],
    start_headings: Optional[Sequence[Optional[int]]] = None,
) -> List[int]:
    """Per edge, the peak number of trains planned to be on it at once.

    The time-aware complement to `edge_train_counts`: two trains using the
    same section an hour apart share track but never contest it, so the
    spatial count alone overstates congestion. A train occupies an edge's
    section during the hull of its windows over every traversed edge that
    shares cells with it; the peak is the maximum number of simultaneously
    open windows. Aligned with `graph.edges` order.

    `start_headings` is one heading per schedule (see `_schedule_edges`);
    without it every schedule is assumed to start at its train's origin,
    which silently under-counts schedules that do not.
    """
    headings = _headings_for(env, schedules, start_headings)
    traversals = []
    for schedule, heading in zip(schedules, headings):
        windows = edge_time_windows(env, graph, schedule, heading)
        traversals.append([(set(e.path), t0, t1) for e, t0, t1 in windows])

    peaks: List[int] = []
    for edge in graph.edges:
        section = set(edge.path)
        spans: List[Tuple[float, float]] = []
        for train in traversals:
            hits = [(t0, t1) for cells, t0, t1 in train if cells & section]
            if hits:
                spans.append((min(t for t, _ in hits), max(t for _, t in hits)))
        # Sweep; a departure and an arrival at the same instant do not clash.
        events = sorted(
            [(t0, 1) for t0, _ in spans] + [(t1, -1) for _, t1 in spans],
            key=lambda event: (event[0], event[1]),
        )
        peak = current = 0
        for _, delta in events:
            current += delta
            peak = max(peak, current)
        peaks.append(peak)
    return peaks


def edge_train_counts(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedules: Sequence[TrainSchedule],
    start_headings: Optional[Sequence[Optional[int]]] = None,
) -> List[int]:
    """Per edge, how many trains route over at least one of its cells.

    A congestion map: an edge shared by several trains' routes sits in a
    contested area, whether or not the conflict actually fires. Aligned with
    `graph.edges` order. See `edge_peak_occupancy` for `start_headings`.
    """
    headings = _headings_for(env, schedules, start_headings)
    coverage = [
        _schedule_cells(env, graph, s, h) for s, h in zip(schedules, headings)
    ]
    counts: List[int] = []
    for edge in graph.edges:
        section = set(edge.path)
        counts.append(sum(1 for cells in coverage if cells & section))
    return counts


def schedules_from_avoidance_policy(
    layout: Layout,
    number_of_agents: int,
    graph: DecisionPointGraph,
    base_schedules: Sequence[TrainSchedule],
    reference_env: RailEnv,
) -> Optional[List[TrainSchedule]]:
    """Holds taken from the repo's `DeadLockAvoidancePolicy`.

    The policy is reactive — it follows the shortest path and stops a train
    rather than let it run into an occupied conflict — so running it on a
    fresh copy of the same scenario reveals *where* trains should give way.
    Each stalled step is charged to the last decision node the train passed,
    which is also the operationally sensible place to hold: at a signal in
    front of the conflict, not in the middle of a block.
    """
    env = build_layout_env(layout, number_of_agents)
    policy = DeadLockAvoidancePolicy()
    try:
        policy.reset(env)
    except Exception:
        return None

    owners = [
        _node_of_cell(reference_env, graph, schedule, schedule.handle)
        for schedule in base_schedules
    ]
    holds: List[Dict[int, int]] = [{} for _ in base_schedules]
    previous: Dict[int, Optional[Tuple[int, int]]] = {}

    handles = list(range(len(env.agents)))
    limit = int(getattr(env, "_max_episode_steps", 0) or 200)
    for _ in range(limit):
        policy.start_step(train=False)
        actions = policy.act_many(handles, None)
        env.step(actions)
        stop = True
        for handle in handles:
            agent = env.agents[handle]
            if agent.state == TrainState.DONE:
                continue
            stop = False
            if agent.position is None:
                continue
            cell = (int(agent.position[0]), int(agent.position[1]))
            if previous.get(handle) == cell and handle < len(holds):
                index = owners[handle].get(cell)
                if index is not None:
                    holds[handle][index] = holds[handle].get(index, 0) + 1
            previous[handle] = cell
        if stop:
            break

    out: List[TrainSchedule] = []
    for schedule, hold in zip(base_schedules, holds):
        out.append(TrainSchedule(
            handle=schedule.handle,
            entries=[
                ScheduleEntry(entry.node_id, hold.get(index, 0))
                for index, entry in enumerate(schedule.entries)
            ],
        ))
    return out


def perturb_waits(
    schedules: Sequence[TrainSchedule],
    rng: random.Random,
    probability: float = 0.25,
    max_wait: int = 12,
) -> List[TrainSchedule]:
    """Layer random holds on top of a plan, degrading it in varied ways."""
    return [
        TrainSchedule(
            handle=schedule.handle,
            entries=[
                ScheduleEntry(
                    entry.node_id,
                    entry.wait + (rng.randint(1, max_wait)
                                  if rng.random() < probability else 0),
                )
                for entry in schedule.entries
            ],
        )
        for schedule in schedules
    ]


def _horizon(env: RailEnv) -> float:
    """Steps available in the episode — the unit for every duration."""
    return float(getattr(env, "_max_episode_steps", 0) or 100)


def encode_graph(
    env: RailEnv, graph: DecisionPointGraph
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, Dict[int, int]]:
    """Encode the decision-point graph as node features and an edge list.

    Returns the five graph tensors plus the mapping from the schedule's
    global node ids to local indices in those tensors. Node features are
    structural (what kind of node, how it connects, where it sits); edges
    carry their travel time, which is what makes a node's position in the
    network meaningful to the encoder.
    """
    ordered = sorted(graph.nodes)
    if len(ordered) > MAX_NODES:
        raise ValueError(
            f"{len(ordered)} nodes exceeds MAX_NODES={MAX_NODES}; "
            "raise the cap rather than truncating the network"
        )
    local = {graph.nodes[cell].node_id: index for index, cell in enumerate(ordered)}
    index_of_cell = {cell: index for index, cell in enumerate(ordered)}
    horizon = _horizon(env)

    out_degree: Dict[Tuple[int, int], int] = {}
    in_degree: Dict[Tuple[int, int], int] = {}
    for edge in graph.edges:
        out_degree[edge.from_cell] = out_degree.get(edge.from_cell, 0) + 1
        in_degree[edge.to_cell] = in_degree.get(edge.to_cell, 0) + 1

    nodes = np.zeros((MAX_NODES, NODE_FEATURES), dtype=np.float32)
    node_mask = np.zeros((MAX_NODES,), dtype=np.float32)
    scale = float(max(env.width, env.height))
    for index, cell in enumerate(ordered):
        node = graph.nodes[cell]
        nodes[index] = (
            1.0 if "station" in node.kinds else 0.0,
            1.0 if "switch_decision" in node.kinds else 0.0,
            out_degree.get(cell, 0) / DEGREE_SCALE,
            in_degree.get(cell, 0) / DEGREE_SCALE,
            len(node.approaches) / APPROACH_SCALE,
            cell[0] / scale,
            cell[1] / scale,
        )
        node_mask[index] = 1.0

    if len(graph.edges) > MAX_EDGES:
        raise ValueError(
            f"{len(graph.edges)} edges exceeds MAX_EDGES={MAX_EDGES}; "
            "raise the cap rather than truncating the network"
        )
    edge_index = np.zeros((MAX_EDGES, 2), dtype=np.int64)
    edge_features = np.zeros((MAX_EDGES, EDGE_FEATURES), dtype=np.float32)
    edge_mask = np.zeros((MAX_EDGES,), dtype=np.float32)
    has_alternative = graph.edges_have_alternative_route()
    for position, edge in enumerate(graph.edges):
        edge_index[position] = (
            index_of_cell[edge.from_cell],
            index_of_cell[edge.to_cell],
        )
        # Structural edge columns 0..2. Columns 3-4 (crowding and peak
        # occupancy) are schedule dependent and left zero here;
        # encode_sample fills them.
        #  0 linear travel time — comparable with deadlines and waits;
        #  1 log travel time — resolution at the short end where nearly all
        #    edges live (median 2 steps, max 90);
        #  2 has-alternative-route — can a train reroute around a block here.
        edge_features[position, :STRUCTURAL_EDGE_FEATURES] = (
            edge.travel_time / horizon,
            float(np.log1p(edge.travel_time) / np.log1p(LOG_TIME_REFERENCE)),
            1.0 if has_alternative[position] else 0.0,
        )
        edge_mask[position] = 1.0

    return nodes, node_mask, edge_index, edge_features, edge_mask, local


def encode_sample(
    env: RailEnv,
    graph: DecisionPointGraph,
    layout_index: int,
    schedules: Sequence[TrainSchedule],
    result: Optional[RolloutResult] = None,
    source: str = "shortest_path",
    start_headings: Optional[Sequence[Optional[int]]] = None,
) -> Sample:
    """Encode the infrastructure and the schedules running on it.

    Schedules reference nodes by *local* index into this scenario's graph,
    so the model resolves a node through the graph it was given rather than
    through a global table that would mean different things on different
    networks.

    `start_headings` is one heading per schedule, for schedules that do not
    begin at their train's origin (see `_schedule_edges`).
    """
    (
        graph_nodes, graph_node_mask, edge_index, edge_features, edge_mask, local
    ) = encode_graph(env, graph)

    if len(schedules) > MAX_TRAINS:
        raise ValueError(
            f"{len(schedules)} trains exceeds MAX_TRAINS={MAX_TRAINS}; "
            "raise the cap rather than dropping trains silently"
        )

    headings = _headings_for(env, schedules, start_headings)

    # Crowding: how many trains route over each edge (column 3) and how many
    # of those are planned to be on it at the same time (column 4), so the
    # graph encoder can propagate "this area is contested" — and *when* it
    # is — into the node embeddings.
    for position, count in enumerate(
        edge_train_counts(env, graph, schedules, headings)
    ):
        edge_features[position, STRUCTURAL_EDGE_FEATURES] = count / CROWD_SCALE
    for position, peak in enumerate(
        edge_peak_occupancy(env, graph, schedules, headings)
    ):
        edge_features[position, STRUCTURAL_EDGE_FEATURES + 1] = peak / CROWD_SCALE

    schedule_nodes = np.zeros((MAX_TRAINS, MAX_SCHEDULE_NODES), dtype=np.int64)
    waits = np.zeros((MAX_TRAINS, MAX_SCHEDULE_NODES), dtype=np.float32)
    node_mask = np.zeros((MAX_TRAINS, MAX_SCHEDULE_NODES), dtype=np.float32)
    stop_flags = np.zeros(
        (MAX_TRAINS, MAX_SCHEDULE_NODES, STOP_FLAGS), dtype=np.float32
    )
    scalars = np.zeros((MAX_TRAINS, TRAIN_SCALARS), dtype=np.float32)
    train_mask = np.zeros((MAX_TRAINS,), dtype=np.float32)

    horizon = _horizon(env)

    for row, (schedule, heading) in enumerate(zip(schedules, headings)):
        entries = schedule.entries
        if len(entries) > MAX_SCHEDULE_NODES:
            raise ValueError(
                f"schedule with {len(entries)} nodes exceeds "
                f"MAX_SCHEDULE_NODES={MAX_SCHEDULE_NODES}"
            )
        agent = env.agents[schedule.handle]
        # The cities this train is booked to call at, and which one ends its
        # run. Only the terminus stops the train, so the two are flagged
        # separately rather than lumped together as "a stop".
        stops = line_stops(env, schedule.handle)
        scheduled_cells = set(stops[1:])
        terminus = stops[-1]
        for column, entry in enumerate(entries):
            if entry.node_id not in local:
                raise ValueError(
                    f"schedule references node {entry.node_id}, which is not "
                    "in the graph it was encoded with"
                )
            schedule_nodes[row, column] = local[entry.node_id]
            waits[row, column] = entry.wait / horizon
            node_mask[row, column] = 1.0
            cell = graph.cell_of(entry.node_id)
            last = column == len(entries) - 1
            stop_flags[row, column, 0] = 1.0 if cell in scheduled_cells else 0.0
            stop_flags[row, column, 1] = 1.0 if (cell == terminus and last) else 0.0

        # Timetable plus how the plan sits inside it. Slack — the buffer
        # between what the plan needs and what the timetable allows — is the
        # single number that separates a tight plan from a comfortable one,
        # and can go negative when the plan cannot make its deadline. All
        # durations are fractions of the horizon, like every other time.
        total_wait = float(sum(e.wait for e in entries))
        departure = float(getattr(agent, "earliest_departure", 0) or 0)
        deadline = float(getattr(agent, "latest_arrival", horizon) or horizon)
        planned_duration = total_wait + float(
            sum(e.travel_time
                for e in _schedule_edges(env, graph, schedule, heading))
        )
        scalars[row] = (
            departure / horizon,
            deadline / horizon,
            planned_duration / horizon,
            (deadline - departure - planned_duration) / horizon,
            total_wait / horizon,
        )
        train_mask[row] = 1.0

    return Sample(
        graph_nodes=graph_nodes,
        graph_node_mask=graph_node_mask,
        edge_index=edge_index,
        edge_features=edge_features,
        edge_mask=edge_mask,
        schedule_nodes=schedule_nodes,
        waits=waits,
        node_mask=node_mask,
        stop_flags=stop_flags,
        train_scalars=scalars,
        train_mask=train_mask,
        layout=int(layout_index),
        all_arrived=float(result.all_arrived) if result else 0.0,
        bucket=int(result.bucket) if result else 0,
        total_delay=int(result.total_delay) if result else 0,
        source=source,
    )


def encode_connections(
    env: RailEnv,
    graph: DecisionPointGraph,
    stations: Sequence,
    outcomes: Sequence,
    local: Dict[int, int],
    handle_rows: Dict[int, int],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """One row per judged connection: features, who it joins, and the label.

    `local` maps graph node ids to their index in the encoded graph, and
    `handle_rows` maps train handles to their row in the per-train tensors,
    so a connection token can point at the trains and station it relates
    without repeating their features.

    A station is represented by the graph node of the platform its *feeder*
    was booked onto — every platform of a city is a node, and the feeder's
    is the one the transfer would happen at.
    """
    features = np.zeros((MAX_CONNECTIONS, CONNECTION_FEATURES), dtype=np.float32)
    index = np.zeros((MAX_CONNECTIONS, 3), dtype=np.int64)
    kept = np.zeros((MAX_CONNECTIONS,), dtype=np.float32)
    mask = np.zeros((MAX_CONNECTIONS,), dtype=np.float32)
    if not outcomes:
        return features, index, kept, mask

    if len(outcomes) > MAX_CONNECTIONS:
        raise ValueError(
            f"{len(outcomes)} connections exceeds "
            f"MAX_CONNECTIONS={MAX_CONNECTIONS}; raise the cap rather than "
            "dropping transfers silently"
        )

    horizon = _horizon(env)
    by_id = {station.id: station for station in stations}
    calls = {
        (call.handle, call.station_id): call
        for call in station_calls(env, stations)
    }

    row = 0
    for outcome in outcomes:
        connection = outcome.connection
        feeder_row = handle_rows.get(connection.feeder)
        connector_row = handle_rows.get(connection.connector)
        if feeder_row is None or connector_row is None:
            continue
        call = calls.get((connection.feeder, connection.station_id))
        station = by_id.get(connection.station_id)
        if call is None or station is None:
            continue
        node = graph.nodes.get(call.cell)
        if node is None or node.node_id not in local:
            continue
        connector_call = calls.get((connection.connector, connection.station_id))
        features[row] = (
            connection.planned_gap / horizon,
            call.time / horizon,
            (connector_call.time if connector_call else call.time) / horizon,
        )
        index[row] = (feeder_row, connector_row, local[node.node_id])
        kept[row] = 1.0 if outcome.kept else 0.0
        mask[row] = 1.0
        row += 1
    return features, index, kept, mask


def generate_samples_report(
    count: int,
    seed: int = 0,
    layouts: Optional[Sequence[Layout]] = None,
    mix: ScenarioMix = TRAINING_MIX,
    verbose: bool = False,
) -> Tuple[List[Sample], Dict[str, int]]:
    """Generate labelled samples, plus a breakdown of what was skipped.

    With `layouts=None` (the default) each scenario is built on a brand new
    network, so the model can never see the same infrastructure twice.
    Problem size varies twice over: networks differ in grid size and city
    count, and each scenario draws its own number of trains.

    A scenario that cannot be built, planned, run or encoded is dropped and
    another drawn. The reasons are counted rather than swallowed because
    they are not interchangeable: `plan` and `rollout` failures are a
    property of the scenario, but an `encode` or `connections` failure means
    the scenario exceeded a tensor cap — and since the scenarios that do
    that are the largest and busiest, silently dropping them would quietly
    shave the hard tail off a set built specifically to contain it.
    """
    rng = random.Random(seed)
    pool = list(layouts) if layouts else None
    samples: List[Sample] = []
    skipped: Dict[str, int] = {}
    attempts = 0

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    while len(samples) < count and attempts < count * 6:
        attempts += 1
        if pool is None:
            # A network of its own for this scenario, never reused.
            layout = Layout(
                index=attempts,
                seed=rng.randint(*mix.seed_range),
                size=rng.choice(mix.sizes),
                cities=rng.choice(mix.cities),
                line_length=mix.line_length,
            )
        else:
            layout = rng.choice(pool)
        number_of_agents = rng.randint(mix.min_trains, mix.max_trains)
        try:
            env = build_layout_env(layout, number_of_agents)
            graph = build_decision_point_graph(env)
            stations = resolve_stations(env)
            # Multi-stop lines: the train calls at every city on its line,
            # which is what makes a connection expressible at all.
            base = plan_all_lines(env, graph)
        except Exception:
            skip("build")
            continue
        if base is None:
            skip("plan")
            continue

        # Three schedule styles in roughly equal measure. None of them
        # dominates (see the module docstring), so the mix is about giving
        # the evaluator different *kinds* of plan to tell apart.
        source = rng.choice(("shortest_path", "avoidance", "overlap_plan"))
        schedules = base
        if source == "avoidance":
            avoided = schedules_from_avoidance_policy(
                layout, number_of_agents, graph, base, env
            )
            if avoided is None:
                skip("avoidance")
                continue
            schedules = avoided
        elif source == "overlap_plan":
            schedules = plan_avoiding_overlaps(
                env, graph, base, safety=1, max_total_wait=10
            )
        if rng.random() < 0.5:
            schedules = perturb_waits(schedules, rng)
            source += "+noise"

        try:
            sample = encode_sample(env, graph, layout.index, schedules, source=source)
        except Exception:
            skip("encode")
            continue
        sample.mix = mix.name
        try:
            connections = planned_connections(env, stations)
            result = run_schedules(
                env, graph, schedules,
                watch_cells=station_watch_cells(stations),
            )
            report = evaluate_connections(
                connections, observed_times(stations, result.occupancy)
            )
        except Exception:
            skip("rollout")
            continue

        sample.all_arrived = float(result.all_arrived)
        sample.bucket = int(result.bucket)
        sample.total_delay = int(result.total_delay)
        sample.connections_total = int(report.total)
        sample.connections_kept = int(report.kept)
        try:
            ordered = sorted(graph.nodes)
            local = {graph.nodes[c].node_id: i for i, c in enumerate(ordered)}
            rows = {s.handle: r for r, s in enumerate(schedules)}
            (sample.connection_features, sample.connection_index,
             sample.connection_kept, sample.connection_mask) = encode_connections(
                env, graph, stations, report.outcomes, local, rows)
        except Exception:
            skip("connections")
            continue
        samples.append(sample)

    if verbose and skipped:
        detail = ", ".join(f"{k} {v}" for k, v in sorted(skipped.items()))
        print(f"  skipped {sum(skipped.values())} scenarios ({detail})")
    return samples, skipped


def generate_samples(
    count: int,
    seed: int = 0,
    layouts: Optional[Sequence[Layout]] = None,
    mix: ScenarioMix = TRAINING_MIX,
    verbose: bool = False,
) -> List[Sample]:
    """Generate labelled samples; see `generate_samples_report`."""
    return generate_samples_report(
        count, seed=seed, layouts=layouts, mix=mix, verbose=verbose
    )[0]


def _generate_chunk(
    job: Tuple[int, int, ScenarioMix]
) -> Tuple[List[Sample], Dict[str, int]]:
    """One worker's share. Top level so it can be pickled to a subprocess."""
    count, seed, mix = job
    return generate_samples_report(count, seed=seed, mix=mix)


def generate_samples_parallel_report(
    count: int,
    seed: int = 0,
    workers: Optional[int] = None,
    chunk_size: int = 100,
    mix: ScenarioMix = TRAINING_MIX,
    verbose: bool = False,
) -> Tuple[List[Sample], Dict[str, int]]:
    """Generate in short-lived worker processes.

    Building a Flatland env is expensive in memory in a way that does not
    come back: rail generation, A*, and the distance map allocate millions
    of small objects, and freeing them leaves fragmented allocator arenas
    rather than memory the OS can reuse. Measured at ~5 MB retained per
    scenario, so a 36k-scenario dataset would need well over 100 GB in one
    process — it drove this machine into swap at 12k.

    A process that exits returns everything, so each chunk runs in a worker
    that is recycled afterwards (`maxtasksperchild=1`). Only the encoded
    samples — ~19 KB each — cross back to the parent. Generation is
    CPU-bound and independent per scenario, so this also parallelises it.

    Deterministic, but *not* the same stream as `generate_samples(count,
    seed)`: chunk *i* runs its own generator seeded from `seed`, so the same
    arguments give the same dataset while different chunking does not.
    """
    import multiprocessing as mp

    if workers is None:
        workers = max(1, min(4, (os.cpu_count() or 2) - 2))
    jobs = []
    remaining, index = count, 0
    while remaining > 0:
        jobs.append((min(chunk_size, remaining), seed * 1_000_003 + index, mix))
        remaining -= jobs[-1][0]
        index += 1

    samples: List[Sample] = []
    skipped: Dict[str, int] = {}
    # 'spawn' keeps workers from inheriting the parent's heap, which is the
    # point of using them at all.
    context = mp.get_context("spawn")
    with context.Pool(processes=workers, maxtasksperchild=1) as pool:
        for done, (chunk, chunk_skips) in enumerate(
            pool.imap_unordered(_generate_chunk, jobs), 1
        ):
            samples.extend(chunk)
            for reason, hits in chunk_skips.items():
                skipped[reason] = skipped.get(reason, 0) + hits
            if verbose and (done % 10 == 0 or done == len(jobs)):
                print(f"  {len(samples)}/{count} scenarios "
                      f"({done}/{len(jobs)} chunks)", flush=True)
    if verbose and skipped:
        detail = ", ".join(f"{k} {v}" for k, v in sorted(skipped.items()))
        print(f"  skipped {sum(skipped.values())} scenarios ({detail})", flush=True)
    return samples[:count], skipped


def generate_samples_parallel(
    count: int,
    seed: int = 0,
    workers: Optional[int] = None,
    chunk_size: int = 100,
    mix: ScenarioMix = TRAINING_MIX,
    verbose: bool = False,
) -> List[Sample]:
    """Generate in worker processes; see `generate_samples_parallel_report`."""
    return generate_samples_parallel_report(
        count, seed=seed, workers=workers, chunk_size=chunk_size,
        mix=mix, verbose=verbose,
    )[0]


def save_samples(path: str, samples: Sequence[Sample]) -> str:
    """Cache a generated dataset so training can resume without rebuilding it.

    Generating 12k scenarios means running 12k Flatland episodes; continuing
    a training run must not pay that again, and must train on exactly the
    same data or the validation split would shift under it.
    """
    stacked = stack_samples(samples)
    np.savez_compressed(
        path,
        graph_nodes=stacked[0],
        graph_node_mask=stacked[1],
        edge_index=stacked[2],
        edge_features=stacked[3],
        edge_mask=stacked[4],
        schedule_nodes=stacked[5],
        waits=stacked[6],
        node_mask=stacked[7],
        stop_flags=stacked[8],
        train_scalars=stacked[9],
        train_mask=stacked[10],
        all_arrived=stacked[11],
        bucket=stacked[12],
        layout=np.array([s.layout for s in samples], dtype=np.int64),
        total_delay=np.array([s.total_delay for s in samples], dtype=np.int64),
        connections_total=np.array(
            [s.connections_total for s in samples], dtype=np.int64),
        connections_kept=np.array(
            [s.connections_kept for s in samples], dtype=np.int64),
        connection_features=stacked[14],
        connection_index=stacked[15],
        connection_kept=stacked[16],
        connection_mask=stacked[17],
        source=np.array([s.source for s in samples]),
        mix=np.array([s.mix for s in samples]),
    )
    return path


def load_samples(path: str) -> List[Sample]:
    """Restore a cached dataset written by `save_samples`.

    The arrays are pulled out of the archive *once*, before the loop.
    `np.load` returns a lazy `NpzFile` whose `[key]` decompresses the whole
    array on every access, so indexing it per sample would decompress each
    full array once per sample — 30k samples across 14 keys is ~420k
    decompressions of ~775 MB of data, which is slow enough to look like a
    hang and enough allocator churn to exhaust memory.
    """
    with np.load(path, allow_pickle=False) as archive:
        data = {key: archive[key] for key in archive.files}
    # Caches written before mixes were nameable hold only the training
    # distribution, which is what that name means.
    mixes = data.get("mix")
    # Caches written before the per-connection block existed load with the
    # fields absent — `stack_samples` already reads that as "no
    # connections", so loading must not refuse what stacking accepts.
    connections = data.get("connection_features")
    return [
        Sample(
            graph_nodes=data["graph_nodes"][i],
            graph_node_mask=data["graph_node_mask"][i],
            edge_index=data["edge_index"][i],
            edge_features=data["edge_features"][i],
            edge_mask=data["edge_mask"][i],
            schedule_nodes=data["schedule_nodes"][i],
            waits=data["waits"][i],
            node_mask=data["node_mask"][i],
            stop_flags=data["stop_flags"][i],
            train_scalars=data["train_scalars"][i],
            train_mask=data["train_mask"][i],
            layout=int(data["layout"][i]),
            all_arrived=float(data["all_arrived"][i]),
            bucket=int(data["bucket"][i]),
            total_delay=int(data["total_delay"][i]),
            connections_total=int(data["connections_total"][i]),
            connections_kept=int(data["connections_kept"][i]),
            connection_features=None if connections is None else connections[i],
            connection_index=(
                None if connections is None else data["connection_index"][i]),
            connection_kept=(
                None if connections is None else data["connection_kept"][i]),
            connection_mask=(
                None if connections is None else data["connection_mask"][i]),
            source=str(data["source"][i]),
            mix="training" if mixes is None else str(mixes[i]),
        )
        for i in range(len(data["bucket"]))
    ]


def stack_samples(samples: Sequence[Sample]):
    """Batch samples into the model's inputs followed by the three targets:
    graph_nodes, graph_node_mask, edge_index, edge_features, edge_mask,
    schedule_nodes, waits, node_mask, stop_flags, train_scalars, train_mask,
    then all_arrived, bucket, connections_kept_ratio, and finally the
    per-connection block (features, index, kept, mask) used by the
    connection model. A sample generated before those existed pads to
    zeros with an all-zero mask, which reads as "no connections"."""
    return (
        np.stack([s.graph_nodes for s in samples]),
        np.stack([s.graph_node_mask for s in samples]),
        np.stack([s.edge_index for s in samples]),
        np.stack([s.edge_features for s in samples]),
        np.stack([s.edge_mask for s in samples]),
        np.stack([s.schedule_nodes for s in samples]),
        np.stack([s.waits for s in samples]),
        np.stack([s.node_mask for s in samples]),
        np.stack([s.stop_flags for s in samples]),
        np.stack([s.train_scalars for s in samples]),
        np.stack([s.train_mask for s in samples]),
        np.array([s.all_arrived for s in samples], dtype=np.float32),
        np.array([s.bucket for s in samples], dtype=np.int64),
        np.array([s.connections_kept_ratio for s in samples], dtype=np.float32),
        np.stack([_connection_block(s)[0] for s in samples]),
        np.stack([_connection_block(s)[1] for s in samples]),
        np.stack([_connection_block(s)[2] for s in samples]),
        np.stack([_connection_block(s)[3] for s in samples]),
    )


def _connection_block(sample: "Sample"):
    """The four per-connection arrays, zero-filled when absent.

    Older caches predate these fields; an all-zero mask means "no
    connections", which every consumer already handles.
    """
    features = sample.connection_features
    if features is None:
        features = np.zeros((MAX_CONNECTIONS, CONNECTION_FEATURES), dtype=np.float32)
    index = sample.connection_index
    if index is None:
        index = np.zeros((MAX_CONNECTIONS, 3), dtype=np.int64)
    kept = sample.connection_kept
    if kept is None:
        kept = np.zeros((MAX_CONNECTIONS,), dtype=np.float32)
    mask = sample.connection_mask
    if mask is None:
        mask = np.zeros((MAX_CONNECTIONS,), dtype=np.float32)
    return features, index, kept, mask


__all__ = [
    "APPROACH_SCALE",
    "DEGREE_SCALE",
    "CONNECTION_FEATURES",
    "EDGE_FEATURES",
    "MAX_CONNECTIONS",
    "MAX_EDGES",
    "MAX_NODES",
    "MAX_SCHEDULE_NODES",
    "NODE_FEATURES",
    "STOP_FLAGS",
    "MAX_TRAINS",
    "NUM_DELAY_BUCKETS",
    "EVAL_MIXES",
    "EVAL_SEED_RANGE",
    "NUM_LAYOUTS",
    "TRAIN_SCALARS",
    "TRAINING_MIX",
    "Layout",
    "Sample",
    "ScenarioMix",
    "build_layout_env",
    "default_layouts",
    "edge_peak_occupancy",
    "edge_time_windows",
    "edge_train_counts",
    "encode_graph",
    "load_samples",
    "save_samples",
    "encode_connections",
    "encode_sample",
    "generate_samples",
    "generate_samples_parallel",
    "generate_samples_parallel_report",
    "generate_samples_report",
    "perturb_waits",
    "plan_all_lines",
    "plan_all_trains",
    "schedules_from_avoidance_policy",
    "start_heading_of",
    "stack_samples",
]
