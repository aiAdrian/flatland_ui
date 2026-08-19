"""The fast graph-level simulator.

Advances the railway between two nodes of the search tree: apply the joint
decision, then run time forward until the next train stands at a decision
point. Cell-by-cell, one cell per step, so blocking, following and head-on
deadlock come out of the movement rules rather than being modelled
separately — but on the decision-point graph's cell paths, with no
Flatland environment stepped and nothing copied.

    state --apply(action)--> state --run--> state (someone is deciding)

This is a *model* of Flatland, not Flatland. What it reproduces on purpose:
one cell per step, a cell holds one train, a train cannot reverse, a train
may enter a cell another train leaves in the same step, and two trains
facing each other on one track never pass. What it leaves out: breakdowns
(the live search re-roots when one happens), speeds other than one cell per
step, and Flatland's own departure bookkeeping beyond the earliest
departure. `tests/test_tree_search_simulator.py` is where that equivalence
is held to account.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

from app.policies.goal_based_policies.infrastructure_graph import (
    Cell,
    GraphEdge,
)
from app.policies.tree_search.scenario import DWELL, Scenario

# Steps without a single train moving, and with nobody deciding, after which
# the world is declared stuck. One step is enough in principle — nothing can
# change without a mover — but a small margin keeps departure bookkeeping
# from being mistaken for gridlock.
STUCK_STEPS = 3


@dataclass(frozen=True)
class TrainState:
    """One train's position in the graph at one instant."""
    handle: int
    cell: Cell                       # where it physically stands
    heading: int
    edge: Optional[GraphEdge] = None  # the edge being driven, None at a node
    index: int = 0                   # how far along `edge.path`
    wait_left: int = 0               # steps still to stand still
    stop_index: int = 1              # the next booked stop, 0 is the origin
    departed: bool = False
    underway: bool = False           # has it ever left its origin
    done: bool = False
    arrival: Optional[int] = None    # step it reached its terminus

    @property
    def at_node(self) -> bool:
        return self.edge is None

    def key(self) -> Tuple:
        """Identity for transposition lookups — position and progress, not
        the edge object."""
        return (
            self.cell, self.heading, self.index, self.wait_left,
            self.stop_index, self.departed, self.underway, self.done,
            None if self.edge is None else (self.edge.from_cell,
                                            self.edge.to_cell,
                                            self.edge.out_direction),
        )


@dataclass(frozen=True)
class WorldState:
    """The whole railway at one instant."""
    step: int
    trains: Tuple[TrainState, ...]
    stuck_for: int = 0

    def train(self, handle: int) -> TrainState:
        return self.trains[handle]

    @property
    def all_done(self) -> bool:
        return all(t.done for t in self.trains)

    def key(self) -> Tuple:
        """Two states with the same key are the same situation and may share
        a node — the tree is really a graph."""
        return (self.step, tuple(t.key() for t in self.trains))


def initial_state(scenario: Scenario) -> WorldState:
    """Every train off the map, at time zero."""
    return WorldState(
        step=0,
        trains=tuple(
            TrainState(
                handle=data.handle,
                cell=data.origin,
                heading=data.initial_direction,
                stop_index=1,
            )
            for data in scenario.trains
        ),
    )


def deciding(scenario: Scenario, state: WorldState) -> Tuple[int, ...]:
    """Handles standing at a decision point with a choice to make now."""
    return tuple(
        train.handle for train in state.trains
        if _needs_decision(scenario, train)
    )


def _needs_decision(scenario: Scenario, train: TrainState) -> bool:
    if train.done or not train.departed or not train.at_node:
        return False
    if train.wait_left > 0:
        return False
    return bool(scenario.onward_edges(train.cell, train.heading))


def is_terminal(scenario: Scenario, state: WorldState) -> bool:
    """Nothing more will happen: everybody arrived, the clock ran out, or
    the world is gridlocked."""
    return (
        state.all_done
        or state.step >= scenario.horizon
        or state.stuck_for >= STUCK_STEPS
    )


def apply_decisions(
    scenario: Scenario, state: WorldState, decisions: Dict[int, object]
) -> WorldState:
    """Give every deciding train its choice. See `actions.Decision`."""
    trains = list(state.trains)
    for handle, decision in decisions.items():
        train = trains[handle]
        if decision.edge is not None:
            # The heading is left alone: it changes when the train actually
            # moves, which is also where it is read from.
            trains[handle] = replace(
                train, edge=decision.edge, index=0, underway=True)
        else:
            trains[handle] = replace(train, wait_left=int(decision.wait))
    return replace(state, trains=tuple(trains))


def run(scenario: Scenario, state: WorldState) -> WorldState:
    """Advance time until somebody has to decide, or nothing can happen."""
    while not is_terminal(scenario, state) and not deciding(scenario, state):
        state = step(scenario, state)
    return state


