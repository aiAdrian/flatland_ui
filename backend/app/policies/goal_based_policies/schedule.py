"""Schedules over the decision-point graph.

A train's whole run is a list of decision nodes it passes, each with the
number of turns it waits there:

    [node_id, wait, node_id, wait, ...]

Playing it back needs no search (`SchedulePlayer`):

- Train not on its current schedule node → drive one step closer to it
  along the edge, using the edge's stored action sequence.
- Train on the node with `wait > 0` → stand still, count the wait down.
- Train on the node with `wait == 0` → drop that entry and drive the first
  step of the edge towards the next node.

`plan_shortest_path` produces such a schedule for a single train with a
Dijkstra search over the graph, weighted by edge travel time.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions

from app.policies.goal_based_policies.infrastructure_graph import (
    Cell,
    DecisionPointGraph,
    GraphEdge,
    _get_transitions,
    action_for_move,
)


@dataclass(frozen=True)
class ScheduleEntry:
    """One decision node on a train's run and how long it waits there."""
    node_id: int
    wait: int = 0


@dataclass
class TrainSchedule:
    """A train's ordered decision nodes, starting at its origin."""
    handle: int
    entries: List[ScheduleEntry] = field(default_factory=list)

    def to_flat_list(self) -> List[int]:
        """`[node_id, wait, node_id, wait, ...]` — two values per node."""
        flat: List[int] = []
        for entry in self.entries:
            flat.extend((int(entry.node_id), int(entry.wait)))
        return flat

    @classmethod
    def from_flat_list(cls, handle: int, values: Sequence[int]) -> "TrainSchedule":
        if len(values) % 2:
            raise ValueError("schedule needs two values per node (id, wait)")
        return cls(
            handle=int(handle),
            entries=[
                ScheduleEntry(node_id=int(values[i]), wait=int(values[i + 1]))
                for i in range(0, len(values), 2)
            ],
        )

    @property
    def total_wait(self) -> int:
        return sum(e.wait for e in self.entries)


def _feasible(env: RailEnv, cell: Cell, heading: int, edge: GraphEdge) -> bool:
    """Can a train oriented `heading` on `cell` take `edge`?"""
    return bool(_get_transitions(env, cell, heading)[edge.out_direction])


def plan_shortest_path_states(
    graph: DecisionPointGraph,
    env: RailEnv,
    start_cell: Cell,
    start_heading: int,
    target_cell: Cell,
) -> Optional[List[Tuple[Cell, int]]]:
    """The `(cell, orientation)` states of the fastest route, in order.

    Same search as `plan_shortest_path`, but keeping the orientation the
    train has at each node. The arrival orientation at the target is what a
    following leg has to start from — a train cannot turn around, so
    re-deriving it from the cells alone can pick a different edge than the
    search actually took.
    """
    start_cell = (int(start_cell[0]), int(start_cell[1]))
    target_cell = (int(target_cell[0]), int(target_cell[1]))
    if start_cell not in graph.nodes or target_cell not in graph.nodes:
        return None

    start = (start_cell, int(start_heading))
    best: Dict[Tuple[Cell, int], int] = {start: 0}
    came_from: Dict[Tuple[Cell, int], Tuple[Cell, int]] = {}
    queue: List[Tuple[int, Tuple[Cell, int]]] = [(0, start)]
    goal: Optional[Tuple[Cell, int]] = None

    while queue:
        cost, state = heapq.heappop(queue)
        if cost > best.get(state, cost):
            continue
        cell, heading = state
        if cell == target_cell and state != start:
            goal = state
            break
        for edge in graph.edges_from(cell):
            if not _feasible(env, cell, heading, edge):
                continue
            nxt = (edge.to_cell, edge.in_direction)
            nxt_cost = cost + edge.travel_time
            if nxt_cost < best.get(nxt, nxt_cost + 1):
                best[nxt] = nxt_cost
                came_from[nxt] = state
                heapq.heappush(queue, (nxt_cost, nxt))

    if goal is None:
        return None

    states = [goal]
    while states[-1] != start:
        states.append(came_from[states[-1]])
    states.reverse()
    return states


