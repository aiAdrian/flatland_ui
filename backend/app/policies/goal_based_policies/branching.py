"""Branch generation for the Director's schedule search.

A search state is, per train, the committed *prefix* of its schedule.
This module answers the four questions the search loop asks:

- what does this prefix become if the train just drives on
  (`complete_from` — the completion policy, producing the full candidate
  the ensemble scores);
- where is the next real decision and what can be done there
  (`next_decision` — route alternatives at nodes offering more than one
  feasible way toward the next stop, crossed with the hold menu);
- what is the state after taking an option (`BranchOption.prefix`,
  already advanced through every forced node that follows, so the next
  decision is again a real one);
- is a finished candidate worth scoring at all (`has_planned_overlap` —
  plans that already collide on paper are pruned before any model call).

Decisions exist only at nodes with a genuine route choice; holding
anywhere else is out of scope for v1 (the avoidance planner shows holds
matter elsewhere too — revisit if a sweep says the action space
is too coarse).

**Completion policy: naive chained shortest path**, not Tokener's Hybrid
PP/CBS (the consortium reuse candidate). Rationale:
the completion's job here is a cheap, consistent leaf estimate, the
overlap pruner covers the "plans must not collide" part PP would
contribute, and Tokener plans on the raw Flatland grid rather than our
decision-point graph — an integration wholly out of proportion for this
role. Revisit if a sweep quantifies completion-policy bias.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from flatland.envs.rail_env import RailEnv

from app.policies.goal_based_policies.dataset import (
    MAX_SCHEDULE_NODES,
    edge_time_windows,
)
from app.policies.goal_based_policies.infrastructure_graph import (
    Cell,
    DecisionPointGraph,
    GraphEdge,
)
from app.policies.goal_based_policies.schedule import (
    ScheduleEntry,
    TrainSchedule,
    _feasible,
    line_stops,
    plan_shortest_path_states,
    simulate_occupancy,
)

# Extra minutes a train can be held at a decision node, on top of any
# dwell the stop itself requires. Tracker open decision: tune on the sweep.
WAIT_MENU: Tuple[int, ...] = (0, 1, 3, 5, 10)

# Matches plan_line's default: an intermediate stop counts as served only
# if the train actually stands there.
DWELL = 1

Prefix = Tuple[ScheduleEntry, ...]


@dataclass(frozen=True)
class BranchOption:
    """One way to leave the decision node: hold `wait` extra minutes, take
    `edge`, then drive every forced node after it."""
    wait: int
    edge: GraphEdge
    prefix: Prefix


@dataclass(frozen=True)
class DecisionPoint:
    handle: int
    node_id: int
    time: float          # planned arrival at the node, in steps
    options: Tuple[BranchOption, ...]


def _walk(
    env: RailEnv, graph: DecisionPointGraph, handle: int, prefix: Prefix
) -> Tuple[List[Cell], int, bool]:
    """Resolve a prefix to its cells and the train's final orientation.

    Resolution mirrors `_schedule_edges` exactly — same feasibility check,
    same `(travel_time, out_direction)` tie-break — because a schedule
    stores node ids, and every consumer (encoding, playback, safety) must
    read the same edges out of them. `ok=False` marks a prefix whose node
    pairs cannot all be resolved.
    """
    heading = int(env.agents[handle].initial_direction)
    cells = [graph.cell_of(entry.node_id) for entry in prefix]
    for cell, nxt in zip(cells, cells[1:]):
        usable = [
            e for e in graph.edges_from(cell)
            if e.to_cell == nxt and _feasible(env, cell, heading, e)
        ]
        if not usable:
            return cells, heading, False
        edge = min(usable, key=lambda e: (e.travel_time, e.out_direction))
        heading = edge.in_direction
    return cells, heading, True


def _remaining_stops(
    env: RailEnv, handle: int, prefix_cells: Sequence[Cell]
) -> List[Cell]:
    """The line's stops not yet reached, in calling order. A stop is
    consumed when its cell appears in the prefix — strictly in order, so
    passing a *later* stop's platform while detouring does not serve it."""
    stops = line_stops(env, handle)[1:]  # the origin is departed, not served
    index = 0
    for cell in prefix_cells:
        if index < len(stops) and cell == stops[index]:
            index += 1
    return stops[index:]


