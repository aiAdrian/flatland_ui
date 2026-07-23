"""Policy-divergence event graph — the holistic "what would each policy do?" view.

Runs all participating policies in LOCKSTEP on one shared state for the
whole run (root → all trains done / episode end). While they agree, the
world advances and no node is created. Where they disagree, one child
node per distinct resulting future is created and annotated with the
policies that produced it; expansion then continues on every child with
ALL policies again (`docs/plans/policy-divergence-event-graph.md` §1).

Divergence is decided on RESULTING STATES, not on actions: differing
proposals are stepped on probe forks and grouped by state hash, so two
policies that express the same physical move differently never create a
branch. Nodes are additionally created when a train reaches its target
and when a deadlock appears.

Machinery (forking, state-hash dedup, event detection, budgets, and the
Flatland cache sweep that keeps forked envs from leaking) is shared with
`action_event_graph`, which measures the exhaustive upper bound.

Standalone experiment:
    cd backend && python -m app.core.policy_divergence_graph --guided-demo
"""
from __future__ import annotations

import argparse
import gc
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from flatland.envs.rail_env import RailEnv

from app.core.action_event_graph import (
    _all_done,
    _build_guided_demo_env,
    _build_test_env,
    _clear_flatland_method_caches,
    _done_handles,
    _state_name,
    blob_to_env,
    env_to_blob,
    hard_deadlocked_agents,
    shared_distance_map,
    state_hash,
)
from flatland.core.grid.grid4_utils import get_new_position
from flatland.envs.fast_methods import fast_argmax, fast_count_nonzero

from app.core.cell_classifier import (
    ACTION_NAMES,
    ACTION_STOP_MOVING as STOP_MOVING_ACTION,
    _get_transitions,
    classify_cell_at,
)
from app.policies.base import Policy

PolicyFactory = Callable[[], Policy]
PolicyEntry = Tuple[str, PolicyFactory]

# Policies excluded from the graph by default. `random` is
# nondeterministic: it disagrees with everything nearly every step, which
# both explodes the graph and makes it irreproducible (plan §6 P2).
_EXCLUDED_BY_DEFAULT = {"random"}


def default_participants() -> List[PolicyEntry]:
    """Deterministic, scenario-capable policies from the registry."""
    from app.policies.registry import scenario_policy_factories

    return [
        (pid, factory)
        for pid, factory in scenario_policy_factories().items()
        if pid not in _EXCLUDED_BY_DEFAULT
    ]


# ── Graph model ─────────────────────────────────────────────────────


@dataclass
class PolicyGraphNode:
    id: str
    step: int                       # env._elapsed_steps at this node
    event: str                      # root | divergence | arrival | deadlock
    agents: Dict[str, dict]
    arrived: List[int]              # cumulative DONE handles
    deadlocked: List[int]           # cumulative hard-deadlocked handles
    terminal: bool = False          # all trains done / episode over
    truncated: bool = False         # expansion cut by a budget

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "step": int(self.step),
            "event": self.event,
            "agents": self.agents,
            "arrived": list(self.arrived),
            "deadlocked": list(self.deadlocked),
            "terminal": bool(self.terminal),
            "truncated": bool(self.truncated),
        }


@dataclass
class PolicyGraphEdge:
    from_id: str
    to_id: str
    steps: int                      # consensus steps compressed into the edge
    policy_ids: List[str]           # policies whose proposal led here
    # Per-agent actions of THIS branch, for the agents the policies
    # disagreed about. Empty on consensus (arrival/deadlock) edges.
    action_diff: Dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_id,
            "to": self.to_id,
            "steps": int(self.steps),
            "policy_ids": list(self.policy_ids),
            "action_diff": {int(h): a for h, a in self.action_diff.items()},
        }


@dataclass
class PolicyGraphLimits:
    max_depth: Optional[int] = None  # steps beyond the root; None = episode end
    max_nodes: int = 2000
    max_wall_s: float = 300.0