def plan_shortest_path(
    graph: DecisionPointGraph,
    env: RailEnv,
    start_cell: Cell,
    start_heading: int,
    target_cell: Cell,
    handle: int = 0,
) -> Optional[TrainSchedule]:
    """Fastest node sequence from `start_cell` to `target_cell`, no waits.

    Dijkstra over `(node, orientation)` states weighted by edge travel time.
    Orientation is part of the state because which edges a node offers
    depends on how the train stands there — a train cannot reverse on the
    spot. Returns None when the target is unreachable.
    """
    states = plan_shortest_path_states(
        graph, env, start_cell, start_heading, target_cell
    )
    if states is None:
        return None
    return TrainSchedule(
        handle=handle,
        entries=[ScheduleEntry(graph.node_id(cell), 0) for cell, _ in states],
    )


def line_stops(env: RailEnv, handle: int) -> List[Cell]:
    """The cells a train's line calls at, origin first, target last.

    Flatland's `sparse_line_generator(line_length=n)` gives each agent `n`
    waypoints; `env_factory` uses 4, its own default is 2. `agent.target`
    is only the *last* of them, so anything routing to `agent.target`
    ignores the calls in between.
    """
    agent = env.agents[handle]
    waypoints = getattr(agent, "waypoints", None)
    if not waypoints:
        return [
            (int(agent.initial_position[0]), int(agent.initial_position[1])),
            (int(agent.target[0]), int(agent.target[1])),
        ]
    return [(int(w[0].position[0]), int(w[0].position[1])) for w in waypoints]


def plan_line(
    graph: DecisionPointGraph,
    env: RailEnv,
    handle: int = 0,
    dwell: int = 1,
) -> Optional[TrainSchedule]:
    """Schedule calling at every stop of the train's line, in order.

    `plan_shortest_path` routes straight to `agent.target`, which is only
    the final waypoint, so it happily skips the calls in between. This
    chains a shortest path per leg, carrying the arrival orientation from
    one leg into the next, and returns them as a single schedule starting
    at the train's origin — so the ordinary `initial_direction` default is
    the right starting heading for the result.

    `dwell` is the wait given at each intermediate stop. It defaults to 1
    rather than 0 because Flatland's reward counts an intermediate stop as
    served only if it records both an arrival *and* a departure there —
    "run through without stopping" is penalised — and a passenger changing
    trains needs the train to actually stand at the platform. The final
    target gets no dwell; the run ends there.

    Returns None if any leg is unroutable.
    """
    stops = line_stops(env, handle)
    heading = int(env.agents[handle].initial_direction)
    entries: List[ScheduleEntry] = []

    for index, target in enumerate(stops[1:], start=1):
        states = plan_shortest_path_states(
            graph, env, stops[index - 1], heading, target
        )
        if states is None or len(states) < 2:
            return None
        cells = [cell for cell, _ in states]
        if not entries:
            entries.append(ScheduleEntry(graph.node_id(cells[0]), 0))
        # The leg starts where the previous one ended, so drop the repeat.
        entries.extend(ScheduleEntry(graph.node_id(cell), 0) for cell in cells[1:])
        heading = states[-1][1]
        if index < len(stops) - 1 and dwell > 0:
            entries[-1] = ScheduleEntry(entries[-1].node_id, int(dwell))

    return TrainSchedule(handle=handle, entries=entries) if entries else None


def simulate_occupancy(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedule: TrainSchedule,
    waits: Sequence[int],
) -> List[Tuple[Cell, int, int, int]]:
    """When the plan puts the train on each cell: `(cell, in, out, node)`.

    `node` is the index of the decision node the train last passed, which is
    where a hold has to be inserted to shift that occupancy later.
    """
    agent = env.agents[schedule.handle]
    heading = int(agent.initial_direction)
    clock = int(getattr(agent, "earliest_departure", 0) or 0)
    cells = [graph.cell_of(e.node_id) for e in schedule.entries]

    occupancy: List[Tuple[Cell, int, int, int]] = []
    for index, (cell, nxt) in enumerate(zip(cells, cells[1:])):
        hold = int(waits[index]) if index < len(waits) else 0
        occupancy.append((cell, clock, clock + hold, index))
        clock += hold
        usable = [
            e for e in graph.edges_from(cell)
            if e.to_cell == nxt and _feasible(env, cell, heading, e)
        ]
        if not usable:
            break
        edge = min(usable, key=lambda e: (e.travel_time, e.out_direction))
        for offset, path_cell in enumerate(edge.path[1:], start=1):
            occupancy.append((path_cell, clock + offset, clock + offset, index))
        clock += edge.travel_time
        heading = edge.in_direction
    return occupancy