def step(scenario: Scenario, state: WorldState) -> WorldState:
    """One time step of the whole railway."""
    trains = list(state.trains)
    now = state.step + 1

    # Departures: a train appears on its origin once its time has come and
    # the platform is free.
    occupied = {
        t.cell: t.handle for t in trains if t.departed and not t.done
    }
    # Anything that changes the world resets the gridlock counter — a train
    # departing, a hold ticking down or a train moving. Trains whose
    # departure slot has not come yet count as pending, so the quiet minutes
    # before the first train rolls are not mistaken for gridlock.
    progress = False
    for handle, train in enumerate(trains):
        if train.departed or train.done:
            continue
        data = scenario.trains[handle]
        if now < data.earliest_departure:
            progress = True   # still to come
            continue
        if train.cell in occupied:
            continue
        occupied[train.cell] = handle
        trains[handle] = replace(train, departed=True)
        progress = True

    # Waits tick down before movement, so a train released this step can be
    # followed into the cell it leaves.
    for handle, train in enumerate(trains):
        if train.departed and not train.done and train.wait_left > 0:
            trains[handle] = replace(train, wait_left=train.wait_left - 1)
            progress = True

    if _advance_positions(scenario, trains, occupied):
        progress = True

    # Arrivals and stops, once positions are settled.
    for handle, train in enumerate(trains):
        if train.done or not train.departed or not train.at_node:
            continue
        trains[handle] = _serve_stop(scenario, train, now)

    stuck = 0 if progress else state.stuck_for + 1
    return WorldState(step=now, trains=tuple(trains), stuck_for=stuck)


def _advance_positions(
    scenario: Scenario,
    trains: List[TrainState],
    occupied: Dict[Cell, int],
) -> bool:
    """Move every train that can move one cell. Returns whether any did.

    Conflicts are resolved by repeatedly approving the moves whose target
    is free — either free to begin with, or freed by a train that already
    moved this step. Trains facing each other on one track therefore both
    stay put, which is what a head-on deadlock is.
    """
    intended: Dict[int, Cell] = {}
    for handle, train in enumerate(trains):
        if (train.done or not train.departed or train.at_node
                or train.wait_left > 0):
            continue
        nxt = train.edge.path[train.index + 1]
        intended[handle] = nxt

    approved: List[int] = []
    claimed: set = set()
    changed = True
    while changed:
        changed = False
        for handle in sorted(intended):
            if handle in approved:
                continue
            target = intended[handle]
            if target in claimed:
                continue
            holder = occupied.get(target)
            if holder is not None and holder not in approved:
                continue
            approved.append(handle)
            claimed.add(target)
            changed = True

    for handle in approved:
        train = trains[handle]
        index = train.index + 1
        cell = train.edge.path[index]
        occupied.pop(train.cell, None)
        occupied[cell] = handle
        arrived = index == len(train.edge.path) - 1
        trains[handle] = replace(
            train,
            cell=cell,
            heading=train.edge.moves[index - 1],
            index=index,
            edge=None if arrived else train.edge,
        )
    return bool(approved)


def _serve_stop(
    scenario: Scenario, train: TrainState, now: int
) -> TrainState:
    """Book a call at a stop the train has just reached, and finish the run
    at its terminus."""
    data = scenario.trains[train.handle]
    if train.stop_index >= len(data.stops):
        return train
    if train.cell != data.stops[train.stop_index]:
        return train
    last = train.stop_index == len(data.stops) - 1
    if last:
        return replace(train, done=True, arrival=now, stop_index=train.stop_index + 1)
    # An intermediate call only counts when the train actually stands there,
    # so the dwell is imposed rather than chosen.
    return replace(
        train, stop_index=train.stop_index + 1, wait_left=max(train.wait_left, DWELL)
    )


@dataclass(frozen=True)
class Outcome:
    """What a finished (or abandoned) run delivered."""
    steps: int
    arrivals: Dict[int, Optional[int]]
    delays: Dict[int, int]
    all_arrived: bool
    arrived_fraction: float
    total_delay: int
    deadlocked: bool

    def to_dict(self) -> Dict[str, object]:
        return {
            "steps": self.steps,
            "all_arrived": self.all_arrived,
            "arrived_fraction": self.arrived_fraction,
            "total_delay": self.total_delay,
            "deadlocked": self.deadlocked,
            "delays": {int(h): int(d) for h, d in self.delays.items()},
        }


def outcome(scenario: Scenario, state: WorldState) -> Outcome:
    """Measure a terminal state.

    A train that never arrived is charged against the *end of the episode*,
    not against the step the run happened to stop at. Anything else makes
    gridlock look cheap: a world that seizes up after twenty steps strands
    every train while none of them is technically late yet, and the search
    would learn to prefer an early deadlock to a small delay.
    """
    arrivals: Dict[int, Optional[int]] = {}
    delays: Dict[int, int] = {}
    for train in state.trains:
        data = scenario.trains[train.handle]
        arrivals[train.handle] = train.arrival
        reference = (
            train.arrival if train.arrival is not None
            else max(state.step, scenario.horizon)
        )
        delays[train.handle] = max(0, int(reference) - data.latest_arrival)
    arrived = sum(1 for t in state.trains if t.done)
    return Outcome(
        steps=state.step,
        arrivals=arrivals,
        delays=delays,
        all_arrived=arrived == len(state.trains),
        arrived_fraction=arrived / max(1, len(state.trains)),
        total_delay=sum(delays.values()),
        deadlocked=state.stuck_for >= STUCK_STEPS and arrived < len(state.trains),
    )


__all__ = [
    "STUCK_STEPS",
    "Outcome",
    "TrainState",
    "WorldState",
    "apply_decisions",
    "deciding",
    "initial_state",
    "is_terminal",
    "outcome",
    "run",
    "step",
]