def _route_cost(
    env: RailEnv,
    graph: DecisionPointGraph,
    start_cell: Cell,
    heading: int,
    target: Cell,
) -> Optional[int]:
    """Cheapest travel time from standing on `start_cell` oriented
    `heading` to standing on `target` — `plan_shortest_path_states`'s
    search, cost only."""
    if start_cell == target:
        return 0
    if start_cell not in graph.nodes or target not in graph.nodes:
        return None
    start = (start_cell, int(heading))
    best: Dict[Tuple[Cell, int], int] = {start: 0}
    queue: List[Tuple[int, Tuple[Cell, int]]] = [(0, start)]
    while queue:
        cost, state = heapq.heappop(queue)
        if cost > best.get(state, cost):
            continue
        cell, orientation = state
        if cell == target:
            return cost
        for edge in graph.edges_from(cell):
            if not _feasible(env, cell, orientation, edge):
                continue
            nxt = (edge.to_cell, edge.in_direction)
            nxt_cost = cost + edge.travel_time
            if nxt_cost < best.get(nxt, nxt_cost + 1):
                best[nxt] = nxt_cost
                heapq.heappush(queue, (nxt_cost, nxt))
    return None


def route_options(
    env: RailEnv,
    graph: DecisionPointGraph,
    handle: int,
    prefix: Prefix,
    k: int = 3,
) -> List[GraphEdge]:
    """Ways onward from the prefix's end that still reach the next stop,
    cheapest overall route first, at most `k`.

    One option per distinct target node: parallel edges collapse onto the
    edge a node-id schedule resolves to, because offering the other one
    would produce a plan that plays back differently than it was scored.
    """
    cells, heading, ok = _walk(env, graph, handle, prefix)
    if not ok or len(prefix) >= MAX_SCHEDULE_NODES:
        return []
    remaining = _remaining_stops(env, handle, cells)
    if not remaining:
        return []
    target = remaining[0]
    current = cells[-1]

    per_node: Dict[Cell, GraphEdge] = {}
    for edge in graph.edges_from(current):
        if not _feasible(env, current, heading, edge):
            continue
        best = per_node.get(edge.to_cell)
        if best is None or (
            (edge.travel_time, edge.out_direction)
            < (best.travel_time, best.out_direction)
        ):
            per_node[edge.to_cell] = edge
    ranked = []
    for edge in per_node.values():
        tail = _route_cost(env, graph, edge.to_cell, edge.in_direction, target)
        if tail is None:
            continue
        ranked.append((edge.travel_time + tail, edge.out_direction, edge))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [edge for _, _, edge in ranked[:k]]


def _append(
    env: RailEnv,
    graph: DecisionPointGraph,
    handle: int,
    prefix: Prefix,
    prefix_cells: Sequence[Cell],
    edge: GraphEdge,
) -> Prefix:
    """The prefix extended by `edge`'s target node, with the dwell the
    stop itself demands (the search's own holds are added elsewhere)."""
    remaining = _remaining_stops(env, handle, prefix_cells)
    serves_stop = bool(remaining) and edge.to_cell == remaining[0]
    is_terminus = len(remaining) == 1
    wait = DWELL if serves_stop and not is_terminus else 0
    return prefix + (ScheduleEntry(graph.node_id(edge.to_cell), wait),)


def advance_through_forced(
    env: RailEnv, graph: DecisionPointGraph, handle: int, prefix: Prefix
) -> Prefix:
    """Drive on while the train has no real choice — exactly one feasible
    way onward that still reaches the next stop. Stops passed on the way
    get their dwell, exactly as the completion would give it."""
    while len(prefix) < MAX_SCHEDULE_NODES:
        options = route_options(env, graph, handle, prefix, k=2)
        if len(options) != 1:
            break
        cells, _, _ = _walk(env, graph, handle, prefix)
        prefix = _append(env, graph, handle, prefix, cells, options[0])
    return prefix


def initial_prefixes(
    env: RailEnv,
    graph: DecisionPointGraph,
    handles: Optional[Iterable[int]] = None,
) -> Dict[int, Prefix]:
    """Every train committed to its origin only, driven up to its first
    real decision — the state the search starts from."""
    chosen = range(len(env.agents)) if handles is None else handles
    prefixes: Dict[int, Prefix] = {}
    for handle in chosen:
        agent = env.agents[handle]
        origin = (int(agent.initial_position[0]), int(agent.initial_position[1]))
        if origin not in graph.nodes:
            raise ValueError(
                f"train {handle} starts on {origin}, which is not a node — "
                "origins are station cells and stations are nodes"
            )
        seed = (ScheduleEntry(graph.node_id(origin), 0),)
        prefixes[int(handle)] = advance_through_forced(env, graph, handle, seed)
    return prefixes


def is_complete(
    env: RailEnv, graph: DecisionPointGraph, handle: int, prefix: Prefix
) -> bool:
    """Has the prefix served the whole line, terminus included?"""
    cells, _, ok = _walk(env, graph, handle, prefix)
    return ok and not _remaining_stops(env, handle, cells)


