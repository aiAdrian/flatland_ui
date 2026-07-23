"""Exhaustive action-space event graph — Phase 0 of the policy-divergence graph.

Builds the graph of ALL reasonably reachable futures for the WHOLE run
(root state → all trains done / episode end) by branching at every
SWITCH cell into every *reasonable* exit direction
(`docs/plans/policy-divergence-event-graph.md` §0). Consensus steps
(no agent at a decision point) are compressed into edges; nodes are
created at branch points, train arrivals and deadlocks.

An exit at a switch is "reasonable" iff
  (a) the train's target is still reachable from it (finite
      distance_map entry — excludes driving away onto dead branches), and
  (b) the train has not already occupied that cell+direction on this
      branch (excludes loops / circling the network).
If filtering leaves exactly one reasonable exit, the switch is not a
branch point — the train simply takes that exit.

Divergence is decided on *resulting states*, not on actions: every new
node is deduplicated by a state hash, so two actions that lead to the
same successor state collapse into one node and reconvergent branches
merge into a DAG.

Purpose: measure how large the full action-space graph gets — it is a
hard upper bound for any policy-divergence graph (which is a subgraph).

Standalone size experiment:
    cd backend && python -m app.core.action_event_graph --agents 3 --seed 42
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import itertools
import tempfile
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from flatland.core.grid.grid4_utils import get_new_position
from flatland.envs.persistence import RailEnvPersister
from flatland.envs.rail_env import RailEnv
from flatland.envs.step_utils.states import TrainState

from app.core.cell_classifier import (
    ACTION_DO_NOTHING,
    ACTION_MOVE_FORWARD,
    ACTION_MOVE_LEFT,
    ACTION_MOVE_RIGHT,
    ACTION_NAMES,
    ACTION_STOP_MOVING,
    LEFT_OF,
    RIGHT_OF,
    _build_switch_options,
    _get_transitions,
    classify_cell_type,
)

# Direction → (dy, dx); Flatland convention 0=N, 1=E, 2=S, 3=W.
_DIR_DELTA = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}


# ── State inspection helpers ────────────────────────────────────────


def _state_name(agent) -> str:
    s = getattr(agent, "state", None)
    return s.name if hasattr(s, "name") else str(s)


def _malfunction_steps(agent) -> int:
    """Remaining malfunction steps, best-effort across Flatland versions."""
    mh = getattr(agent, "malfunction_handler", None)
    if mh is not None:
        try:
            return int(getattr(mh, "malfunction_down_counter", 0) or 0)
        except (TypeError, ValueError):
            pass
    md = getattr(agent, "malfunction_data", None)
    if isinstance(md, dict):
        try:
            return int(md.get("malfunction", 0) or 0)
        except (TypeError, ValueError):
            pass
    return 0


def _is_cell_entry(agent) -> bool:
    """True if the agent's action matters this step (speed<1 agents only
    choose at cell entry). Defaults to True when unknown."""
    sc = getattr(agent, "speed_counter", None)
    if sc is None:
        return True
    v = getattr(sc, "is_cell_entry", None)
    return True if v is None else bool(v)


def _done_handles(env) -> set:
    return {
        h for h, a in enumerate(env.agents)
        if getattr(a, "state", None) == TrainState.DONE
    }


def _all_done(env) -> bool:
    return all(
        getattr(a, "state", None) == TrainState.DONE for a in env.agents
    )


def state_hash(env, intents: Optional[Dict[int, Tuple[int, Tuple[int, int]]]] = None) -> str:
    """Stable hash of the decision-relevant env state.

    Includes elapsed step, so merging only happens between states reached
    at the same simulation time (schedules are time-dependent). Pending
    branch intents (chosen-but-not-yet-executed switch exits) are part of
    the state: two physically identical states with different pending
    intents have different futures.
    """
    parts = [str(int(getattr(env, "_elapsed_steps", 0) or 0))]
    for h, a in enumerate(env.agents):
        pos = a.position
        pos_t = (int(pos[0]), int(pos[1])) if pos is not None else None
        d = int(a.direction) if a.direction is not None else None
        sc = getattr(a, "speed_counter", None)
        counter = getattr(sc, "counter", None) if sc is not None else None
        parts.append(
            f"{h}:{pos_t}:{d}:{_state_name(a)}"
            f":{_malfunction_steps(a)}:{counter}"
        )
    if intents:
        for h in sorted(intents):
            act, cell = intents[h]
            parts.append(f"i{h}:{act}@{cell}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def hard_deadlocked_agents(env) -> set:
    """Agents that can never move again, no matter what anyone does.

    Fixpoint computation: start with all on-map agents, repeatedly remove
    any agent that has at least one exit cell which is free or occupied
    by an already-removed agent. What remains are agents in cyclic
    blocking (mutual face-to-face pairs, longer cycles) plus convoys
    stuck behind them with no alternative exit.

    Stricter than scenario_runner.deadlocked_agents (which also flags
    temporary follow-behind situations — fine post-mortem, wrong as a
    mid-rollout event trigger).
    """
    on_map: Dict[int, Tuple[int, int, int]] = {}
    for h, a in enumerate(env.agents):
        if _state_name(a) == "DONE":
            continue
        if a.position is None or a.direction is None:
            continue
        on_map[h] = (int(a.position[0]), int(a.position[1]), int(a.direction))

    occupied = {(r, c): h for h, (r, c, _d) in on_map.items()}

    exits: Dict[int, List[Tuple[int, int]]] = {}
    for h, (r, c, d) in on_map.items():
        try:
            trans = _get_transitions(env, r, c, d)
        except Exception:
            exits[h] = []
            continue
        exits[h] = [
            tuple(int(v) for v in get_new_position((r, c), nd))
            for nd in range(4) if trans[nd]
        ]

    stuck = {h for h in on_map if exits[h]}
    changed = True
    while changed:
        changed = False
        for h in list(stuck):
            for cell in exits[h]:
                blocker = occupied.get(cell)
                if blocker is None or blocker not in stuck:
                    stuck.discard(h)
                    changed = True
                    break
    return stuck


# ── Env fork helpers (same primitive as scenario_runner._fork_env) ──


EnvBlob = Tuple[bytes, int]


def _clear_flatland_method_caches() -> None:
    """Free forked envs pinned by Flatland's global lru_caches.

    Flatland decorates *instance methods* and helper functions with
    @lru_cache in several modules (RailGridTransitionMap with
    maxsize=4_000_000, distance-map walkers, fast methods, …). Cache keys
    include `self` / env-derived objects, so every forked env — and, via
    env references, its ~4 MB malfunction rand-cache — stays strongly
    referenced forever. Entries of dead envs can never be cache hits
    (different `self`), so clearing costs only the warm cache of the
    currently-expanding env. We sweep every flatland module for anything
    exposing cache_clear (plain functions and class attributes).
    """
    import sys

    for mod_name, mod in list(sys.modules.items()):
        if not mod_name.startswith("flatland") or mod is None:
            continue
        for attr_name in dir(mod):
            try:
                attr = getattr(mod, attr_name)
            except Exception:
                continue
            if hasattr(attr, "cache_clear"):
                try:
                    attr.cache_clear()
                except Exception:
                    pass
            elif isinstance(attr, type):
                for m_name in dir(attr):
                    try:
                        m = getattr(attr, m_name)
                    except Exception:
                        continue
                    if hasattr(m, "cache_clear"):
                        try:
                            m.cache_clear()
                        except Exception:
                            pass


def env_to_blob(env: RailEnv) -> EnvBlob:
    """Serialize env state to bytes + elapsed steps (persister drops them)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "state.pkl"
        RailEnvPersister.save(env, str(p))
        data = p.read_bytes()
    return data, int(getattr(env, "_elapsed_steps", 0) or 0)