def plan_avoiding_overlaps(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedules: Sequence[TrainSchedule],
    safety: int = 1,
    max_total_wait: int = 60,
    max_iterations: int = 400,
) -> List[TrainSchedule]:
    """Add holds so trains do not claim the same cell at the same time.

    Prioritised planning: trains are planned one after another, each
    reserving the cells it occupies over time, and a later train is held at
    the last decision node before any cell another train has already
    reserved. Holds land on decision nodes because that is the only place
    this schedule representation can express them — and the only place a
    train can realistically be held.

    Deliberately our own simple planner rather than a consortium one: the
    reuse target for proper multi-train planning is Tokener's PP/CBS
    (see CLAUDE.md), which is a larger integration than this data
    generation needs.
    """
    order = sorted(
        schedules,
        key=lambda s: (
            int(getattr(env.agents[s.handle], "earliest_departure", 0) or 0),
            s.handle,
        ),
    )

    reservations: Dict[Cell, List[Tuple[int, int]]] = {}
    planned: Dict[int, TrainSchedule] = {}

    for schedule in order:
        waits = [0] * len(schedule.entries)
        occupancy: List[Tuple[Cell, int, int, int]] = []
        for _ in range(max_iterations):
            occupancy = simulate_occupancy(env, graph, schedule, waits)
            blocked = None
            for cell, start, end, node_index in occupancy:
                for other_start, other_end in reservations.get(cell, ()):
                    if start - safety <= other_end and other_start - safety <= end:
                        blocked = node_index
                        break
                if blocked is not None:
                    break
            if blocked is None:
                break
            waits[blocked] += 1
            if sum(waits) > max_total_wait:
                break

        for cell, start, end, _ in occupancy:
            reservations.setdefault(cell, []).append((start, end))
        planned[schedule.handle] = TrainSchedule(
            handle=schedule.handle,
            entries=[
                ScheduleEntry(entry.node_id, waits[index])
                for index, entry in enumerate(schedule.entries)
            ],
        )

    return [planned[s.handle] for s in schedules]