@dataclass
class PolicyGraphStats:
    nodes: int = 0
    edges: int = 0
    divergences: int = 0            # real branch points (states differed)
    # Proposals differed as ACTIONS but produced the identical state —
    # branches avoided by the compare-states rule.
    false_divergences: int = 0
    # Steps where the policies still disagreed about exactly the trains
    # already under dispute — the same decision continuing, not a new one.
    ongoing_dispute_steps: int = 0
    # Disagreements about trains that are mid-section, where no choice is
    # left to make (see `decision_cells_only`).
    non_decision_disputes: int = 0
    # Branches abandoned at a deadlock: a hard-deadlocked train can never
    # reach its target, so nothing downstream is a usable plan.
    pruned_deadlock_branches: int = 0
    merges: int = 0                 # edges into an already-existing node
    arrival_events: int = 0
    deadlock_events: int = 0
    truncated_nodes: int = 0
    max_depth_reached: int = 0
    forks: int = 0
    steps_simulated: int = 0
    policy_errors: int = 0
    build_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class PolicyDivergenceGraph:
    root_id: str
    policy_ids: List[str]
    nodes: Dict[str, PolicyGraphNode] = field(default_factory=dict)
    edges: List[PolicyGraphEdge] = field(default_factory=list)
    stats: PolicyGraphStats = field(default_factory=PolicyGraphStats)
    # Static per-agent info, sent once instead of per node: targets never
    # change during an episode and every node would otherwise repeat them.
    num_agents: int = 0
    agent_targets: Dict[int, List[int]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_id": self.root_id,
            "policy_ids": list(self.policy_ids),
            "num_agents": int(self.num_agents),
            "agent_targets": {int(h): list(t) for h, t in self.agent_targets.items()},
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "stats": self.stats.to_dict(),
        }


# ── Builder ─────────────────────────────────────────────────────────