# Distance map shared by every fork while `shared_distance_map` is active.
# Process-global because the mechanism patches a Flatland class method —
# a graph build must therefore be single-threaded (they are: one builder
# per request/CLI run, CPU-bound, meant to run in a worker).
_SHARED_DISTANCE_MAP = None


@contextmanager
def shared_distance_map(env: RailEnv):
    """Compute the distance map once and reuse it for every fork.

    `RailEnvPersister.set_full_state` calls `distance_map._compute()`
    unconditionally on every load — bypassing Flatland's own
    "don't compute the distance map if it was loaded" guard in
    `AbstractDistanceMap.get()`. That recompute is a full multi-target
    BFS over the grid and dominates the cost of forking (measured: ~63 %
    of build time).

    The map depends only on the rail layout and the agents' targets,
    neither of which changes during an episode or across a fork, so one
    computation is valid for the whole build. We suppress the recompute
    and hand every fork the same array; nothing mutates it once
    `_compute` is disabled (only `_compute` ever writes to it).
    """
    global _SHARED_DISTANCE_MAP
    from flatland.envs.grid.distance_map import DistanceMap

    previous = _SHARED_DISTANCE_MAP
    original_compute = DistanceMap._compute
    try:
        _SHARED_DISTANCE_MAP = env.distance_map.get()
    except Exception:
        yield None
        return

    def _skip_compute(self, agents, rail):
        return None

    DistanceMap._compute = _skip_compute
    try:
        yield _SHARED_DISTANCE_MAP
    finally:
        DistanceMap._compute = original_compute
        _SHARED_DISTANCE_MAP = previous


