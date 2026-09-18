"""Replan the trains from the current state with Prioritized Planning.

The solver is AI4REALNET/flatland-blackbox's PP (vendored in `blackbox/`). This
module is the glue it does not have for a running episode:

- a `(row, col, heading)` graph of the env's transitions;
- start states taken from where the trains are *now*, each train only leaving in
  the heading it has — a train cannot turn round;
- the cells of trains standing with a malfunction reserved while they stand;
- a physical-occupancy check, because the solver lets a train "wait" on its start
  proxy, which is off the grid, while in reality it keeps occupying its cell;
- the result as a `TrainrunDict`, which `PlanPolicy` already executes.

Plan: docs/plans/proposal-agents-roadmap.md (stage 2a).
"""
from __future__ import annotations

import itertools
from types import SimpleNamespace
from typing import Dict, List, Optional, Sequence, Tuple

import networkx as nx
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_trainrun_data_structures import TrainrunDict, TrainrunWaypoint, Waypoint
from flatland.envs.step_utils.states import TrainState

from app.planners.blackbox.pp import PrioritizedPlanningSolver
from app.planners.blackbox.utils import (
    NoSolutionError,
    add_proxy_nodes,
    check_no_collisions,
    get_direction,
    is_proxy_node,
)
from app.policies.goal_based_policies.infrastructure_graph import _get_transitions
from app.utils.agent_compat import (
    agent_direction,
    agent_initial_direction,
    agent_initial_position,
    agent_position,
    agent_target,
)

_DELTA = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}


def build_rail_digraph(env: RailEnv) -> nx.DiGraph:
    """Directed graph over `(row, col, heading)`: an edge per allowed move, cost 1."""
    graph = nx.DiGraph()
    for r in range(env.height):
        for c in range(env.width):
            if int(env.rail.grid[r, c]) == 0:
                continue
            for heading in range(4):
                moves = _get_transitions(env, (r, c), heading)
                if not any(moves):
                    continue
                node = (r, c, heading)
                graph.add_node(node, type="rail")
                for move, allowed in enumerate(moves):
                    if not allowed:
                        continue
                    dr, dc = _DELTA[move]
                    nr, nc = r + dr, c + dc
                    if not (0 <= nr < env.height and 0 <= nc < env.width):
                        continue
                    nxt = (nr, nc, move)
                    if nxt not in graph:
                        graph.add_node(nxt, type="rail")
                    graph.add_edge(node, nxt, type="dir", l=1.0)
    return graph


def _down_steps(agent) -> int:
    handler = getattr(agent, "malfunction_handler", None)
    return int(getattr(handler, "malfunction_down_counter", 0) or 0)


def _start_states(env: RailEnv) -> List[SimpleNamespace]:
    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    starts = []
    for agent in env.agents:
        if agent.state == TrainState.DONE:
            continue
        on_map = agent_position(agent) is not None
        cell = agent_position(agent) if on_map else agent_initial_position(agent)
        heading = agent_direction(agent) if on_map else agent_initial_direction(agent)
        if cell is None or heading is None:
            continue
        starts.append(SimpleNamespace(
            handle=int(agent.handle),
            initial_position=(int(cell[0]), int(cell[1])),
            target=(int(agent_target(agent)[0]), int(agent_target(agent)[1])),
            heading=int(heading),
            on_map=on_map,
            down=_down_steps(agent) if on_map else 0,
            earliest_departure=0 if on_map else max(0, int(agent.earliest_departure or 0) - elapsed),
        ))
    return starts


def _physical_paths(solution: Dict[int, list], starts: Dict[int, SimpleNamespace]) -> Dict[int, list]:
    """Paths including the steps a train stands in its cell before its first move.

    The solver's own paths leave that out (the train waits on its off-grid start
    proxy); a train already on the map occupies its cell during that wait.
    """
    physical = {}
    for handle, path in solution.items():
        rail = [(node, t) for node, t in path if not is_proxy_node(node)]
        start = starts[handle]
        if rail and start.on_map:
            first_node, first_t = rail[0]
            standing = [
                ((start.initial_position[0], start.initial_position[1], start.heading), t)
                for t in range(0, int(first_t))
            ]
            rail = standing + rail
        physical[handle] = rail
    return physical