class SchedulePlayer:
    """Executes schedules, turning them into Flatland actions per step.

    Holds only the remaining schedule per train; where a train is along the
    current edge is read back from the env each step, so a train delayed by
    a malfunction or a blocked cell simply repeats its action instead of
    drifting out of sync with the plan.
    """

    def __init__(
        self,
        graph: DecisionPointGraph,
        env: RailEnv,
        schedules: Iterable[TrainSchedule] = (),
    ):
        self.graph = graph
        self.env = env
        self._remaining: Dict[int, List[ScheduleEntry]] = {}
        self._waited: Dict[int, int] = {}
        for schedule in schedules:
            self.set_schedule(schedule)

    def set_schedule(self, schedule: TrainSchedule) -> None:
        self._remaining[schedule.handle] = list(schedule.entries)
        self._waited[schedule.handle] = 0

    def remaining(self, handle: int) -> List[ScheduleEntry]:
        return list(self._remaining.get(handle, []))

    def waited(self, handle: int) -> int:
        """Steps already stood at the current entry's node."""
        return self._waited.get(handle, 0)

    def locate(self, handle: int) -> Optional[Tuple[GraphEdge, int]]:
        """Where the train stands on its planned edge right now, from the
        env: `(edge, index_in_path)`, or None when off the map, off plan,
        or standing on its final node."""
        agent = self.env.agents[handle]
        if agent.position is None:
            return None
        return self._locate(
            handle,
            (int(agent.position[0]), int(agent.position[1])),
            int(agent.direction),
        )

    def future_path(self, handle: int) -> List[Dict[str, int]]:
        """The cells still ahead of the train on its plan, in driving
        order, as `{step, row, col}` points — `step` estimating when the
        train reaches each cell from *now* (malfunction remaining and
        unserved waits included). Starts at the train's actual position,
        so it is contiguous on the rails by construction.

        Empty for a train that is done, off its plan, or has nothing
        left — no highlight beats a wrong one. A train not yet on the
        map gets its whole run from the origin.
        """
        from flatland.envs.step_utils.states import TrainState

        agent = self.env.agents[handle]
        remaining = self._remaining.get(handle, [])
        if agent.state == TrainState.DONE or not remaining:
            return []
        now = int(getattr(self.env, "_elapsed_steps", 0) or 0)
        handler = getattr(agent, "malfunction_handler", None)
        malfunction = int(getattr(handler, "malfunction_down_counter", 0) or 0)

        points: List[Dict[str, int]] = []

        def emit(cell: Cell, step: int) -> None:
            if points and (points[-1]["row"], points[-1]["col"]) == (
                int(cell[0]), int(cell[1])
            ):
                return
            points.append({
                "step": int(step), "row": int(cell[0]), "col": int(cell[1]),
            })

        if agent.position is None:
            # Not on the map yet: the whole run, from the origin.
            departure = int(getattr(agent, "earliest_departure", 0) or 0)
            clock = max(now, departure) + malfunction + 1
            emit(self.graph.cell_of(remaining[0].node_id), clock)
            clock += remaining[0].wait
            heading = int(agent.initial_direction)
            entries = remaining
        else:
            located = self.locate(handle)
            if located is None:
                return []
            edge, index = located
            if index == 0:
                # Standing on the current node.
                emit(self.graph.cell_of(remaining[0].node_id), now)
                wait_left = max(
                    remaining[0].wait - self._waited.get(handle, 0), 0)
                clock = now + max(wait_left, malfunction)
                heading = int(agent.direction)
                entries = remaining
            else:
                # Mid-edge: the rest of the current edge first.
                clock = now + malfunction
                for offset, path_cell in enumerate(edge.path[index:]):
                    emit(path_cell, clock + offset)
                clock += len(edge.path) - 1 - index
                clock += remaining[1].wait if len(remaining) > 1 else 0
                heading = edge.in_direction
                entries = remaining[1:]

        cells = [self.graph.cell_of(entry.node_id) for entry in entries]
        for i, (cell, nxt) in enumerate(zip(cells, cells[1:])):
            usable = [
                e for e in self.graph.edges_from(cell)
                if e.to_cell == nxt and _feasible(self.env, cell, heading, e)
            ]
            if not usable:
                break
            onward = min(usable, key=lambda e: (e.travel_time, e.out_direction))
            for offset, path_cell in enumerate(onward.path[1:], start=1):
                emit(path_cell, clock + offset)
            clock += onward.travel_time
            heading = onward.in_direction
            if i + 1 < len(entries):
                clock += entries[i + 1].wait
        return points

    def snapshot(self) -> Dict[int, Tuple[List[ScheduleEntry], int]]:
        """The player's whole progress state, for replaying the same plan
        on a forked env: per handle, the remaining entries and the wait
        already served at the current node."""
        return {
            handle: (list(entries), self._waited.get(handle, 0))
            for handle, entries in self._remaining.items()
        }

    def restore(
        self, state: Dict[int, Tuple[List[ScheduleEntry], int]]
    ) -> None:
        self._remaining = {
            handle: list(entries) for handle, (entries, _) in state.items()
        }
        self._waited = {
            handle: int(waited) for handle, (_, waited) in state.items()
        }

    def _locate(
        self, handle: int, position: Cell, heading: int
    ) -> Optional[Tuple[GraphEdge, int]]:
        """Find the edge to the next node and how far along it the train is.

        Returns `(edge, index_in_path)`, or None when the train is not on
        the planned edge at all. Matching uses the arrival heading as well
        as the cell: an edge may roll over a cell more than once (a node is
        only a node for some directions), and parallel edges between the
        same two nodes are told apart the same way.
        """
        entries = self._remaining.get(handle, [])
        if len(entries) < 2:
            return None
        cell = self.graph.cell_of(entries[0].node_id)
        target = self.graph.cell_of(entries[1].node_id)
        candidates = [
            edge for edge in self.graph.edges_from(cell) if edge.to_cell == target
        ]

        located: List[Tuple[GraphEdge, int]] = []
        for edge in candidates:
            if position == cell and _feasible(self.env, cell, heading, edge):
                located.append((edge, 0))
                continue
            for index, path_cell in enumerate(edge.path):
                # index 0 is the source node, only valid via the branch above.
                if index and path_cell == position and edge.moves[index - 1] == heading:
                    located.append((edge, index))
                    break
        if not located:
            return None
        # Deterministic pick: fastest, then by exit direction.
        return min(located, key=lambda item: (item[0].travel_time, item[0].out_direction))

    def act(self, handle: int) -> int:
        """Action for this train this step."""
        entries = self._remaining.get(handle)
        if not entries:
            return RailEnvActions.DO_NOTHING.value

        agent = self.env.agents[handle]
        if agent.position is None:
            # Still off map: a move action puts it on its origin, which is
            # the schedule's first node — no entry is consumed for that.
            return RailEnvActions.MOVE_FORWARD.value

        position = (int(agent.position[0]), int(agent.position[1]))
        heading = int(agent.direction)

        if position == self.graph.cell_of(entries[0].node_id):
            if entries[0].wait > self._waited[handle]:
                self._waited[handle] += 1
                return RailEnvActions.STOP_MOVING.value
            self._waited[handle] = 0

        located = self._locate(handle, position, heading)
        if located is None:
            # Off plan, or standing on the final node — hold rather than guess.
            return RailEnvActions.DO_NOTHING.value

        edge, index = located
        if index == len(edge.path) - 1:
            # Arrived at the next node: drop the entry we came from and
            # re-decide from there (the new node may impose a wait).
            self._remaining[handle] = entries[1:]
            self._waited[handle] = 0
            return self.act(handle)

        return action_for_move(heading, edge.moves[index])

    def act_many(self, handles: Optional[Iterable[int]] = None) -> Dict[int, int]:
        if handles is None:
            handles = list(self._remaining)
        return {int(h): self.act(int(h)) for h in handles}