class PolicyDivergenceGraphBuilder:
    """Breadth-first expansion of the policy-divergence graph.

    The base env is never mutated: the root state is serialized once and
    every expansion works on a restored copy.
    """

    def __init__(
        self,
        base_env: RailEnv,
        participants: Optional[List[PolicyEntry]] = None,
        limits: PolicyGraphLimits = PolicyGraphLimits(),
        new_disputes_only: bool = True,
        decision_cells_only: bool = True,
        prune_deadlocks: bool = True,
    ):
        self._base_env = base_env
        self._participants = participants or default_participants()
        self._limits = limits
        self._new_disputes_only = new_disputes_only
        self._decision_cells_only = decision_cells_only
        self._prune_deadlocks = prune_deadlocks
        self._nodes: Dict[str, PolicyGraphNode] = {}
        self._edges: List[PolicyGraphEdge] = []
        self._stats = PolicyGraphStats()
        self._deadline = 0.0
        self._root_step = 0
        self._depth_cap = 0
        # True when the depth cap IS the end of the episode: reaching it
        # means the run finished, not that we cut it short.
        self._depth_cap_is_episode_end = limits.max_depth is None

    # ── public API ──────────────────────────────────────────────────

    def build(self) -> PolicyDivergenceGraph:
        with shared_distance_map(self._base_env):
            return self._build()

    def _build(self) -> PolicyDivergenceGraph:
        t0 = time.perf_counter()
        self._deadline = t0 + self._limits.max_wall_s

        root_blob = env_to_blob(self._base_env)
        self._stats.forks += 1
        env = blob_to_env(root_blob)
        self._root_step = int(getattr(env, "_elapsed_steps", 0) or 0)

        if self._limits.max_depth is not None:
            self._depth_cap = self._limits.max_depth
        else:
            max_ep = int(getattr(env, "_max_episode_steps", 0) or 0)
            self._depth_cap = max(1, max_ep - self._root_step) if max_ep else 1000

        root, _ = self._node_for_state(env, "root")
        # (node id, env blob, depth, owner policy, handles under dispute)
        queue: deque = deque([(root.id, root_blob, 0, None, frozenset())])
        expansions = 0

        while queue:
            over_budget = (
                len(self._nodes) >= self._limits.max_nodes
                or time.perf_counter() > self._deadline
            )
            if over_budget:
                # Never truncate silently: flag every unexpanded frontier node.
                for nid, _blob, _depth, _owner, _disputed in queue:
                    node = self._nodes[nid]
                    if not node.terminal:
                        node.truncated = True
                break
            nid, blob, depth, owner, disputed = queue.popleft()
            env = blob_to_env(blob)
            self._stats.forks += 1
            self._expand(nid, env, depth, owner, disputed, queue)
            del env
            expansions += 1
            if expansions % 20 == 0:
                _clear_flatland_method_caches()
                gc.collect()

        _clear_flatland_method_caches()
        gc.collect()

        self._stats.nodes = len(self._nodes)
        self._stats.edges = len(self._edges)
        self._stats.truncated_nodes = sum(
            1 for n in self._nodes.values() if n.truncated
        )
        self._stats.max_depth_reached = max(
            (n.step - self._root_step for n in self._nodes.values()), default=0,
        )
        self._stats.build_seconds = time.perf_counter() - t0
        return PolicyDivergenceGraph(
            root_id=root.id,
            policy_ids=[pid for pid, _f in self._participants],
            nodes=self._nodes,
            edges=self._edges,
            stats=self._stats,
            num_agents=len(self._base_env.agents),
            agent_targets=self._agent_targets(self._base_env),
        )

    @staticmethod
    def _agent_targets(env: RailEnv) -> Dict[int, List[int]]:
        """Handle → [row, col] of the agent's target (static per episode)."""
        out: Dict[int, List[int]] = {}
        for h, agent in enumerate(env.agents):
            target = getattr(agent, "target", None)
            if target is None:
                continue
            try:
                out[int(h)] = [int(target[0]), int(target[1])]
            except (TypeError, ValueError, IndexError):
                continue
        return out

    # ── expansion ───────────────────────────────────────────────────

    def _expand(
        self,
        node_id: str,
        env: RailEnv,
        depth: int,
        owner: Optional[str],
        disputed: frozenset,
        queue: deque,
    ) -> None:
        """Advance one node in lockstep until the policies diverge anew.

        Consensus steps are compressed into the outgoing edge; arrivals
        and deadlocks emit chain nodes on the way. On a new divergence
        the children are enqueued and this returns.

        ``owner`` — the policy whose proposal created this branch; it
        drives while a dispute persists.
        ``disputed`` — handles under an unresolved disagreement here. A
        disagreement about exactly these trains is the *same* decision
        continuing (e.g. one policy holding a train while another wants
        to run it) and must not re-branch every step; only a train that
        is newly in dispute marks a new decision moment.
        """
        if self._prune_deadlocks and self._nodes[node_id].deadlocked:
            # Already a dead end (e.g. the live session is deadlocked at
            # the root) — nothing downstream can be a plan.
            self._nodes[node_id].terminal = True
            return

        policies = self._fresh_policies(env)
        if not policies:
            self._nodes[node_id].terminal = True
            return

        cur_id = node_id
        steps_since = 0
        prev_done = _done_handles(env)
        prev_dl = hard_deadlocked_agents(env)
        disputed = set(disputed)

        try:
            while True:
                if _all_done(env):
                    self._nodes[cur_id].terminal = True
                    return
                if depth >= self._depth_cap:
                    if self._depth_cap_is_episode_end:
                        self._nodes[cur_id].terminal = True
                    else:
                        self._nodes[cur_id].truncated = True
                    return
                if time.perf_counter() > self._deadline:
                    self._nodes[cur_id].truncated = True
                    return

                handles = env.get_agent_handles()
                observations = {h: env for h in handles}

                proposals: Dict[str, Dict[int, int]] = {}
                for pid, policy in list(policies.items()):
                    policy.start_step()
                    actions = self._policy_actions(policy, handles, observations)
                    if actions is None:
                        self._stats.policy_errors += 1
                        del policies[pid]
                        continue
                    proposals[pid] = actions
                if not proposals:
                    self._nodes[cur_id].terminal = True
                    return

                # Group by proposed action first (cheap); only distinct
                # action dicts need a probe fork to reveal their state.
                by_action: Dict[tuple, List[str]] = {}
                action_of: Dict[tuple, Dict[int, int]] = {}
                for pid, actions in proposals.items():
                    key = tuple(sorted(actions.items()))
                    by_action.setdefault(key, []).append(pid)
                    action_of[key] = actions

                branch_groups: Optional[Dict[str, dict]] = None
                if len(by_action) == 1:
                    actions = next(iter(action_of.values()))
                    disputed = set()
                else:
                    # Actions differ — probe each on a fork and group by
                    # the STATE it produces (plan §6 P1).
                    by_state = self._probe_states(env, by_action, action_of)
                    if not by_state:
                        self._nodes[cur_id].terminal = True
                        return
                    if len(by_state) == 1:
                        # Same future despite different actions.
                        self._stats.false_divergences += 1
                        actions = next(iter(by_state.values()))["actions"]
                        disputed = set()
                    else:
                        all_disputed = set(self._differing_handles(
                            [g["actions"] for g in by_state.values()]
                        ))
                        now_disputed = all_disputed
                        if self._decision_cells_only:
                            # What each disputed train is being asked to do
                            # decides *where* that decision legitimately
                            # belongs (hold → before the switch, route → on it).
                            proposed = {
                                h: {g["actions"].get(h) for g in by_state.values()}
                                for h in all_disputed
                            }
                            now_disputed = {
                                h for h in all_disputed
                                if self._at_decision_point(env, h, proposed[h])
                            }
                        owner_actions = proposals.get(owner) if owner else None
                        if not now_disputed and owner_actions is not None:
                            # Every disputed train is committed mid-section:
                            # a timing difference, not a routing decision, so
                            # this world keeps following the policy that owns
                            # it rather than forking again.
                            self._stats.non_decision_disputes += 1
                            actions = owner_actions
                            disputed = set()
                        elif not now_disputed:
                            # Same situation, but this world has no owner yet
                            # (the root). Picking a policy here would silently
                            # decide which future the whole graph shows — the
                            # result would depend on participant order — so we
                            # branch instead and let each policy own a world.
                            branch_groups = by_state
                            disputed = all_disputed
                        elif self._new_disputes_only and not (now_disputed - disputed):
                            # Same trains still in dispute → the decision
                            # already branched on, continuing. The owner
                            # drives; do not create another node.
                            self._stats.ongoing_dispute_steps += 1
                            actions = (
                                proposals.get(owner)
                                or next(iter(by_state.values()))["actions"]
                            )
                            disputed = now_disputed
                        else:
                            branch_groups = by_state
                            disputed = now_disputed

                if branch_groups is not None:
                    self._stats.divergences += 1
                    for p in policies.values():
                        p.end_step()
                    self._emit_children(
                        cur_id, branch_groups, steps_since, depth,
                        disputed, prev_done, prev_dl, queue,
                    )
                    return

                # Advance this branch by one step.
                if not self._step(env, actions):
                    self._nodes[cur_id].terminal = True
                    return
                for p in policies.values():
                    p.end_step()
                depth += 1
                steps_since += 1
                cur_id, steps_since, prev_done, prev_dl, stop = self._emit_events(
                    env, cur_id, steps_since, prev_done, prev_dl
                )
                if stop:
                    return
        finally:
            for p in policies.values():
                try:
                    p.end_episode()
                except Exception:
                    pass

    @staticmethod
    def is_hold_point(env: RailEnv, position, direction: int) -> bool:
        """Can a train usefully *wait* here?

        Yes when the NEXT cell is a junction another train may need, so
        that stopping short of it keeps that junction free. There are two
        approaches to the same junction and they classify differently —
        accepting only one of them halves the hold points and guts the
        graph:

        * **Converging side — `MERGING`.** This heading has a single exit
          through the next cell, but another heading into it has several
          (`opp_dir_options > 1`): a train coming from the other side has
          an alternative route. Waiting here leaves it that alternative;
          rolling in takes it away and can deadlock both.
        * **Diverging side — the next cell is a `SWITCH`.** Here *this*
          train has the options, but stopping short still keeps the
          junction clear for everyone else. These cells classify as
          FORWARD_ONLY, **not** MERGING (the MERGING test needs the next
          cell to have one exit for this heading; a switch has several),
          so they must be detected explicitly.

        No while standing ON the junction: that blocks it for every other
        train — an operating error, not an option. No mid-section either:
        the train is committed and cannot re-route, so a disagreement
        there is a timing difference.
        """
        cell = classify_cell_at(env, position, direction)
        if cell == "SWITCH":
            return False
        if cell == "MERGING":
            return True
        transitions = _get_transitions(env, position[0], position[1], direction)
        if fast_count_nonzero(transitions) != 1:
            return False
        next_dir = fast_argmax(transitions)
        nr, nc = get_new_position(position, next_dir)
        if not (0 <= nr < env.height and 0 <= nc < env.width):
            return False
        return classify_cell_at(env, (nr, nc), next_dir) == "SWITCH"

    @classmethod
    def _at_decision_point(cls, env: RailEnv, handle: int, actions: set) -> bool:
        """True if this train still has a real choice to make right now.

        The two kinds of decision live on different cells: a **hold**
        belongs before the junction (see :meth:`is_hold_point`), a **route
        choice** can only be taken ON the switch, where the exit direction
        is picked.

        Fails open: if the cell cannot be classified we treat it as a
        decision point rather than silently dropping a divergence.
        """
        agent = env.agents[handle]
        if agent.position is None or agent.direction is None:
            return True
        position = (int(agent.position[0]), int(agent.position[1]))
        direction = int(agent.direction)
        try:
            if STOP_MOVING_ACTION in actions:
                return cls.is_hold_point(env, position, direction)
            return classify_cell_at(env, position, direction) in ("SWITCH", "MERGING")
        except Exception:
            return True

    def _probe_states(
        self,
        env: RailEnv,
        by_action: Dict[tuple, List[str]],
        action_of: Dict[tuple, Dict[int, int]],
    ) -> Dict[str, dict]:
        """Step each distinct proposal on its own fork and group the
        results by resulting state hash (the divergence test)."""
        parent_blob = env_to_blob(env)
        self._stats.forks += 1
        by_state: Dict[str, dict] = {}
        for key, pids in by_action.items():
            probe = blob_to_env(parent_blob)
            self._stats.forks += 1
            if not self._step(probe, action_of[key]):
                continue
            group = by_state.setdefault(
                state_hash(probe),
                {"env": probe, "policy_ids": [], "actions": action_of[key]},
            )
            group["policy_ids"].extend(pids)
        return by_state

    def _emit_children(
        self,
        cur_id: str,
        by_state: Dict[str, dict],
        steps_since: int,
        depth: int,
        disputed: set,
        prev_done: set,
        prev_dl: set,
        queue: deque,
    ) -> None:
        """One child node per distinct future, annotated with the policies
        that produced it and the actions they disagreed about."""
        diff_handles = self._differing_handles(
            [g["actions"] for g in by_state.values()]
        )
        for group in by_state.values():
            child_env = group["env"]
            node, created = self._node_for_state(child_env, "divergence")
            self._add_edge(
                cur_id,
                node.id,
                steps_since + 1,
                group["policy_ids"],
                {
                    h: ACTION_NAMES.get(group["actions"].get(h), "?")
                    for h in diff_handles
                },
            )
            if not created:
                self._stats.merges += 1
                continue
            if set(node.arrived) - prev_done:
                self._stats.arrival_events += 1
            if set(node.deadlocked) - prev_dl:
                self._stats.deadlock_events += 1
            if node.deadlocked and self._prune_deadlocks:
                # Dead end — keep the node so the outcome stays visible,
                # but do not expand it.
                node.terminal = True
                self._stats.pruned_deadlock_branches += 1
                continue
            queue.append((
                node.id, env_to_blob(child_env), depth + 1,
                group["policy_ids"][0], frozenset(disputed),
            ))
            self._stats.forks += 1

    def _emit_events(
        self,
        env: RailEnv,
        cur_id: str,
        steps_since: int,
        prev_done: set,
        prev_dl: set,
    ) -> Tuple[str, int, set, set, bool]:
        """Emit an arrival/deadlock chain node if either set grew.

        Returns (current node id, steps since it, done set, deadlock set,
        stop) where `stop` means the state was already explored elsewhere
        and this branch should end.
        """
        done = _done_handles(env)
        dl = hard_deadlocked_agents(env)
        new_done = done - prev_done
        new_dl = dl - prev_dl
        if not (new_done or new_dl):
            return cur_id, steps_since, prev_done, prev_dl, False

        event = "deadlock" if new_dl else "arrival"
        if new_done:
            self._stats.arrival_events += 1
        if new_dl:
            self._stats.deadlock_events += 1
        node, created = self._node_for_state(env, event)
        self._add_edge(cur_id, node.id, steps_since, [], {})
        if not created:
            self._stats.merges += 1
            return cur_id, steps_since, done, dl, True
        if new_dl and self._prune_deadlocks:
            # Dead end: a hard-deadlocked train can never reach its target,
            # so no plan downstream is usable. Stop here — the node stays
            # in the graph as a visible deadlock outcome.
            node.terminal = True
            self._stats.pruned_deadlock_branches += 1
            return node.id, 0, done, dl, True
        return node.id, 0, done, dl, False

    # ── internals ───────────────────────────────────────────────────

    def _fresh_policies(self, env: RailEnv) -> Dict[str, Policy]:
        """A new policy instance per participant, reset on this env.

        Policies hold per-episode state (DLA rebuilds distance maps), so
        every node expansion gets fresh instances — the same reason
        TrajectoryBranchRunner takes factories rather than instances.
        """
        out: Dict[str, Policy] = {}
        for pid, factory in self._participants:
            try:
                policy = factory()
                policy.reset(env)
                policy.start_episode()
            except Exception:
                self._stats.policy_errors += 1
                continue
            out[pid] = policy
        return out

    def _policy_actions(
        self, policy: Policy, handles, observations
    ) -> Optional[Dict[int, int]]:
        """One policy's joint action as {handle: int}, or None on failure."""
        try:
            raw = policy.act_many(handles, observations)
        except Exception:
            return None
        if not raw:
            return None
        out: Dict[int, int] = {}
        for h, a in raw.items():
            try:
                out[int(h)] = int(a.value)  # IntEnum member
            except AttributeError:
                out[int(h)] = int(a)
        return out

    @staticmethod
    def _differing_handles(action_dicts: List[Dict[int, int]]) -> List[int]:
        """Handles the branches disagree about (the operator-facing diff)."""
        handles = set()
        for d in action_dicts:
            handles.update(d)
        return sorted(
            h for h in handles
            if len({d.get(h) for d in action_dicts}) > 1
        )

    def _step(self, env: RailEnv, actions: Dict[int, int]) -> bool:
        """env.step wrapper; False when the episode is already over."""
        self._stats.steps_simulated += 1
        try:
            env.step({int(h): int(a) for h, a in actions.items()})
            return True
        except Exception as e:
            if "Episode is done" in str(e):
                return False
            raise

    def _node_for_state(
        self, env: RailEnv, event: str
    ) -> Tuple[PolicyGraphNode, bool]:
        """Get-or-create the node for the env's current state (identical
        states are the same node → DAG, reconvergence shows up as a merge)."""
        hid = state_hash(env)
        existing = self._nodes.get(hid)
        if existing is not None:
            return existing, False
        node = PolicyGraphNode(
            id=hid,
            step=int(getattr(env, "_elapsed_steps", 0) or 0),
            event=event,
            agents=self._capture_agents(env),
            arrived=sorted(_done_handles(env)),
            deadlocked=sorted(hard_deadlocked_agents(env)),
        )
        self._nodes[hid] = node
        return node, True

    def _add_edge(
        self,
        from_id: str,
        to_id: str,
        steps: int,
        policy_ids: List[str],
        action_diff: Dict[int, str],
    ) -> None:
        self._edges.append(
            PolicyGraphEdge(from_id, to_id, steps, list(policy_ids), action_diff)
        )

    @staticmethod
    def _capture_agents(env: RailEnv) -> Dict[str, dict]:
        """Same shape as ScenarioBuilder._capture_env_state, plus state."""
        out: Dict[str, dict] = {}
        for h, agent in enumerate(env.agents):
            if agent.position is None:
                continue
            out[str(h)] = {
                "pos": (int(agent.position[0]), int(agent.position[1])),
                "dir": int(agent.direction) if agent.direction is not None else 0,
                "state": _state_name(agent),
            }
        return out