def _to_trainruns(paths: Dict[int, list], elapsed: int) -> TrainrunDict:
    trainruns: TrainrunDict = {}
    for handle, path in paths.items():
        run = []
        last_cell = None
        for node, t in path:
            cell = (int(node[0]), int(node[1]))
            if cell == last_cell:
                continue  # a wait: the next waypoint's time carries it
            run.append(TrainrunWaypoint(
                scheduled_at=elapsed + int(t),
                waypoint=Waypoint(cell, int(get_direction(node))),
            ))
            last_cell = cell
        if run:
            trainruns[int(handle)] = run
    return trainruns


def replan_from_state(env: RailEnv, priority: Sequence[int] = ()) -> Optional[TrainrunDict]:
    """A collision-free plan for every train not yet arrived, from the current step.

    `priority` lists handles to plan first, in order; the rest follow with trains
    standing on a malfunction first, then by handle. Returns None when the solver
    finds no plan or the plan would put two trains in one cell.
    """
    starts = _start_states(env)
    if not starts:
        return None
    rank = {int(h): i for i, h in enumerate(priority)}
    starts.sort(key=lambda a: (rank.get(a.handle, len(rank)), -a.down, a.handle))

    graph = add_proxy_nodes(build_rail_digraph(env), starts, cost=0.0)
    for start in starts:
        proxy = next(
            n for n in graph.nodes
            if is_proxy_node(n) and len(n) == 4 and int(n[3]) == start.handle
        )
        for succ in list(graph.successors(proxy)):
            if get_direction(succ) != start.heading:
                graph.remove_edge(proxy, succ)

    solver = PrioritizedPlanningSolver(graph)
    for start in starts:
        if start.down > 0:
            node = (start.initial_position[0], start.initial_position[1], start.heading)
            solver.res_manager.block_path(start.handle, [(node, t) for t in range(start.down + 1)])
            start.earliest_departure = max(start.earliest_departure, start.down)

    try:
        solution = solver.solve(starts)
    except (NoSolutionError, ValueError):
        return None

    by_handle = {s.handle: s for s in starts}
    paths = _physical_paths(solution, by_handle)
    try:
        check_no_collisions(paths)
    except AssertionError:
        return None

    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    return _to_trainruns(paths, elapsed)


def replan_orders(env: RailEnv, max_orders: int = 24) -> List[Tuple[Tuple[int, ...], TrainrunDict]]:
    """Distinct replans for different priority orders of the trains not yet arrived.

    With PP the order is the decision: who goes first into a contested section.
    Up to four trains every order is tried; beyond that, each train once in
    front. Orders the solver cannot plan are dropped, and orders that produce the
    same plan are reported once, under the first order that produced it.
    """
    handles = sorted(s.handle for s in _start_states(env))
    if not handles:
        return []
    if len(handles) <= 4:
        candidates = list(itertools.permutations(handles))
    else:
        candidates = [tuple(handles)] + [(h, *[o for o in handles if o != h]) for h in handles]

    seen = set()
    distinct: List[Tuple[Tuple[int, ...], TrainrunDict]] = []
    for order in candidates[:max_orders]:
        trainruns = replan_from_state(env, priority=order)
        if trainruns is None:
            continue
        key = tuple(
            (handle, tuple((wp.scheduled_at, tuple(wp.waypoint.position)) for wp in run))
            for handle, run in sorted(trainruns.items())
        )
        if key in seen:
            continue
        seen.add(key)
        distinct.append((tuple(order), trainruns))
    return distinct


__all__ = ["build_rail_digraph", "replan_from_state", "replan_orders"]
