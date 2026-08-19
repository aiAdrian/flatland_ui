"""What a train may be asked at a decision point, and how choices combine.

The geometry decides the question, and the two questions never mix:

- **stop** — a platform. The train may be held, or sent on; where it goes
  next is not in question here.
- **leg approach** — the train is about to enter a switch that merges its
  track with another. It may be held to let the other branch through; its
  route is forced.
- **head approach** — the track divides beyond this cell. The train picks a
  branch. Holding is *not* offered: there is no other branch to let past, so
  a hold here buys nothing. A train whose way is blocked is still stopped by
  the simulator — that is a consequence, not a decision.

Which of these a cell is depends on the direction of travel, not on the cell
alone: one plain-rail tile is commonly the leg approach of the switch behind
it and the head approach of the switch ahead of it. Where a cell genuinely
carries both for the *same* direction — two switches back to back, the
decision pushed back onto one tile — the option list is the product of the
two, which falls out of the code below rather than being special-cased.

A branch of the search tree is one **joint action**: one option per train
standing at a decision point at that instant.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Dict, List, Optional, Sequence, Tuple

from app.policies.goal_based_policies.infrastructure_graph import GraphEdge
from app.policies.tree_search import simulator
from app.policies.tree_search.scenario import Scenario
from app.policies.tree_search.simulator import WorldState

# Holds a train can be given. It stays on its node and decides again when
# the hold is over, so longer holds are built by holding repeatedly — and
# the route is then chosen against what the other trains did meanwhile.
WAIT_MENU: Tuple[int, ...] = (1, 3, 5, 10)

# Most children one node may have. The cross product of several trains
# deciding at once would otherwise run into the hundreds.
MAX_CHILDREN = 24


@dataclass(frozen=True)
class Decision:
    """One train's choice. Exactly one of the two is set: an edge means it
    leaves now, a wait means it stays and re-decides later."""
    wait: int = 0
    edge: Optional[GraphEdge] = None

    @property
    def is_wait(self) -> bool:
        return self.edge is None

    def describe(self) -> Dict[str, object]:
        if self.edge is None:
            return {"action": "wait", "wait": int(self.wait)}
        return {
            "action": "go",
            "to": [int(self.edge.to_cell[0]), int(self.edge.to_cell[1])],
            "travel_time": int(self.edge.travel_time),
        }


JointAction = Tuple[Tuple[int, Decision], ...]


def options_for(
    scenario: Scenario, state: WorldState, handle: int
) -> List[Decision]:
    """Everything this train may do right now, cheapest route first.

    Routes come before holds and are ordered by travel time, so option 0 is
    always "go the cheapest way, without holding" — a stable convention for
    tie-breaking and for reading traces.
    """
    train = state.train(handle)
    data = scenario.trains[handle]
    edges = scenario.onward_edges(train.cell, train.heading)
    if not edges:
        return []

    # A branch that can no longer reach the next booked stop is not a
    # choice, it is a way of stranding the train, so it never enters the
    # tree. If *no* branch reaches it the train is already lost; the
    # branches stay in so the run can still be played out and scored.
    #
    # The survivors are ordered by what the whole detour costs — this leg
    # plus the way on from where it lands — not by the length of the next
    # hop, so option 0 is "the cheapest way towards the next stop" and a
    # branch that doubles back never leads. Ordering only; every reachable
    # branch stays in the tree, and nothing here scores a state.
    if train.stop_index < len(data.stops):
        target = data.stops[train.stop_index]
        ranked: List[Tuple[int, int, int, GraphEdge]] = []
        for edge in edges:
            onward = scenario.cost_to_go(
                edge.to_cell, edge.in_direction, target)
            if onward is None:
                continue
            ranked.append((
                edge.travel_time + onward, edge.travel_time,
                edge.out_direction, edge,
            ))
        ranked.sort(key=lambda item: item[:3])
        edges = [item[3] for item in ranked] or list(edges)

    decisions = [Decision(wait=0, edge=edge) for edge in edges]

    # Holding is only a decision where it achieves something, and only once
    # the train is running: a train at its origin waiting for its departure
    # slot is not making a choice, it is waiting for the timetable.
    if train.underway and scenario.can_hold(train.cell, train.heading):
        decisions.extend(
            Decision(wait=wait)
            for wait in WAIT_MENU
            if state.step + wait < scenario.horizon
        )
    return decisions


def joint_actions(
    scenario: Scenario,
    state: WorldState,
    handles: Sequence[int],
    max_children: int = MAX_CHILDREN,
) -> List[JointAction]:
    """Every combination of the deciding trains' options, capped.

    When the product is too large the *longest holds* are dropped first,
    from whichever train offers the most options. A hold is never lost by
    that: the train re-decides at the same node, so a long hold is only
    spread over several levels of the tree. Dropping a direction would
    remove an outcome from the tree for good, which is why directions are
    never touched.
    """
    per_train = {handle: options_for(scenario, state, handle)
                 for handle in handles}
    per_train = {h: options for h, options in per_train.items() if options}
    if not per_train:
        return []

    def size(table: Dict[int, List[Decision]]) -> int:
        total = 1
        for options in table.values():
            total *= len(options)
        return total

    while size(per_train) > max_children:
        trimmable = [
            handle for handle, options in per_train.items()
            if sum(1 for option in options if option.is_wait) > 0
        ]
        if not trimmable:
            break
        widest = max(trimmable, key=lambda h: (len(per_train[h]), h))
        per_train[widest] = per_train[widest][:-1]

    ordered = sorted(per_train)
    combinations = product(*(per_train[handle] for handle in ordered))
    return [
        tuple((handle, decision) for handle, decision in zip(ordered, combo))
        for combo in combinations
    ]


def apply(
    scenario: Scenario, state: WorldState, action: JointAction
) -> WorldState:
    """The state that follows a joint action: hand out the decisions, then
    let time run until the next real choice."""
    after = simulator.apply_decisions(scenario, state, dict(action))
    return advance_to_choice(scenario, simulator.run(scenario, after))


def advance_to_choice(scenario: Scenario, state: WorldState) -> WorldState:
    """Run forward past everything that is not a genuine choice.

    A train leaving its origin down the only track available, or rolling
    through a node with one way onward, decides nothing — putting such
    states in the tree would bury the real branch points under chains of
    single-child nodes. They are executed here instead, so every node of
    the tree is a point where something was actually chosen.
    """
    state = simulator.run(scenario, state)
    while not simulator.is_terminal(scenario, state):
        handles = simulator.deciding(scenario, state)
        if not handles:
            break
        actions = joint_actions(scenario, state, handles)
        if len(actions) != 1:
            break
        after = simulator.apply_decisions(scenario, state, dict(actions[0]))
        state = simulator.run(scenario, after)
    return state


def describe(action: JointAction) -> List[Dict[str, object]]:
    """A joint action as plain data, for traces and for the HMI."""
    return [
        {"handle": int(handle), **decision.describe()}
        for handle, decision in action
    ]


__all__ = [
    "MAX_CHILDREN",
    "WAIT_MENU",
    "Decision",
    "JointAction",
    "advance_to_choice",
    "apply",
    "describe",
    "joint_actions",
    "options_for",
]