# ── Experiment CLI ──────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Policy-divergence event graph over a whole run."
    )
    parser.add_argument("--width", type=int, default=25)
    parser.add_argument("--height", type=int, default=25)
    parser.add_argument("--agents", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--depth", type=int, default=0,
        help="step cap beyond the root; 0 = whole episode (default)",
    )
    parser.add_argument("--max-nodes", type=int, default=2000)
    parser.add_argument("--max-wall", type=float, default=300.0)
    parser.add_argument(
        "--guided-demo", action="store_true",
        help="use the UI's Guided Demo Environment (36x24, bottlenecked, "
             "malfunctions; --width/--height ignored, UI default agents=8)",
    )
    parser.add_argument(
        "--literal", action="store_true",
        help="branch on EVERY step the policies disagree, even when the "
             "same trains are already in dispute (explodes; for comparison)",
    )
    parser.add_argument(
        "--policies", type=str, default="",
        help="comma-separated policy ids (default: all deterministic "
             "scenario policies)",
    )
    args = parser.parse_args(argv)

    if args.guided_demo:
        env = _build_guided_demo_env(args.agents, args.seed)
    else:
        env = _build_test_env(args.width, args.height, args.agents, args.seed)

    participants = default_participants()
    if args.policies:
        from app.policies.registry import get_policy_spec

        wanted = [p.strip() for p in args.policies.split(",") if p.strip()]
        participants = []
        for pid in wanted:
            spec = get_policy_spec(pid)
            if spec is None:
                parser.error(f"unknown policy id: {pid}")
            participants.append((spec.id, spec.branch_factory))

    graph = PolicyDivergenceGraphBuilder(
        env,
        participants,
        PolicyGraphLimits(
            max_depth=args.depth or None,
            max_nodes=args.max_nodes,
            max_wall_s=args.max_wall,
        ),
        new_disputes_only=not args.literal,
    ).build()

    s = graph.stats
    env_desc = "guided-demo 36x24" if args.guided_demo else f"{args.width}x{args.height}"
    print(
        f"env {env_desc} agents={args.agents} seed={args.seed} "
        f"depth<={args.depth or 'episode-end'} max_nodes={args.max_nodes}"
    )
    print(f"policies: {', '.join(graph.policy_ids)}")
    print(
        f"nodes={s.nodes} edges={s.edges} divergences={s.divergences} "
        f"merges={s.merges}"
    )
    print(
        f"false_divergences={s.false_divergences} (same state, different "
        f"actions) ongoing_dispute_steps={s.ongoing_dispute_steps} "
        f"policy_errors={s.policy_errors}"
    )
    print(
        f"events: arrival={s.arrival_events} deadlock={s.deadlock_events} "
        f"terminal={sum(1 for n in graph.nodes.values() if n.terminal)} "
        f"truncated={s.truncated_nodes}"
    )
    print(
        f"max_depth_reached={s.max_depth_reached} "
        f"steps_simulated={s.steps_simulated} forks={s.forks} "
        f"build={s.build_seconds:.1f}s"
    )

    for e in graph.edges[:8]:
        if e.action_diff:
            diff = ", ".join(f"T{h}:{a}" for h, a in e.action_diff.items())
            print(f"  divergence @step {graph.nodes[e.to_id].step}: "
                  f"{'+'.join(e.policy_ids)} → {diff}")


if __name__ == "__main__":
    main()
