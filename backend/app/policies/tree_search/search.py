"""The anytime best-first tree search.

Nodes are states of the railway, branches are joint decisions. Unexpanded
nodes across the *whole* tree sit in one frontier, ordered by

    priority = value + c / sqrt(1 + siblings already expanded)

The first term is what the networks make of the state; the second is a
small bonus for a corner of the tree that has barely been touched, so the
search cannot collapse into one line before it knows anything. Every value
is a utility in [0, 1], so `c` means the same thing everywhere.

The search never "finishes". It is stepped by a budget, always has a best
complete solution to hand, and is re-rooted when a decision is actually
executed so that everything already explored below the branch reality took
is kept and the rest released.

Nothing here completes a plan or simulates ahead to judge a node: a node's
value is the networks' verdict on the state itself. Terminal states are not
guessed at all — they are measured.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from app.policies.tree_search import actions as action_model
from app.policies.tree_search import metrics as metric_model
from app.policies.tree_search import observation as observation_model
from app.policies.tree_search import simulator
from app.policies.tree_search.actions import JointAction
from app.policies.tree_search.scenario import Scenario
from app.policies.tree_search.simulator import Outcome, WorldState

EXPLORATION = 0.15
MAX_NODES = 20_000
# Expansions between dives (see `TreeSearch._should_dive`). Small enough
# that solutions keep being refreshed, large enough that most of the budget
# still goes on the frontier.
DIVE_INTERVAL = 8
# Fraction of the frontier released when the node cap is reached — the worst
# unexpanded leaves, which are the ones the search was never going to look
# at again.
TRIM_FRACTION = 0.25


@dataclass
class Node:
    identifier: int
    state: WorldState
    parent: Optional[int]
    action: Optional[JointAction]
    depth: int
    values: Dict[str, float]
    value: float
    terminal: bool
    outcome: Optional[Outcome] = None
    children: Dict[int, int] = field(default_factory=dict)  # action -> node
    child_actions: Tuple[JointAction, ...] = ()
    expanded: bool = False
    expanded_children: int = 0


@dataclass
class Solution:
    """A complete run the search found, and how it got there."""
    node: int
    outcome: Outcome
    utilities: Dict[str, float]
    weighted: float
    actions: List[JointAction]

    def to_dict(self) -> Dict[str, object]:
        return {
            "weighted": self.weighted,
            "utilities": dict(self.utilities),
            "outcome": self.outcome.to_dict(),
            "decisions": len(self.actions),
        }


class TreeSearch:
    """One growing, continuously pruned tree over one scenario."""

    def __init__(
        self,
        scenario: Scenario,
        models: Optional[Dict[str, object]] = None,
        weights: Optional[Dict[str, float]] = None,
        exploration: float = EXPLORATION,
        max_children: int = action_model.MAX_CHILDREN,
        max_nodes: int = MAX_NODES,
        root_state: Optional[WorldState] = None,
        dive_interval: int = DIVE_INTERVAL,
    ):
        self.scenario = scenario
        self.models = dict(models or {})
        self.weights = dict(weights or {name: 1.0 for name in metric_model.METRICS})
        self.exploration = float(exploration)
        self.max_children = int(max_children)
        self.max_nodes = int(max_nodes)
        self.dive_interval = max(1, int(dive_interval))

        self.nodes: Dict[int, Node] = {}
        self._next_id = 0
        self._frontier: List[Tuple[float, int, int, int]] = []
        self._by_key: Dict[Tuple, int] = {}
        self._tick = 0
        self.best: Optional[int] = None
        self.expansions = 0
        self.saturated = False

        # What a replay of this search has to start from: the state before
        # the forced opening moves, so `plan.replay` walks the same ground.
        self.replay_from = (
            root_state if root_state is not None
            else simulator.initial_state(scenario)
        )
        state = action_model.advance_to_choice(scenario, self.replay_from)
        self.root = self._add(state, parent=None, action=None, depth=0)

    # -------------------------------------------------------------- values

    def _evaluate(self, states: Sequence[WorldState]) -> List[Dict[str, float]]:
        """Value every state: measured where the run is over, predicted
        otherwise. States with no model behind them score 0.5 — the search
        is then undirected, which is exactly what generation zero is."""
        results: List[Dict[str, float]] = [{} for _ in states]
        pending: List[int] = []
        for index, state in enumerate(states):
            if simulator.is_terminal(self.scenario, state):
                results[index] = metric_model.utilities(
                    simulator.outcome(self.scenario, state))
            else:
                pending.append(index)
        if pending and self.models:
            observations = [
                observation_model.encode(self.scenario, states[index])
                for index in pending
            ]
            from app.policies.tree_search.net import evaluate_states

            predicted = evaluate_states(self.models, observations)
            for position, index in enumerate(pending):
                results[index] = {
                    name: float(values[position])
                    for name, values in predicted.items()
                }
        else:
            for index in pending:
                results[index] = {
                    name: 0.5 for name in metric_model.METRICS
                }
        return results

    def _weighted(self, values: Dict[str, float]) -> float:
        return metric_model.combine(values, self.weights)

    # --------------------------------------------------------------- nodes

    def _add(
        self,
        state: WorldState,
        parent: Optional[int],
        action: Optional[JointAction],
        depth: int,
        values: Optional[Dict[str, float]] = None,
    ) -> int:
        if values is None:
            values = self._evaluate([state])[0]
        terminal = simulator.is_terminal(self.scenario, state)
        identifier = self._next_id
        self._next_id += 1
        node = Node(
            identifier=identifier,
            state=state,
            parent=parent,
            action=action,
            depth=depth,
            values=values,
            value=self._weighted(values),
            terminal=terminal,
            outcome=simulator.outcome(self.scenario, state) if terminal else None,
        )
        self.nodes[identifier] = node
        self._by_key[state.key()] = identifier
        if terminal:
            self._offer_solution(node)
        else:
            self._push(node)
        return identifier

    def _push(self, node: Node) -> None:
        """Queue a node.

        Ties break by depth first, then by age. Depth, because a search
        whose values are all alike — an untrained network, or the very
        first generation — would otherwise fan out breadth-first and never
        finish a single run; diving gets complete solutions to learn from.
        Age, because children are queued cheapest-route-first, so the
        oldest sibling is the "go the obvious way, do not hold" branch: the
        untrained search then behaves like the sensible default and
        improves on it, instead of diving into the longest hold it was
        offered."""
        self._tick += 1
        heapq.heappush(
            self._frontier,
            (-self._priority(node), -node.depth, self._tick, node.identifier),
        )

    def _priority(self, node: Node) -> float:
        """Value plus a bonus for a barely-touched corner of the tree.

        The bonus decays with the number of siblings already expanded, so
        the first look into a branch is encouraged and the tenth is not.
        Deliberately monotone: a queued priority can then only ever be too
        *high*, which is what makes the lazy re-ranking in `_pop` exact.
        """
        if node.parent is None:
            return node.value + self.exploration
        parent = self.nodes.get(node.parent)
        if parent is None:
            return node.value
        return node.value + self.exploration / math.sqrt(
            1 + parent.expanded_children
        )

    def _offer_solution(self, node: Node) -> None:
        if node.outcome is None:
            return
        if self.best is None or node.value > self.nodes[self.best].value:
            self.best = node.identifier

    # ------------------------------------------------------------- growing

    def run(self, node_budget: int = 64) -> int:
        """Expand up to `node_budget` nodes. Returns how many it managed."""
        done = 0
        while done < node_budget:
            node = self._pop()
            if node is None:
                break
            self._expand(node)
            done += 1
            if self._should_dive():
                done += self._dive(node, node_budget - done)
            if len(self.nodes) >= self.max_nodes:
                self._trim()
        return done

    def _should_dive(self) -> bool:
        """Is it time to drive a branch through to the end?

        A node's value is an estimate of the *end* it leads to, and it does
        not shrink as the run progresses — so a shallow state looks exactly
        as good as the best state below it, and pure best-first spreads
        sideways forever without ever finishing a run. Diving fixes that:
        every so often, and always while no complete run is known, the
        search follows its own preference straight down to the end.

        The dive does not evaluate anything: the states it passes are
        ordinary nodes, valued by the networks like any other, and only the
        terminal it reaches is measured. It is how solutions are *found*,
        not how they are judged.
        """
        return self.best is None or self.expansions % self.dive_interval == 0

    def _dive(self, node: Node, budget: int) -> int:
        """Follow the most promising child down to a complete run."""
        used = 0
        current = node
        while used < budget:
            if current.terminal or not current.children:
                break
            options = [
                self.nodes[child] for child in current.children.values()
                if child in self.nodes
            ]
            open_options = [child for child in options if not child.expanded]
            if not open_options:
                break
            best = max(open_options, key=lambda child: (child.value, -child.depth))
            if best.terminal:
                break
            self._expand(best)
            used += 1
            current = best
        return used

    def _pop(self) -> Optional[Node]:
        """The best unexpanded node, re-ranking stale entries as it goes.

        The exploration bonus shrinks as a node's siblings get expanded, so
        a queued priority can only ever be too high; such an entry is put
        back with its current value instead of being trusted.
        """
        for _ in range(len(self._frontier) + 1):
            if not self._frontier:
                return None
            priority, _depth, _tick, identifier = heapq.heappop(self._frontier)
            node = self.nodes.get(identifier)
            if node is None or node.expanded or node.terminal:
                continue
            current = self._priority(node)
            if current < -priority - 1e-9:
                self._push(node)
                continue
            return node
        return None

    def _expand(self, node: Node) -> None:
        node.expanded = True
        self.expansions += 1
        handles = simulator.deciding(self.scenario, node.state)
        candidates = action_model.joint_actions(
            self.scenario, node.state, handles, self.max_children
        )
        if not candidates:
            return
        node.child_actions = tuple(candidates)

        fresh_states: List[WorldState] = []
        fresh_slots: List[int] = []
        reused: Dict[int, int] = {}
        for slot, joint in enumerate(candidates):
            child_state = action_model.apply(self.scenario, node.state, joint)
            known = self._by_key.get(child_state.key())
            if known is not None and known != node.identifier:
                reused[slot] = known
                continue
            fresh_states.append(child_state)
            fresh_slots.append(slot)

        values = self._evaluate(fresh_states) if fresh_states else []
        for position, slot in enumerate(fresh_slots):
            child = self._add(
                fresh_states[position], parent=node.identifier,
                action=candidates[slot], depth=node.depth + 1,
                values=values[position],
            )
            node.children[slot] = child
        for slot, known in reused.items():
            node.children[slot] = known

        parent = self.nodes.get(node.parent) if node.parent is not None else None
        if parent is not None:
            parent.expanded_children += 1

    def _trim(self) -> None:
        """Release the least promising unexpanded leaves.

        Only frontier nodes are dropped, and only ones nothing hangs off, so
        the tree stays consistent — what is lost is the *option* of looking
        there later, which is the honest cost of a memory bound.
        """
        # Stale entries first: a node can be queued twice (once when it is
        # created, once when `_pop` re-ranks it), so the heap outlives the
        # nodes it names. Dropping one of those would take an *expanded*
        # node with it and orphan its children.
        live = [
            entry for entry in self._frontier
            if entry[3] in self.nodes
            and not self.nodes[entry[3]].expanded
            and not self.nodes[entry[3]].children
        ]
        if not live:
            self._frontier = []
            self.saturated = True
            return
        keep = int(len(live) * (1.0 - TRIM_FRACTION))
        ordered = sorted(live)  # best first: priorities are negated
        survivors, dropped = ordered[:keep], ordered[keep:]
        for _priority, _depth, _tick, identifier in dropped:
            node = self.nodes.pop(identifier, None)
            if node is None:
                continue
            self._by_key.pop(node.state.key(), None)
            parent = self.nodes.get(node.parent) if node.parent is not None else None
            if parent is not None:
                for slot, child in list(parent.children.items()):
                    if child == identifier:
                        del parent.children[slot]
        heapq.heapify(survivors)
        self._frontier = survivors

    # ------------------------------------------------------------ the plan

    def best_solution(self) -> Optional[Solution]:
        """The best complete run found so far, with the decisions that lead
        to it. None until one exists."""
        if self.best is None:
            return None
        node = self.nodes.get(self.best)
        if node is None or node.outcome is None:
            return None
        path: List[JointAction] = []
        cursor: Optional[Node] = node
        while cursor is not None and cursor.parent is not None:
            if cursor.action is not None:
                path.append(cursor.action)
            cursor = self.nodes.get(cursor.parent)
        path.reverse()
        return Solution(
            node=node.identifier, outcome=node.outcome, utilities=node.values,
            weighted=node.value, actions=path,
        )

    def best_action(self) -> Optional[JointAction]:
        """The decision to take at the root, on the best path known."""
        solution = self.best_solution()
        if solution is not None and solution.actions:
            return solution.actions[0]
        root = self.nodes[self.root]
        if not root.children:
            return None
        slot = max(
            root.children,
            key=lambda s: self.nodes[root.children[s]].value,
        )
        return root.child_actions[slot]

    # ---------------------------------------------------------- re-rooting

    def reroot(self, action: JointAction) -> bool:
        """Move the root onto the child that `action` leads to.

        Everything explored below it is kept; the rest is released. False
        when that branch was never explored — the caller then starts a
        fresh search, which is also what a world that diverged from the
        model needs.
        """
        root = self.nodes[self.root]
        for slot, child in root.children.items():
            if root.child_actions[slot] == action:
                return self._reroot_to(child)
        return False

    def reroot_to_state(self, state: WorldState) -> bool:
        """Re-root onto an explored state, matched exactly."""
        known = self._by_key.get(state.key())
        if known is None or known not in self.nodes:
            return False
        return self._reroot_to(known)

    def _reroot_to(self, identifier: int) -> bool:
        keep: Dict[int, Node] = {}
        self.replay_from = self.nodes[identifier].state if identifier in self.nodes else self.replay_from
        stack = [identifier]
        while stack:
            current = stack.pop()
            node = self.nodes.get(current)
            if node is None or current in keep:
                continue
            keep[current] = node
            stack.extend(node.children.values())
        if identifier not in keep:
            return False

        keep[identifier].parent = None
        keep[identifier].action = None
        shift = keep[identifier].depth
        for node in keep.values():
            node.depth -= shift
        self.nodes = keep
        self._by_key = {node.state.key(): key for key, node in keep.items()}
        self.root = identifier
        self._frontier = []
        self.best = None
        for node in keep.values():
            if node.terminal:
                self._offer_solution(node)
            elif not node.expanded:
                self._push(node)
        return True

    # --------------------------------------------------------------- stats

    def stats(self) -> Dict[str, object]:
        solution = self.best_solution()
        return {
            "nodes": len(self.nodes),
            "frontier": len(self._frontier),
            "expansions": self.expansions,
            "depth": max((n.depth for n in self.nodes.values()), default=0),
            "saturated": self.saturated,
            "has_solution": solution is not None,
            "best": None if solution is None else solution.to_dict(),
            "weights": metric_model.normalised_weights(self.weights),
            "models": sorted(self.models),
        }


__all__ = [
    "DIVE_INTERVAL", "EXPLORATION", "MAX_NODES", "Node", "Solution",
    "TreeSearch",
]