def blob_to_env(blob: EnvBlob) -> RailEnv:
    data, elapsed = blob
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "state.pkl"
        p.write_bytes(data)
        env, _ = RailEnvPersister.load_new(str(p))
    env._elapsed_steps = elapsed
    if _SHARED_DISTANCE_MAP is not None:
        # `get()` then short-circuits: reset_was_called is set, but
        # agents_previous_computation is None and the map is present.
        env.distance_map.distance_map = _SHARED_DISTANCE_MAP
    return env


# ── Graph model ─────────────────────────────────────────────────────


@dataclass
class GraphNode:
    id: str
    step: int                       # env._elapsed_steps at this node
    event: str                      # root | branch | arrival | deadlock
    agents: Dict[str, dict]
    arrived: List[int]              # cumulative DONE handles
    deadlocked: List[int]           # cumulative hard-deadlocked handles
    pending: Dict[int, str] = field(default_factory=dict)  # unexecuted intents
    terminal: bool = False          # all agents done / episode over
    truncated: bool = False         # expansion cut by a budget

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "step": int(self.step),
            "event": self.event,
            "agents": self.agents,
            "arrived": list(self.arrived),
            "deadlocked": list(self.deadlocked),
            "pending": {int(h): a for h, a in self.pending.items()},
            "terminal": bool(self.terminal),
            "truncated": bool(self.truncated),
        }


@dataclass
class GraphEdge:
    from_id: str
    to_id: str
    steps: int                      # consensus steps compressed into the edge
    actions: Dict[int, str]         # branching agents only; {} on event edges

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_id,
            "to": self.to_id,
            "steps": int(self.steps),
            "actions": {int(h): a for h, a in self.actions.items()},
        }


@dataclass
class GraphLimits:
    max_depth: Optional[int] = None  # steps beyond the root; None = episode end
    max_nodes: int = 2000
    max_wall_s: float = 120.0


@dataclass
class GraphStats:
    nodes: int = 0
    edges: int = 0
    branch_points: int = 0
    merges: int = 0                 # edges into an already-existing node
    arrival_events: int = 0
    deadlock_events: int = 0
    truncated_nodes: int = 0
    max_depth_reached: int = 0
    forks: int = 0                  # env blob save/load round-trips
    steps_simulated: int = 0
    filtered_exits: int = 0         # switch exits dropped (unreachable / loop)
    forced_exits: int = 0           # switches collapsed to 1 reasonable exit
    dead_end_fallbacks: int = 0     # switches where ALL exits were unreasonable
    build_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class ActionEventGraph:
    root_id: str
    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    edges: List[GraphEdge] = field(default_factory=list)
    stats: GraphStats = field(default_factory=GraphStats)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_id": self.root_id,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "stats": self.stats.to_dict(),
        }


# ── Builder ─────────────────────────────────────────────────────────


