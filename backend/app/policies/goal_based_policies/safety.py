"""How safe a set of schedules is — static robustness, no rollout.

`run_schedules` measures how a plan *performs*; this measures how much it
can absorb. A plan can be perfectly on time and still be a house of cards:
no slack anywhere, opposing trains threading a single-track corridor
minutes apart, the whole fleet coupled into one delay-domino line.

Four components, each a survival probability in [0, 1]:

- **slack** — can each train absorb a disturbance to itself. A train's
  buffer is `latest_arrival` minus its planned arrival; fragility decays
  exponentially in that buffer. Aggregated as a product, so one
  zero-slack train caps the score no matter how comfortable the rest are.
- **deadlock** — can one delay make the plan unrecoverable. Trains cannot
  reverse, so two trains meeting head-on inside a stretch of track with
  no node between them is terminal. Every opposing pair of planned runs
  over shared cells is scored by the gap between one train clearing the
  stretch and the other entering it, discounted where rerouting exists.
- **track** — how many trains one blockage catches. Per shared cell, the
  most trains whose planned presence intersects any blockage window of
  `params.window` minutes; scored per contiguous shared stretch so a long
  corridor is one resource, not one resource per cell.
- **cascade** — how far a delay spreads. Trains are coupled wherever one
  needs a cell shortly after another clears it; a reference disturbance
  of `params.delta` minutes is propagated along those couplings,
  shrinking by the follow-gap at each hop.

The composite is the product of the four — uniform on purpose, so any
single catastrophic element (a zero-slack train, a two-minute opposing
meet, a fleet-wide cascade) tanks the headline number.

Everything works on shared *cells*, never on shared graph edges: switch
wait-cells are directional, so the two directions over one physical track
run between different nodes and their edges' cell paths overlap without
ever being equal. Grouping by edge identity finds no opposing traffic at
all on real networks — measured, not hypothetical.

Everything reads the *planned* timeline (`edge_time_windows`), never a
rollout: the score is exposure under naive replay. The reactive layer
(deadlock-avoidance policy, `SchedulePlayer` holding at blocked cells)
may catch some of these at runtime — a plan that depends on that safety
net is exactly what should score as unsafe. Parameter defaults are
hand-picked; calibrating them against malfunction rollouts is the
follow-up step, which is why they all sit in one `SafetyParams`.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import asdict, dataclass, field
from typing import Dict, FrozenSet, Iterator, List, Optional, Sequence, Tuple

from flatland.envs.rail_env import RailEnv

from app.policies.goal_based_policies.infrastructure_graph import (
    Cell,
    DecisionPointGraph,
    GraphEdge,
)
from app.policies.goal_based_policies.schedule import (
    TrainSchedule,
    edge_time_windows,
)


@dataclass(frozen=True)
class SafetyParams:
    """Free parameters of the measure, in one place for later calibration."""
    tau_slack: float = 5.0      # minutes a typical disturbance costs a train
    p_disturb: float = 0.3      # chance a disturbance hits a given train at all
    tau_deadlock: float = 10.0  # minutes; matches malfunction duration, not
    #                             tau_slack — a meet faces the full disturbance,
    #                             not what is left of it after terminal slack
    q_deadlock: float = 0.8     # cost of a zero-gap meet; largest q because
    #                             the outcome is terminal, not a delay
    alt_discount: float = 0.5   # meet weight when rerouting around it exists
    window: float = 15.0        # minutes a blockage lasts (track exposure)
    q_track: float = 0.15
    horizon: float = 15.0       # largest follow-gap that still couples trains
    delta: float = 10.0         # reference disturbance for cascade reach
    q_cascade: float = 0.5


@dataclass(frozen=True)
class PlanTimeline:
    """One train's planned movements, resolved to timed graph-edge windows.

    `windows` is `(edge, enter, exit)` per traversed edge: standing on
    `edge.from_cell` at `enter`, on `edge.to_cell` at `exit`. The node
    visits must cover the window endpoints (`build_timelines` does), since
    the per-cell presence is assembled from both. A plan whose node pairs
    cannot all be resolved to edges is `playable=False` and is flagged
    rather than scored — its timing means nothing.
    """
    handle: int
    windows: Tuple[Tuple[GraphEdge, float, float], ...]
    node_visits: Tuple[Tuple[Cell, float, float], ...]
    playable: bool
    planned_arrival: float
    latest_arrival: Optional[float]


@dataclass(frozen=True)
class TrainSafety:
    handle: int
    slack: Optional[float]  # minutes of buffer; None when there is no deadline
    fragility: float        # exp(-slack/tau); 1.0 when the plan is already late
    reach: int              # trains infected when this one is disturbed by delta


@dataclass(frozen=True)
class OpposingMeet:
    """Two trains planned through one stretch of track in opposite directions."""
    first: int              # handle of the train through the stretch first
    second: int
    cells: Tuple[Cell, ...]
    gap: float              # minutes between first clearing and second entering
    has_alternative: bool
    fragility: float        # alt-discounted exp(-gap/tau_deadlock)


@dataclass(frozen=True)
class ResourceLoad:
    """A stretch of track where one blockage catches several trains."""
    cells: Tuple[Cell, ...]
    trains: Tuple[int, ...]
    peak: int               # most trains caught by one window-long blockage
    has_alternative: bool


@dataclass(frozen=True)
class CascadeEdge:
    from_handle: int
    to_handle: int
    headway: float          # minutes between the leader clearing shared
    #                         track and the follower needing it


@dataclass
class SafetyReport:
    safety: float
    slack_score: float
    deadlock_score: float
    track_score: float
    cascade_score: float
    trains: List[TrainSafety]
    meets: List[OpposingMeet]           # most fragile first
    loads: List[ResourceLoad]           # highest peak first
    cascade_edges: List[CascadeEdge]    # tightest headway first
    largest_component: int              # biggest set of mutually coupled trains
    unplayable: Tuple[int, ...]         # handles excluded from scoring
    params: SafetyParams = field(default_factory=SafetyParams)

    def to_dict(self) -> Dict[str, object]:
        return {
            "safety": self.safety,
            "slack_score": self.slack_score,
            "deadlock_score": self.deadlock_score,
            "track_score": self.track_score,
            "cascade_score": self.cascade_score,
            "trains": [
                {
                    "handle": t.handle,
                    "slack": t.slack,
                    "fragility": t.fragility,
                    "reach": t.reach,
                }
                for t in self.trains
            ],
            "meets": [
                {
                    "first": m.first,
                    "second": m.second,
                    "cells": [list(c) for c in m.cells],
                    "gap": m.gap,
                    "has_alternative": m.has_alternative,
                    "fragility": m.fragility,
                }
                for m in self.meets
            ],
            "loads": [
                {
                    "cells": [list(c) for c in load.cells],
                    "trains": list(load.trains),
                    "peak": load.peak,
                    "has_alternative": load.has_alternative,
                }
                for load in self.loads
            ],
            "cascade_edges": [
                {"from": e.from_handle, "to": e.to_handle, "headway": e.headway}
                for e in self.cascade_edges
            ],
            "largest_component": self.largest_component,
            "unplayable": list(self.unplayable),
            "params": asdict(self.params),
        }


def build_timelines(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedules: Sequence[TrainSchedule],
) -> List[PlanTimeline]:
    """Resolve every schedule to its planned edge windows and node visits."""
    timelines: List[PlanTimeline] = []
    for schedule in schedules:
        agent = env.agents[schedule.handle]
        departure = float(getattr(agent, "earliest_departure", 0) or 0)
        windows = edge_time_windows(env, graph, schedule)
        playable = len(windows) == len(schedule.entries) - 1

        # A train stands on a node from arriving there (the previous
        # window's exit) until departing (the next window's enter) — the
        # scheduled wait is exactly that difference.
        visits: List[Tuple[Cell, float, float]] = []
        clock = departure
        for window_edge, enter, exit_ in windows:
            visits.append((window_edge.from_cell, clock, enter))
            clock = exit_
        if playable and windows:
            visits.append((windows[-1][0].to_cell, clock, clock))

        latest = getattr(agent, "latest_arrival", None)
        timelines.append(PlanTimeline(
            handle=schedule.handle,
            windows=tuple((e, float(t0), float(t1)) for e, t0, t1 in windows),
            node_visits=tuple(visits),
            playable=playable,
            planned_arrival=clock,
            latest_arrival=None if latest is None else float(latest),
        ))
    return timelines


def corridor_alternatives(
    graph: DecisionPointGraph,
) -> Dict[FrozenSet[Cell], bool]:
    """Per edge (keyed by its cell set), whether it can be bypassed.

    Depends only on the infrastructure, so callers scoring many schedules
    on one network should compute it once and pass it to `assess_safety`.
    """
    alternatives: Dict[FrozenSet[Cell], bool] = {}
    for edge, has in zip(graph.edges, graph.edges_have_alternative_route()):
        key = frozenset(edge.path)
        alternatives[key] = alternatives.get(key, False) or has
    return alternatives


# One cell of a train's planned drive: (cell, enter, leave, reroutable).
_Presence = Tuple[Cell, float, float, bool]


def _presence(
    timeline: PlanTimeline,
    alternatives: Dict[FrozenSet[Cell], bool],
) -> List[_Presence]:
    """A train's planned drive, cell by cell in time order.

    Node visits carry their holds; an edge's interior cells are crossed at
    one cell per step (stretched uniformly when a slow train widens the
    window). Interior cells remember whether their edge can be bypassed —
    the reroutability input to meets and loads; standing on a node cannot
    be rerouted away, so node cells never carry the flag.
    """
    entries: List[_Presence] = [
        (cell, arrive, depart, False)
        for cell, arrive, depart in timeline.node_visits
    ]
    for edge, enter, exit_ in timeline.windows:
        interior = edge.path[1:-1]
        if not interior:
            continue
        reroutable = alternatives.get(frozenset(edge.path), False)
        step = (exit_ - enter) / (len(edge.path) - 1)
        for offset, cell in enumerate(interior, start=1):
            instant = enter + offset * step
            entries.append((cell, instant, instant, reroutable))
    entries.sort(key=lambda entry: (entry[1], entry[2]))
    return entries


def _shared_runs(
    sequence: List[_Presence], other_cells: FrozenSet[Cell]
) -> Iterator[List[_Presence]]:
    """Maximal contiguous stretches of this drive the other train also uses.

    Contiguity is by drive order: consecutive presence entries are
    consecutive cells of the run, so an index gap means the shared track
    is interrupted — two separate stretches, two separate events.
    """
    current: List[_Presence] = []
    previous = -2
    for index, entry in enumerate(sequence):
        if entry[0] not in other_cells:
            continue
        if index != previous + 1 and current:
            yield current
            current = []
        current.append(entry)
        previous = index
    if current:
        yield current


def _cascade_reach(
    seed: int, adjacency: Dict[int, List[Tuple[int, float]]], delta: float
) -> int:
    """Trains infected when `seed` is disturbed by `delta` minutes.

    A delay shrinks by the follow-gap at each hop and dies at zero.
    Max-relaxation rather than plain BFS because coupling graphs have
    cycles and a train can be reached better via a longer route.
    """
    gained: Dict[int, float] = {seed: delta}
    heap: List[Tuple[float, int]] = [(-delta, seed)]
    while heap:
        negative, train = heapq.heappop(heap)
        if -negative < gained.get(train, 0.0):
            continue
        for follower, headway in adjacency.get(train, ()):
            passed = gained[train] - headway
            if passed > 0 and passed > gained.get(follower, 0.0):
                gained[follower] = passed
                heapq.heappush(heap, (-passed, follower))
    return sum(1 for train in gained if train != seed)


def assess_timelines(
    timelines: Sequence[PlanTimeline],
    alternatives: Dict[FrozenSet[Cell], bool],
    params: SafetyParams = SafetyParams(),
) -> SafetyReport:
    """Score already-resolved timelines. See the module docstring."""
    scored = [t for t in timelines if t.playable]
    unplayable = tuple(t.handle for t in timelines if not t.playable)
    count = len(scored)

    # Slack: exponential fragility per train, survival product overall.
    slack_score = 1.0
    fragilities: Dict[int, float] = {}
    slacks: Dict[int, Optional[float]] = {}
    for timeline in scored:
        if timeline.latest_arrival is None:
            slacks[timeline.handle] = None
            fragilities[timeline.handle] = 0.0
            continue
        slack = timeline.latest_arrival - timeline.planned_arrival
        fragility = math.exp(-max(slack, 0.0) / params.tau_slack)
        slacks[timeline.handle] = slack
        fragilities[timeline.handle] = fragility
        slack_score *= 1.0 - params.p_disturb * fragility

    sequences = {t.handle: _presence(t, alternatives) for t in scored}
    cell_sets = {
        handle: frozenset(entry[0] for entry in sequence)
        for handle, sequence in sequences.items()
    }

    # Meets and couplings come from the same pairwise shared stretches: a
    # stretch driven in opposite directions is a potential deadlock, and
    # either way the later train needs track the earlier one clears.
    meets: List[OpposingMeet] = []
    deadlock_score = 1.0
    tightest: Dict[Tuple[int, int], float] = {}
    handles = sorted(sequences)
    for i, handle_a in enumerate(handles):
        sequence_a = sequences[handle_a]
        for handle_b in handles[i + 1:]:
            shared = cell_sets[handle_a] & cell_sets[handle_b]
            if not shared:
                continue
            position_b: Dict[Cell, int] = {}
            for index, entry in enumerate(sequences[handle_b]):
                position_b.setdefault(entry[0], index)
            for run in _shared_runs(sequence_a, shared):
                cells = tuple(entry[0] for entry in run)
                other = [sequences[handle_b][position_b[c]] for c in cells]
                a_in = min(entry[1] for entry in run)
                a_out = max(entry[2] for entry in run)
                b_in = min(entry[1] for entry in other)
                b_out = max(entry[2] for entry in other)
                # The meet gap is hull-based — deadlock needs the whole
                # stretch cleared. The coupling is cell-wise: a follower
                # trailing a leader down a long stretch overlaps its hull
                # yet still has its real headway at every single cell.
                if a_in <= b_in:
                    first, second = handle_a, handle_b
                    gap = max(0.0, b_in - a_out)
                    follow = min(
                        max(0.0, o[1] - r[2]) for r, o in zip(run, other)
                    )
                else:
                    first, second = handle_b, handle_a
                    gap = max(0.0, a_in - b_out)
                    follow = min(
                        max(0.0, r[1] - o[2]) for r, o in zip(run, other)
                    )
                if follow <= params.horizon:
                    pair = (first, second)
                    if follow < tightest.get(pair, math.inf):
                        tightest[pair] = follow
                opposing = (
                    len(cells) > 1
                    and position_b[cells[0]] > position_b[cells[-1]]
                )
                if not opposing:
                    continue
                reroutable = any(entry[3] for entry in run) or any(
                    entry[3] for entry in other
                )
                weight = params.alt_discount if reroutable else 1.0
                fragility = weight * math.exp(-gap / params.tau_deadlock)
                meets.append(OpposingMeet(
                    first=first, second=second, cells=cells, gap=gap,
                    has_alternative=reroutable, fragility=fragility,
                ))
                deadlock_score *= max(0.0, 1.0 - params.q_deadlock * fragility)
    meets.sort(key=lambda m: -m.fragility)

    # Track: per cell, the most trains one `window`-minute blockage can
    # catch — a blockage starting anywhere in (enter - window, leave]
    # intersects a train's presence, so per train that is an interval and
    # the peak is the most overlapping intervals. Scored per contiguous
    # stretch sharing one train set, so a corridor is one resource and a
    # longer corridor is not penalised more for the same conflict.
    hulls: Dict[Cell, Dict[int, Tuple[float, float]]] = {}
    cell_reroutable: Dict[Cell, bool] = {}
    for handle, sequence in sequences.items():
        for cell, enter, leave, reroutable in sequence:
            per_train = hulls.setdefault(cell, {})
            first, last = per_train.get(handle, (enter, leave))
            per_train[handle] = (min(first, enter), max(last, leave))
            cell_reroutable[cell] = cell_reroutable.get(cell, False) or reroutable

    peaks: Dict[Cell, int] = {}
    for cell, per_train in hulls.items():
        if len(per_train) < 2:
            continue
        events = sorted(
            [(first - params.window, 1) for first, _ in per_train.values()]
            + [(last, -1) for _, last in per_train.values()],
            key=lambda event: (event[0], event[1]),
        )
        peak = current = 0
        for _, delta in events:
            current += delta
            peak = max(peak, current)
        if peak >= 2:
            peaks[cell] = peak

    loads: List[ResourceLoad] = []
    track_score = 1.0
    grouped: Dict[Tuple[int, ...], List[Cell]] = {}
    for cell, peak in peaks.items():
        grouped.setdefault(tuple(sorted(hulls[cell])), []).append(cell)
    for trains, cells in grouped.items():
        # Split along the first train's drive so that spatially separate
        # stretches shared by the same trains stay separate resources.
        order = {
            entry[0]: index
            for index, entry in enumerate(sequences[trains[0]])
        }
        stretches: List[List[Cell]] = []
        for cell in sorted(cells, key=lambda c: order.get(c, -1)):
            if (
                stretches
                and order.get(cell, -1) == order.get(stretches[-1][-1], -2) + 1
            ):
                stretches[-1].append(cell)
            else:
                stretches.append([cell])
        for stretch in stretches:
            peak = max(peaks[cell] for cell in stretch)
            reroutable = any(cell_reroutable[cell] for cell in stretch)
            loads.append(ResourceLoad(
                cells=tuple(stretch), trains=trains, peak=peak,
                has_alternative=reroutable,
            ))
            weight = params.alt_discount if reroutable else 1.0
            track_score *= max(
                0.0,
                1.0 - params.q_track * weight * (peak - 1) / max(count - 1, 1),
            )
    loads.sort(key=lambda load: -load.peak)

    # Cascade: propagate a reference disturbance along the couplings.
    adjacency: Dict[int, List[Tuple[int, float]]] = {}
    for (leader, follower), headway in tightest.items():
        adjacency.setdefault(leader, []).append((follower, headway))
    cascade_edges = sorted(
        (CascadeEdge(leader, follower, headway)
         for (leader, follower), headway in tightest.items()),
        key=lambda e: e.headway,
    )

    reaches = {
        t.handle: _cascade_reach(t.handle, adjacency, params.delta)
        for t in scored
    }
    if count > 1:
        mean_reach = sum(reaches.values()) / count
        cascade_score = max(
            0.0, 1.0 - params.q_cascade * mean_reach / (count - 1)
        )
    else:
        cascade_score = 1.0

    parent: Dict[int, int] = {t.handle: t.handle for t in scored}

    def find(train: int) -> int:
        while parent[train] != train:
            parent[train] = parent[parent[train]]
            train = parent[train]
        return train

    for leader, follower in tightest:
        parent[find(leader)] = find(follower)
    component_sizes: Dict[int, int] = {}
    for train in parent:
        root = find(train)
        component_sizes[root] = component_sizes.get(root, 0) + 1
    largest_component = max(component_sizes.values(), default=0)

    trains = [
        TrainSafety(
            handle=t.handle,
            slack=slacks[t.handle],
            fragility=fragilities[t.handle],
            reach=reaches[t.handle],
        )
        for t in scored
    ]

    return SafetyReport(
        safety=slack_score * deadlock_score * track_score * cascade_score,
        slack_score=slack_score,
        deadlock_score=deadlock_score,
        track_score=track_score,
        cascade_score=cascade_score,
        trains=trains,
        meets=meets,
        loads=loads,
        cascade_edges=cascade_edges,
        largest_component=largest_component,
        unplayable=unplayable,
        params=params,
    )


def assess_safety(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedules: Sequence[TrainSchedule],
    params: SafetyParams = SafetyParams(),
    alternatives: Optional[Dict[FrozenSet[Cell], bool]] = None,
) -> SafetyReport:
    """How much disturbance this plan can absorb — see the module docstring.

    `alternatives` is per-network, not per-plan; pass the result of
    `corridor_alternatives(graph)` when scoring many plans on one network
    to skip recomputing the graph's bypass analysis every time.
    """
    if alternatives is None:
        alternatives = corridor_alternatives(graph)
    return assess_timelines(
        build_timelines(env, graph, schedules), alternatives, params
    )


__all__ = [
    "CascadeEdge",
    "OpposingMeet",
    "PlanTimeline",
    "ResourceLoad",
    "SafetyParams",
    "SafetyReport",
    "TrainSafety",
    "assess_safety",
    "assess_timelines",
    "build_timelines",
    "corridor_alternatives",
]
