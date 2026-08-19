"""Turning a path through the tree into something the trains can be driven by.

The search reasons in joint decisions; the running app drives trains with
`SchedulePlayer`, which reads a per-train list of `(node, wait)`. The two
line up exactly — a decision is "leave this node for that one" or "stand
here a while" — so a path becomes a set of schedules by replaying it.

Replay rather than bookkeeping: the tree's branches only record the
*choices*, because everything forced (leaving a platform down the only
track, rolling through a node with one way onward) is executed while the
child state is built and never becomes a node. Replaying the same
deterministic machinery recovers those steps instead of storing them on
every node, which is what keeps a large tree affordable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from app.policies.goal_based_policies.infrastructure_graph import Cell
from app.policies.goal_based_policies.schedule import ScheduleEntry, TrainSchedule
from app.policies.tree_search import actions as action_model
from app.policies.tree_search import simulator
from app.policies.tree_search.actions import JointAction
from app.policies.tree_search.scenario import DWELL, Scenario
from app.policies.tree_search.simulator import Outcome, WorldState


@dataclass
class _Track:
    """One train's visits, being written as the replay proceeds."""
    cells: List[Cell] = field(default_factory=list)
    waits: List[int] = field(default_factory=list)

    def visit(self, cell: Cell) -> None:
        if not self.cells or self.cells[-1] != cell:
            self.cells.append(cell)
            self.waits.append(0)

    def hold(self, steps: int) -> None:
        if self.waits:
            self.waits[-1] += int(steps)


@dataclass
class ReplayResult:
    state: WorldState
    schedules: List[TrainSchedule]
    outcome: Outcome


def replay(
    scenario: Scenario,
    root: WorldState,
    joint_actions: Sequence[JointAction],
    max_children: int = action_model.MAX_CHILDREN,
) -> ReplayResult:
    """Run the decisions and write down where every train stood.

    `root` is the state the *search* started from — for a plan made from
    scratch that is the initial state, not the search's root node: getting
    to the root already involved forced moves, and the schedule has to
    contain the nodes they went through or it will name two nodes with no
    track between them.

    Only *intended* standing time is recorded — the holds the search chose
    and the dwell a booked stop demands. Time a train spent waiting for a
    cell to clear is not a plan, it is what happened, and writing it into
    the schedule would harden a queue into a timetable.
    """
    # Anchor each train where it stands in `root`: at a node, that node; in
    # mid-run, the node it drove out of, because a player reads the first
    # entry as "the node this train is coming from". A hold already being
    # served carries over, so a re-plan does not silently release a train
    # that was told to wait.
    tracks: Dict[int, _Track] = {
        data.handle: _Track() for data in scenario.trains
    }
    for train in root.trains:
        anchor = train.edge.from_cell if train.edge is not None else train.cell
        tracks[train.handle].visit(anchor)
        tracks[train.handle].hold(train.wait_left)

    state = root
    pending = list(joint_actions)

    def record_stops(before: WorldState, after: WorldState) -> None:
        for handle, track in tracks.items():
            was, now = before.train(handle), after.train(handle)
            if now.at_node and now.cell != was.cell:
                track.visit(now.cell)
            # A booked intermediate call adds the dwell the stop demands.
            if now.stop_index > was.stop_index and not now.done:
                track.hold(DWELL)

    def advance(state: WorldState) -> WorldState:
        """One step, with the node visits it produced written down."""
        nxt = simulator.step(scenario, state)
        record_stops(state, nxt)
        return nxt

    while not simulator.is_terminal(scenario, state):
        handles = simulator.deciding(scenario, state)
        if not handles:
            state = advance(state)
            continue
        candidates = action_model.joint_actions(
            scenario, state, handles, max_children)
        if not candidates:
            state = advance(state)
            continue
        if len(candidates) == 1:
            chosen = candidates[0]      # forced: not a branch of the tree
        elif pending:
            chosen = pending.pop(0)
        else:
            break                       # the path ran out before the run did
        for handle, decision in chosen:
            if decision.is_wait:
                tracks[handle].hold(decision.wait)
        state = simulator.apply_decisions(scenario, state, dict(chosen))

    schedules = [
        TrainSchedule(
            handle=data.handle,
            entries=[
                ScheduleEntry(scenario.graph.node_id(cell), wait)
                for cell, wait in zip(
                    tracks[data.handle].cells, tracks[data.handle].waits
                )
            ],
        )
        for data in scenario.trains
    ]
    return ReplayResult(
        state=state, schedules=schedules,
        outcome=simulator.outcome(scenario, state),
    )


def schedules_for(
    scenario: Scenario, root: WorldState, joint_actions: Sequence[JointAction]
) -> List[TrainSchedule]:
    """Just the schedules — the form the app executes plans in."""
    return replay(scenario, root, joint_actions).schedules


__all__ = ["ReplayResult", "replay", "schedules_for"]