def arrival_time(
    env: RailEnv, graph: DecisionPointGraph, handle: int, prefix: Prefix
) -> float:
    """When the plan has the train standing at the prefix's last node."""
    windows = edge_time_windows(
        env, graph, TrainSchedule(handle=handle, entries=list(prefix))
    )
    if windows:
        return float(windows[-1][2])
    return float(getattr(env.agents[handle], "earliest_departure", 0) or 0)


def next_decision(
    env: RailEnv,
    graph: DecisionPointGraph,
    prefixes: Dict[int, Prefix],
    k_routes: int = 3,
    wait_menu: Sequence[int] = WAIT_MENU,
) -> Optional[DecisionPoint]:
    """The earliest open decision across all trains, with its options.

    Chronological: whoever reaches their next choice node first decides
    first, ties broken by handle so the search is deterministic. Trains
    that are complete — or dead-ended, which the completion will surface
    as an unroutable candidate — have nothing to decide and are passed
    over. Returns None when nobody has a decision left.
    """
    pending = []
    for handle in sorted(prefixes):
        prefix = prefixes[handle]
        options = route_options(env, graph, handle, prefix, k=k_routes)
        if not options:
            continue
        pending.append(
            (arrival_time(env, graph, handle, prefix), handle, prefix, options)
        )
    if not pending:
        return None
    time_, handle, prefix, edges = min(pending, key=lambda p: (p[0], p[1]))

    cells, _, _ = _walk(env, graph, handle, prefix)
    current = prefix[-1]
    options: List[BranchOption] = []
    for wait in wait_menu:
        held = prefix[:-1] + (
            ScheduleEntry(current.node_id, current.wait + int(wait)),
        )
        for edge in edges:
            extended = _append(env, graph, handle, held, cells, edge)
            options.append(BranchOption(
                wait=int(wait),
                edge=edge,
                prefix=advance_through_forced(env, graph, handle, extended),
            ))
    return DecisionPoint(
        handle=handle,
        node_id=current.node_id,
        time=time_,
        options=tuple(options),
    )


def complete_from(
    env: RailEnv, graph: DecisionPointGraph, handle: int, prefix: Prefix
) -> Optional[TrainSchedule]:
    """The committed prefix plus the train simply driving on: a shortest
    path per remaining leg, dwell at intermediate stops — with a bare
    origin prefix this reproduces `plan_line` entry for entry. Returns
    None when a leg is unroutable or the schedule outgrows the encoding
    cap: a dead branch, for the caller to prune."""
    cells, heading, ok = _walk(env, graph, handle, prefix)
    if not ok:
        return None
    entries = list(prefix)
    remaining = _remaining_stops(env, handle, cells)
    position = cells[-1]
    for index, target in enumerate(remaining):
        states = plan_shortest_path_states(graph, env, position, heading, target)
        if states is None or len(states) < 2:
            return None
        entries.extend(
            ScheduleEntry(graph.node_id(cell), 0) for cell, _ in states[1:]
        )
        heading = states[-1][1]
        position = target
        if index < len(remaining) - 1 and DWELL > 0:
            entries[-1] = ScheduleEntry(entries[-1].node_id, DWELL)
    if len(entries) > MAX_SCHEDULE_NODES:
        return None
    return TrainSchedule(handle=handle, entries=entries)


def has_planned_overlap(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedules: Sequence[TrainSchedule],
    safety: int = 1,
) -> bool:
    """Do these plans claim a cell at overlapping times? The condition
    `plan_avoiding_overlaps` resolves by holding, as a predicate: such a
    candidate stalls under naive replay, so scoring it wastes a model
    call."""
    reservations: Dict[Cell, List[Tuple[int, int]]] = {}
    for schedule in schedules:
        waits = [entry.wait for entry in schedule.entries]
        occupancy = simulate_occupancy(env, graph, schedule, waits)
        # Check first, reserve after: a plan trivially "overlaps" itself —
        # `simulate_occupancy` emits every intermediate node twice at the
        # same instant — and a train cannot block its own path anyway.
        for cell, start, end, _ in occupancy:
            for other_start, other_end in reservations.get(cell, ()):
                if start - safety <= other_end and other_start - safety <= end:
                    return True
        for cell, start, end, _ in occupancy:
            reservations.setdefault(cell, []).append((start, end))
    return False


__all__ = [
    "DWELL",
    "WAIT_MENU",
    "BranchOption",
    "DecisionPoint",
    "advance_through_forced",
    "arrival_time",
    "complete_from",
    "has_planned_overlap",
    "initial_prefixes",
    "is_complete",
    "next_decision",
    "route_options",
]
