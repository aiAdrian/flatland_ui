"""Reading a running Flatland episode back into a search state.

The search plans in its own fast model of the railway; the app runs the
real thing. To re-plan from where the trains actually are — after a
breakdown, or when the dials change mid-episode — that live situation has
to be expressed as a `WorldState` the tree can be rooted on.

Most of it is direct: a train's cell, its heading, whether it has departed
and whether it is done all come straight off the environment. One thing has
to be *inferred*: how far down its line the train has got. Flatland records
the final target but not which intermediate calls are already served, so it
is read off the plan the train is currently following — the stops still
ahead are the ones its remaining schedule still visits. Where there is no
plan to read, the fallback is the last stop the train is standing on, and
failing that the first one.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from flatland.envs.rail_env import RailEnv
from flatland.envs.step_utils.states import TrainState as FlatlandTrainState

from app.policies.goal_based_policies.infrastructure_graph import Cell
from app.policies.tree_search.scenario import Scenario
from app.policies.tree_search.simulator import TrainState, WorldState


def _locate_edge(
    scenario: Scenario, cell: Cell, heading: int
) -> Optional[Tuple[object, int]]:
    """Guess which edge a train on this cell is driving, and how far along.

    A last resort, used only for a train whose plan cannot say — it scans
    every edge for one that passes this cell in this direction, and a long
    network usually offers several in quite different places. Where the
    train *is* following a plan, `SchedulePlayer.locate` answers exactly
    and is used instead; this is the "off plan" case, where being roughly
    right beats refusing to re-plan at all.
    """
    best: Optional[Tuple[object, int]] = None
    for edge in scenario.graph.edges:
        for index, path_cell in enumerate(edge.path):
            if index == 0 or path_cell != cell:
                continue
            if edge.moves[index - 1] != heading:
                continue
            if best is None or (
                (edge.travel_time, edge.out_direction)
                < (best[0].travel_time, best[0].out_direction)
            ):
                best = (edge, index)
    return best


def _stop_index(
    scenario: Scenario,
    handle: int,
    cell: Cell,
    remaining_cells: Optional[Sequence[Cell]],
) -> int:
    """Which booked stop the train is heading for next."""
    stops = scenario.trains[handle].stops
    if remaining_cells:
        ahead = set(remaining_cells)
        for index in range(1, len(stops)):
            if stops[index] in ahead:
                return index
        return len(stops)
    for index in range(len(stops) - 1, 0, -1):
        if stops[index] == cell:
            return min(index + 1, len(stops))
    return 1


def state_from_env(
    scenario: Scenario,
    env: RailEnv,
    player=None,
) -> WorldState:
    """The live episode as a search state.

    Pass the `SchedulePlayer` driving the episode whenever there is one.
    It is what makes the reading exact: it knows which edge each train is
    on — the graph alone does not, since one cell in one direction belongs
    to several edges across a network — and its remaining entries are what
    the served stops are read off.
    """
    now = int(getattr(env, "_elapsed_steps", 0) or 0)
    remaining = None if player is None else remaining_cells(scenario, player)
    trains: List[TrainState] = []
    for data in scenario.trains:
        agent = env.agents[data.handle]
        done = agent.state == FlatlandTrainState.DONE
        position = getattr(agent, "position", None)
        if position is None:
            # Off the map: either finished, or not yet departed. A train
            # that is not on the map has no direction — Flatland reports
            # None rather than its initial one, so that is what has to be
            # fallen back on.
            heading = getattr(agent, "direction", None)
            trains.append(TrainState(
                handle=data.handle,
                cell=data.stops[-1] if done else data.origin,
                heading=int(
                    data.initial_direction if heading is None else heading),
                stop_index=len(data.stops) if done else 1,
                departed=done,
                underway=done,
                done=done,
                arrival=now if done else None,
            ))
            continue

        cell = (int(position[0]), int(position[1]))
        heading = int(agent.direction)
        # Which edge is this train on? The player knows, because it is the
        # one driving it; index 0 means "standing on the node, not yet
        # under way", which is a train at a decision point.
        located = None if player is None else player.locate(data.handle)
        if located is not None and (
            located[1] == 0 or located[1] == len(located[0].path) - 1
        ):
            # Either end of the edge means the train is standing *at* a
            # node — not yet under way, or just arrived. Keeping the edge
            # would leave it with no next cell to drive to.
            located = None
        elif located is None and (
            cell not in scenario.graph.nodes
            or not scenario.onward_edges(cell, heading)
        ):
            located = _locate_edge(scenario, cell, heading)
        handler = getattr(agent, "malfunction_handler", None)
        broken = int(getattr(handler, "malfunction_down_counter", 0) or 0)
        trains.append(TrainState(
            handle=data.handle,
            cell=cell,
            heading=heading,
            edge=None if located is None else located[0],
            index=0 if located is None else located[1],
            # A train that is broken down is standing still for that long,
            # which the search should plan around rather than discover.
            wait_left=broken,
            stop_index=_stop_index(
                scenario, data.handle, cell,
                None if remaining is None else remaining.get(data.handle),
            ),
            departed=True,
            underway=True,
            done=False,
        ))
    return WorldState(step=now, trains=tuple(trains))


def remaining_cells(scenario: Scenario, player) -> Dict[int, List[Cell]]:
    """Per train, the cells its committed schedule still has ahead."""
    cells: Dict[int, List[Cell]] = {}
    for data in scenario.trains:
        entries = player.remaining(data.handle)
        cells[data.handle] = [
            scenario.graph.cell_of(entry.node_id) for entry in entries
        ]
    return cells


__all__ = ["remaining_cells", "state_from_env"]