def schedule_edges(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedule: TrainSchedule,
    start_heading: Optional[int] = None,
) -> List[GraphEdge]:
    """The graph edges the plan traverses, in order.

    Resolves each consecutive node pair to the edge the player would take
    (feasible from the arrival heading, cheapest first, ties by exit
    direction — the same rule `SchedulePlayer` applies, so what is read
    here is what would actually be driven). Stops early where a pair
    cannot be resolved, mirroring how playback would fail there.

    `start_heading` is which way the train points at the schedule's first
    node. It is a parameter rather than something derived because a cell
    offers completely different onward edges — often none — depending on
    the orientation the train stands in. It defaults to the agent's
    initial direction, which is right only when the schedule starts at the
    train's origin.
    """
    heading = (
        int(env.agents[schedule.handle].initial_direction)
        if start_heading is None else int(start_heading)
    )
    cells = [graph.cell_of(e.node_id) for e in schedule.entries]
    edges: List[GraphEdge] = []
    for cell, nxt in zip(cells, cells[1:]):
        usable = [
            e for e in graph.edges_from(cell)
            if e.to_cell == nxt and _feasible(env, cell, heading, e)
        ]
        if not usable:
            break
        edge = min(usable, key=lambda e: (e.travel_time, e.out_direction))
        edges.append(edge)
        heading = edge.in_direction
    return edges


def edge_time_windows(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedule: TrainSchedule,
    start_heading: Optional[int] = None,
) -> List[Tuple[GraphEdge, float, float]]:
    """Per traversed edge, the planned `(edge, enter, exit)` window.

    Open-loop timing: the train departs at its earliest departure, sits out
    each scheduled wait at the node before moving on, and crosses an edge
    in its travel time. No interaction with any other train — this is what
    the *plan* claims will happen, which is what a plan is.
    """
    agent = env.agents[schedule.handle]
    clock = float(getattr(agent, "earliest_departure", 0) or 0)
    windows: List[Tuple[GraphEdge, float, float]] = []
    for index, edge in enumerate(
        schedule_edges(env, graph, schedule, start_heading)
    ):
        clock += schedule.entries[index].wait
        windows.append((edge, clock, clock + edge.travel_time))
        clock += edge.travel_time
    return windows