class ExhaustiveActionGraphBuilder:
    """Breadth-first expansion of the full action-space event graph.

    The base env is never mutated: the root state is serialized first and
    every expansion works on a restored copy.
    """

    def __init__(
        self,
        base_env: RailEnv,
        limits: GraphLimits = GraphLimits(),
        include_stop: bool = False,
    ):
        self._base_env = base_env
        self._limits = limits
        self._include_stop = include_stop
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: List[GraphEdge] = []
        self._stats = GraphStats()
        self._deadline = 0.0
        self._root_step = 0
        self._depth_cap = 0
        # True when the depth cap IS the end of the episode: reaching it
        # means the run finished, not that we cut it short.
        self._depth_cap_is_episode_end = limits.max_depth is None
        # Distance map shared across ALL forks (it depends only on rail
        # layout + targets, which forking never changes). Computing it per
        # fork would cost ~2 MB + significant CPU per expanded node.
        self._dist = None

    # ── public API ──────────────────────────────────────────────────

    def build(self) -> ActionEventGraph:
        with shared_distance_map(self._base_env):
            return self._build()

    def _build(self) -> ActionEventGraph:
        t0 = time.perf_counter()
        self._deadline = t0 + self._limits.max_wall_s

        root_blob = env_to_blob(self._base_env)
        self._stats.forks += 1
        env = blob_to_env(root_blob)
        self._root_step = int(getattr(env, "_elapsed_steps", 0) or 0)

        if self._limits.max_depth is not None:
            self._depth_cap = self._limits.max_depth
        else:
            # Whole run: cap at the episode's own end.
            max_ep = int(getattr(env, "_max_episode_steps", 0) or 0)
            self._depth_cap = max(1, max_ep - self._root_step) if max_ep else 1000

        try:
            self._dist = env.distance_map.get()
        except Exception:
            self._dist = None

        root, _ = self._node_for_state(env, "root", {})
        root_visited: Dict[int, set] = {}
        self._record_visited(env, root_visited)
        queue: deque = deque([(root.id, root_blob, 0, root_visited, {})])
        expansions = 0

        while queue:
            over_budget = (
                len(self._nodes) >= self._limits.max_nodes
                or time.perf_counter() > self._deadline
            )
            if over_budget:
                # Never truncate silently: flag every unexpanded frontier node.
                for nid, _blob, _depth, _visited, _intents in queue:
                    node = self._nodes[nid]
                    if not node.terminal:
                        node.truncated = True
                break
            nid, blob, depth, visited, intents = queue.popleft()
            env = blob_to_env(blob)
            self._stats.forks += 1
            self._expand(nid, env, depth, visited, intents, queue)
            del env
            expansions += 1
            if expansions % 20 == 0:
                # Without this, dead forked envs pile up: Flatland's global
                # method lru_caches pin them, and RailEnv reference cycles
                # defer the rest to rare gen-2 GCs.
                _clear_flatland_method_caches()
                gc.collect()

        self._stats.nodes = len(self._nodes)
        self._stats.edges = len(self._edges)
        self._stats.truncated_nodes = sum(
            1 for n in self._nodes.values() if n.truncated
        )
        self._stats.max_depth_reached = max(
            (n.step - self._root_step for n in self._nodes.values()),
            default=0,
        )
        _clear_flatland_method_caches()
        gc.collect()
        self._stats.build_seconds = time.perf_counter() - t0
        return ActionEventGraph(
            root_id=root.id,
            nodes=self._nodes,
            edges=self._edges,
            stats=self._stats,
        )

    # ── expansion ───────────────────────────────────────────────────

    def _expand(
        self,
        node_id: str,
        env: RailEnv,
        depth: int,
        visited: Dict[int, set],
        intents: Dict[int, Tuple[int, Tuple[int, int]]],
        queue: deque,
    ) -> None:
        """Advance one node: compress consensus steps, emit event nodes,
        stop at the first branch point (children are enqueued).

        ``visited`` — per-agent set of (row, col, dir) states occupied on
        this branch; feeds the no-loop exit filter.
        ``intents`` — handle → (action, decision cell): switch exits already
        chosen on this branch but not yet executed (train blocked). The
        intent action is re-issued every step and the agent does not
        re-branch until it actually leaves the decision cell.
        """
        cur_id = node_id
        steps_since = 0
        prev_done = _done_handles(env)
        prev_dl = hard_deadlocked_agents(env)

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

            combos = self._joint_action_combos(env, visited, intents)

            if len(combos) == 1:
                actions, _labeled = combos[0]
                if not self._step(env, actions):
                    self._nodes[cur_id].terminal = True
                    return
                self._consume_intents(env, intents)
                self._record_visited(env, visited)
                depth += 1
                steps_since += 1

                done = _done_handles(env)
                dl = hard_deadlocked_agents(env)
                new_done = done - prev_done
                new_dl = dl - prev_dl
                if new_done or new_dl:
                    event = "deadlock" if new_dl else "arrival"
                    if new_done:
                        self._stats.arrival_events += 1
                    if new_dl:
                        self._stats.deadlock_events += 1
                    node, created = self._node_for_state(env, event, intents)
                    self._add_edge(cur_id, node.id, steps_since, {})
                    if not created:
                        self._stats.merges += 1
                        return  # state already explored elsewhere
                    cur_id = node.id
                    steps_since = 0
                    prev_done, prev_dl = done, dl
                continue

            # Branch point: one child per joint action combo. Capture the
            # branching agents' decision cells BEFORE stepping (the last
            # combo reuses `env` in place).
            self._stats.branch_points += 1
            decision_cells = {
                h: (int(env.agents[h].position[0]), int(env.agents[h].position[1]))
                for h in combos[0][1]  # branching handles (same in every combo)
                if env.agents[h].position is not None
            }
            parent_blob = env_to_blob(env)
            self._stats.forks += 1
            for i, (actions, labeled) in enumerate(combos):
                if i == len(combos) - 1:
                    child_env = env  # reuse in-place for the last combo
                else:
                    child_env = blob_to_env(parent_blob)
                    self._stats.forks += 1
                if not self._step(child_env, actions):
                    self._nodes[cur_id].terminal = True
                    continue
                child_intents = dict(intents)
                for h in labeled:
                    if h in decision_cells:
                        child_intents[h] = (actions[h], decision_cells[h])
                self._consume_intents(child_env, child_intents)
                child_visited = {h: set(s) for h, s in visited.items()}
                self._record_visited(child_env, child_visited)
                node, created = self._node_for_state(
                    child_env, "branch", child_intents
                )
                self._add_edge(cur_id, node.id, steps_since + 1, labeled)
                if not created:
                    self._stats.merges += 1
                    continue
                if set(node.arrived) - prev_done:
                    self._stats.arrival_events += 1
                if set(node.deadlocked) - prev_dl:
                    self._stats.deadlock_events += 1
                queue.append((
                    node.id, env_to_blob(child_env), depth + 1,
                    child_visited, child_intents,
                ))
                self._stats.forks += 1
            return

    # ── branching rule ──────────────────────────────────────────────

    def _agent_switch_actions(
        self, env: RailEnv, handle: int, agent, visited: Dict[int, set]
    ) -> Optional[List[int]]:
        """Reasonable exit actions if the agent decides at a SWITCH this
        step, else None (agent is not at a decision point).

        Filters out exits from which the target is unreachable and exits
        into a cell+direction the agent already occupied on this branch
        (no loops). May return a single action — then the switch is not
        a branch point but the action must still be applied.
        """
        if getattr(agent, "state", None) == TrainState.DONE:
            return None
        if agent.position is None or agent.direction is None:
            return None
        if _malfunction_steps(agent) > 0:
            return None
        if not _is_cell_entry(agent):
            return None
        if classify_cell_type(env, agent) != "SWITCH":
            return None

        direction = int(agent.direction)
        opts = _build_switch_options(
            env,
            (int(agent.position[0]), int(agent.position[1])),
            direction,
        )
        dist = self._dist

        seen = visited.get(handle, set())
        reasonable: List[int] = []
        for o in opts:
            act = int(o["action"])
            if act == ACTION_MOVE_LEFT:
                exit_dir = LEFT_OF[direction]
            elif act == ACTION_MOVE_RIGHT:
                exit_dir = RIGHT_OF[direction]
            else:
                exit_dir = direction
            nr, nc = (int(v) for v in o["target_position"])
            if (nr, nc, exit_dir) in seen:
                self._stats.filtered_exits += 1  # loop
                continue
            if dist is not None:
                d = dist[handle, nr, nc, exit_dir]
                if not np.isfinite(d):
                    self._stats.filtered_exits += 1  # target unreachable
                    continue
            reasonable.append(act)

        if not reasonable:
            # Every exit is unreasonable (e.g. train already looped into a
            # trap) — fall back to the raw options so the run continues.
            self._stats.dead_end_fallbacks += 1
            reasonable = [int(o["action"]) for o in opts]
        if self._include_stop:
            reasonable.append(ACTION_STOP_MOVING)
        return reasonable

    def _joint_action_combos(
        self,
        env: RailEnv,
        visited: Dict[int, set],
        intents: Dict[int, Tuple[int, Tuple[int, int]]],
    ) -> List[Tuple[Dict[int, int], Dict[int, str]]]:
        """All reasonable joint actions: cross product over agents at
        decision points.

        Agents with a pending intent re-issue it instead of re-branching;
        hard-deadlocked agents never branch (their choice can't execute).
        Returns [(full action dict, {handle: action_name} for branching
        agents)]. Exactly one entry when nobody has a genuine choice.
        """
        deadlocked = hard_deadlocked_agents(env)
        base: Dict[int, int] = {}
        branching: Dict[int, List[int]] = {}
        for h, a in enumerate(env.agents):
            base[h] = (
                ACTION_DO_NOTHING
                if getattr(a, "state", None) == TrainState.DONE
                else ACTION_MOVE_FORWARD
            )
            if h in intents:
                base[h] = intents[h][0]
                continue
            if h in deadlocked:
                continue
            opts = self._agent_switch_actions(env, h, a, visited)
            if opts is None:
                continue
            if len(opts) == 1:
                # Only one reasonable exit: forced move, not a branch point.
                base[h] = opts[0]
                self._stats.forced_exits += 1
            else:
                branching[h] = opts

        if not branching:
            return [(base, {})]

        handles = sorted(branching)
        combos: List[Tuple[Dict[int, int], Dict[int, str]]] = []
        for combo in itertools.product(*(branching[h] for h in handles)):
            actions = dict(base)
            labeled: Dict[int, str] = {}
            for h, act in zip(handles, combo):
                actions[h] = act
                labeled[h] = ACTION_NAMES[act]
            combos.append((actions, labeled))
        return combos

    # ── internals ───────────────────────────────────────────────────

    def _step(self, env: RailEnv, actions: Dict[int, int]) -> bool:
        """env.step wrapper; False when the episode is already over
        (same guard as TrajectoryBranchRunner.run_branch)."""
        self._stats.steps_simulated += 1
        try:
            env.step({int(h): int(a) for h, a in actions.items()})
            return True
        except Exception as e:
            if "Episode is done" in str(e):
                return False
            raise

    def _node_for_state(
        self,
        env: RailEnv,
        event: str,
        intents: Dict[int, Tuple[int, Tuple[int, int]]],
    ) -> Tuple[GraphNode, bool]:
        """Get-or-create the node for the env's current state (P1 rule:
        identical states are the same node; pending intents are state)."""
        hid = state_hash(env, intents)
        existing = self._nodes.get(hid)
        if existing is not None:
            return existing, False
        node = GraphNode(
            id=hid,
            step=int(getattr(env, "_elapsed_steps", 0) or 0),
            event=event,
            agents=self._capture_agents(env),
            arrived=sorted(_done_handles(env)),
            deadlocked=sorted(hard_deadlocked_agents(env)),
            pending={h: ACTION_NAMES[act] for h, (act, _c) in intents.items()},
        )
        self._nodes[hid] = node
        return node, True

    @staticmethod
    def _consume_intents(
        env: RailEnv, intents: Dict[int, Tuple[int, Tuple[int, int]]]
    ) -> None:
        """Drop every intent whose agent has left its decision cell (the
        chosen exit was executed) or is no longer on the map."""
        for h in list(intents):
            _act, cell = intents[h]
            pos = env.agents[h].position
            if pos is None or (int(pos[0]), int(pos[1])) != cell:
                del intents[h]

    def _add_edge(
        self, from_id: str, to_id: str, steps: int, actions: Dict[int, str]
    ) -> None:
        self._edges.append(GraphEdge(from_id, to_id, steps, actions))

    @staticmethod
    def _record_visited(env: RailEnv, visited: Dict[int, set]) -> None:
        """Add every on-map agent's current (row, col, dir) to its branch
        history (feeds the no-loop exit filter)."""
        for h, a in enumerate(env.agents):
            if a.position is None or a.direction is None:
                continue
            visited.setdefault(h, set()).add(
                (int(a.position[0]), int(a.position[1]), int(a.direction))
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


# ── Size experiment CLI ─────────────────────────────────────────────


def _build_test_env(width: int, height: int, agents: int, seed: int) -> RailEnv:
    from flatland.core.env_observation_builder import DummyObservationBuilder
    from flatland.envs.line_generators import sparse_line_generator
    from flatland.envs.rail_generators import sparse_rail_generator

    env = RailEnv(
        width=width,
        height=height,
        number_of_agents=agents,
        random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    env.reset()
    return env


def _build_guided_demo_env(agents: int, seed: int) -> RailEnv:
    """The UI's "Guided Demo Environment" (app.component.ts
    guidedDemoEnvOpts): bottlenecked corridors + malfunctions, 36x24,
    400 steps. `agents`/`seed` overridable for scaling experiments
    (UI defaults: 8 agents, seed 42).

    NB: `env_factory.create_env` seeds the rail/line *generators* but
    never passes `random_seed` to RailEnv itself, so the env's own RNG
    (schedule, targets, malfunction draws) differs on every call — the
    "fixed seed 42" demo env is not reproducible across sessions. We
    re-reset with an explicit seed so measurements are comparable.
    """
    from app.core.env_factory import create_env

    env = create_env(
        width=36,
        height=24,
        number_of_agents=agents,
        seed=seed,
        max_num_cities=3,
        max_rails_between_cities=2,
        max_rail_pairs_in_city=1,
        max_episode_steps=400,
        latest_departure_max=35,
        speed_profile="uniform_1_0",
        line_length=4,
        malfunction_rate=0.02,
        malfunction_min_duration=10,
        malfunction_max_duration=22,
    )
    env.reset(random_seed=seed)
    return env


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Exhaustive action-space graph size experiment (Phase 0)."
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
    parser.add_argument("--max-wall", type=float, default=120.0)
    parser.add_argument("--include-stop", action="store_true")
    parser.add_argument(
        "--guided-demo", action="store_true",
        help="use the UI's Guided Demo Environment (36x24, bottlenecked, "
             "malfunctions; --width/--height ignored, UI default agents=8)",
    )
    args = parser.parse_args(argv)

    if args.guided_demo:
        env = _build_guided_demo_env(args.agents, args.seed)
    else:
        env = _build_test_env(args.width, args.height, args.agents, args.seed)
    graph = ExhaustiveActionGraphBuilder(
        env,
        GraphLimits(
            max_depth=args.depth or None,
            max_nodes=args.max_nodes,
            max_wall_s=args.max_wall,
        ),
        include_stop=args.include_stop,
    ).build()

    s = graph.stats
    env_desc = (
        "guided-demo 36x24" if args.guided_demo
        else f"{args.width}x{args.height}"
    )
    print(
        f"env {env_desc} agents={args.agents} seed={args.seed} "
        f"depth<={args.depth or 'episode-end'} max_nodes={args.max_nodes} "
        f"include_stop={args.include_stop}"
    )
    print(
        f"nodes={s.nodes} edges={s.edges} branch_points={s.branch_points} "
        f"merges={s.merges}"
    )
    print(
        f"exit filter: filtered={s.filtered_exits} forced={s.forced_exits} "
        f"dead_end_fallbacks={s.dead_end_fallbacks}"
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

    by_depth: Dict[int, int] = {}
    root_step = graph.nodes[graph.root_id].step
    for n in graph.nodes.values():
        by_depth[n.step - root_step] = by_depth.get(n.step - root_step, 0) + 1
    hist = " ".join(f"{d}:{c}" for d, c in sorted(by_depth.items()))
    print(f"nodes_by_depth {hist}")


if __name__ == "__main__":
    main()
