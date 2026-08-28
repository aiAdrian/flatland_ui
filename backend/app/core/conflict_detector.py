"""ConflictDetectionCallbacks — passive conflict observer for Flatland.

Subclass of flatland.callbacks.callbacks.FlatlandCallbacks. Plug it into
PolicyRunner.create_from_policy(callbacks=...) or TrajectoryEvaluator
to automatically collect conflict events during a trajectory run.

Usage
-----
    detector = ConflictDetectionCallbacks(blocked_threshold=3)
    PolicyRunner.create_from_policy(
        policy=DeadLockAvoidancePolicy(),
        env=env,
        callbacks=detector,
        snapshot_interval=0,
        end_step=20,
        data_dir=tmp_dir,
    )
    conflicts = detector.get_conflicts()  # List[Conflict]
    kpis = detector.get_kpis()            # dict

Detects: blocked-streaks, swap attempts, deadlock cycles, malfunctions,
         agent_done, overdue arrivals.

Reference
---------
Flatland 4.2.6 FlatlandCallbacks API (on_episode_start/step/end).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flatland.callbacks.callbacks import FlatlandCallbacks
from flatland.envs.rail_env import RailEnv
from flatland.envs.step_utils.states import TrainState


# ── Public types ────────────────────────────────────────────────────


ConflictKind = str  # "blocked" | "malfunction" | "swap_attempt"
                    # | "deadlock_cycle" | "agent_done" | "overdue_arrival"


# Direction → (dy, dx) for the cell in front of an agent (Flatland 0=N,1=E,2=S,3=W).
# Mirrors scenario_runner._DIR_DELTA so the detector stays self-contained — the
# scenario_runner copy is the single source for the runner; this one is local to
# detection so the callback does not import across modules.
_DIR_DELTA = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}


@dataclass
class Conflict:
    """One conflict event observed during a trajectory run."""
    kind: ConflictKind
    step: int
    agents: List[int]                 # involved agent handles
    position: Optional[Tuple[int, int]] = None
    info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # tuple → list for JSON friendliness
        if self.position is not None:
            d["position"] = [int(self.position[0]), int(self.position[1])]
        return d


# ── Callback implementation ─────────────────────────────────────────


class ConflictDetectionCallbacks(FlatlandCallbacks[RailEnv]):
    """Collects per-step snapshots and derives conflict events.

    Parameters
    ----------
    blocked_threshold : int
        How many consecutive STOPPED steps (without malfunction) count
        as a 'blocked' event. Default 3.
    detect_deadlocks : bool
        Run cycle detection on the wait-graph at episode end. Default True.
    """

    def __init__(
        self,
        *,
        blocked_threshold: int = 3,
        detect_deadlocks: bool = True,
    ):
        self.blocked_threshold = blocked_threshold
        self.detect_deadlocks = detect_deadlocks

        # Per-step snapshots: list of dicts
        #   {step, agents: {h: {pos, dir, state, malfunction}}}
        self._snapshots: List[Dict[str, Any]] = []

        # Streaks: handle → consecutive STOPPED count (resets when state changes)
        self._stopped_streak: Dict[int, int] = {}
        # Already emitted blocked events to avoid flooding
        self._blocked_emitted: Dict[int, int] = {}  # handle → step of last emission

        # Already emitted agent_done events
        self._done_emitted: set[int] = set()

        # Output
        self._conflicts: List[Conflict] = []

        # Memoised remaining-path cell sets, keyed by (handle, position) — a
        # stopped train's position is stable, so its path is computed once per
        # stall. Cleared on episode start alongside the streak counters.
        self._path_cache: Dict[Tuple[int, Tuple[int, int]], frozenset] = {}

    # ── FlatlandCallbacks API ───────────────────────────────────────

    def on_episode_start(
        self,
        *,
        env: Optional[RailEnv] = None,
        data_dir: Optional[Path] = None,
        **kwargs,
    ) -> None:
        # Reset state in case the same instance is reused.
        self._snapshots.clear()
        self._stopped_streak.clear()
        self._blocked_emitted.clear()
        self._done_emitted.clear()
        self._conflicts.clear()
        self._path_cache.clear()
        if env is not None:
            self._take_snapshot(env)

    def on_episode_step(
        self,
        *,
        env: Optional[RailEnv] = None,
        data_dir: Optional[Path] = None,
        **kwargs,
    ) -> None:
        if env is None:
            return
        self._take_snapshot(env)
        # Per-step detectors are wired in Part 2/3.
        self._detect_blocked(env)
        self._detect_swap(env)
        self._detect_malfunctions(env)
        self._detect_done(env)

    def on_episode_end(
        self,
        *,
        env: Optional[RailEnv] = None,
        data_dir: Optional[Path] = None,
        **kwargs,
    ) -> None:
        if env is None:
            return
        if self.detect_deadlocks:
            self._detect_deadlock_cycles(env)
        self._detect_overdue(env)

    # ── snapshot helper ─────────────────────────────────────────────

    def _take_snapshot(self, env: RailEnv) -> None:
        step = int(getattr(env, "_elapsed_steps", 0))
        agents = {}
        for h, ag in enumerate(env.agents):
            agents[h] = {
                "pos": tuple(ag.position) if ag.position is not None else None,
                "dir": int(ag.direction) if ag.direction is not None else None,
                "state": ag.state.name if hasattr(ag.state, "name") else str(ag.state),
                "malfunction": int(self._malfunction_counter(ag)),
            }
        self._snapshots.append({"step": step, "agents": agents})

    @staticmethod
    def _malfunction_counter(agent) -> int:
        # Flatland 4.2.6: agent.malfunction_handler.malfunction_down_counter
        mh = getattr(agent, "malfunction_handler", None)
        if mh is None:
            return 0
        return int(getattr(mh, "malfunction_down_counter", 0) or 0)

    # ── detection (blocked / swap / deadlock_cycle filled; the three
    #    single-train kinds stay no-ops until a separate task wires them) ─

    def _detect_blocked(self, env: RailEnv) -> None:
        """A train STOPPED for `blocked_threshold` consecutive steps is
        *blocked* — the cell ahead is occupied. The contention is between
        the stopped train and whatever holds that cell, so both handles go
        in `agents` (a lone stopped train is a delay, not a contention).

        One event per streak: the streak counter resets the moment the
        train moves, and `_blocked_emitted` is cleared with it, so a later
        stall emits a fresh event.
        """
        step = int(getattr(env, "_elapsed_steps", 0))
        for h, ag in enumerate(env.agents):
            state_name = ag.state.name if hasattr(ag.state, "name") else str(ag.state)
            if state_name != "STOPPED":
                # Moving again → streak broken, allow a new emission next stall.
                self._stopped_streak[h] = 0
                self._blocked_emitted.pop(h, None)
                continue

            cur = self._stopped_streak.get(h, 0) + 1
            self._stopped_streak[h] = cur
            if cur < self.blocked_threshold or h in self._blocked_emitted:
                continue

            # The contention is the set of trains whose remaining route shares
            # a cell with this one's — they are fighting for the same track
            # segment (a face-to-face ahead, or a distant merge onto a single
            # line). Adjacency alone misses the distant case the PF–CH
            # single-track conflict exhibits, so the blocker set is the
            # path-overlap set rather than only the train in the next cell.
            contenders = self._contenders(env, h)
            agents = sorted({h, *contenders})
            pos = tuple(ag.position) if ag.position is not None else None
            self._conflicts.append(
                Conflict(
                    kind="blocked",
                    step=step,
                    agents=agents,
                    position=pos,
                    # `emitter` is the stalled train whose streak crossed the
                    # threshold — distinct from the other `agents`, which are
                    # its contenders. Lets callers count emissions per train
                    # rather than per handle-membership (a handle appears in
                    # its own event and in each contender's).
                    info={"consecutive_stops": int(cur), "emitter": int(h)},
                )
            )
            self._blocked_emitted[h] = step

    def _detect_swap(self, env: RailEnv) -> None:
        """A *swap attempt* is two on-map agents face-to-face: each occupies
        the cell the other is trying to enter (a mutual edge in the
        wait-graph). Flatland's movement scheme forbids the swap and stalls
        both, so it surfaces as a stand-off the dispatcher has to break.

        Detected from the wait-graph (mutual edges) rather than from
        observed position swaps, which Flatland never lets happen — so the
        only signal that a swap was *attempted* is the face-to-face itself.

        A 2-cycle is reported here as ``swap_attempt``; larger cycles are
        left to ``_detect_deadlock_cycles`` so a face-to-face is not
        double-reported.
        """
        if len(self._snapshots) < 2:
            return
        step = int(getattr(env, "_elapsed_steps", 0))
        graph = self._wait_graph(env)
        emitted: set = set()
        for h, blockers in graph.items():
            for h2 in blockers:
                if h2 == h:
                    continue
                if h in graph.get(h2, set()):
                    pair = tuple(sorted((h, h2)))
                    if pair in emitted:
                        continue
                    emitted.add(pair)
                    ag = env.agents[h]
                    pos = tuple(ag.position) if ag.position is not None else None
                    self._conflicts.append(
                        Conflict(
                            kind="swap_attempt",
                            step=step,
                            agents=[pair[0], pair[1]],
                            position=pos,
                            info={"a": pair[0], "b": pair[1]},
                        )
                    )

    def _detect_malfunctions(self, env: RailEnv) -> None:
        pass

    def _detect_done(self, env: RailEnv) -> None:
        pass

    def _detect_deadlock_cycles(self, env: RailEnv) -> None:
        """A deadlock cycle is a set of on-map agents each waiting on the
        next, closing a loop — no one in the cycle can ever reach its
        target. Modelled as the strongly connected components (size ≥ 3)
        of the wait-graph (agent → agents occupying the cell ahead of it);
        one `deadlock_cycle` conflict per SCC, its `agents` the whole cycle.

        Size-2 cycles (a mutual face-to-face) are reported as `swap_attempt`
        by `_detect_swap`, not here, so a stand-off is not double-reported.
        Running at episode end catches cycles that only close after the
        final step.
        """
        step = int(getattr(env, "_elapsed_steps", 0))
        graph = self._wait_graph(env)
        for scc in self._sccs_of_size_ge(graph, 3):
            self._conflicts.append(
                Conflict(
                    kind="deadlock_cycle",
                    step=step,
                    agents=list(scc),
                    position=None,
                    info={"cycle": list(scc)},
                )
            )

    def _detect_overdue(self, env: RailEnv) -> None:
        pass

    # ── detection helpers ───────────────────────────────────────────

    def _contenders(self, env: RailEnv, handle: int) -> List[int]:
        """Other on-map trains whose remaining shortest path shares at least
        one cell with `handle`'s — i.e. the trains it is contending with for
        track ahead. A face-to-face ahead is the special case where the
        shared cell is the one directly in front; the general case (a distant
        merge onto a single line, the PF–CH Wal conflict) is caught by the
        full path overlap, which adjacency alone misses.

        Only on-map, not-done trains are candidates — a done train no longer
        holds any cell it would block others on."""
        mine = self._remaining_path_cells(env, handle)
        if not mine:
            return []
        out: List[int] = []
        for h2, a2 in enumerate(env.agents):
            if h2 == handle or a2.position is None:
                continue
            s2 = a2.state.name if hasattr(a2.state, "name") else str(a2.state)
            if s2 == "DONE":
                continue
            theirs = self._remaining_path_cells(env, h2)
            if theirs and not mine.isdisjoint(theirs):
                out.append(h2)
        return out

    def _remaining_path_cells(
        self, env: RailEnv, handle: int, cap: int = 300
    ) -> frozenset:
        """The cell set of one shortest remaining path for `handle`, from its
        current position to its target, by gradient descent on the env's
        distance map (direction-aware: ``dm[h][r][c][dir]`` is the distance
        from cell ``(r,c)`` entered facing ``dir``).

        Memoised by ``(handle, position)``: a stopped train's position is
        stable, so its path is computed once per stall. At a switch more than
        one neighbour may lower the distance; any shortest branch is taken —
        for overlap detection that is sufficient, since a train stopped on
        *any* shortest path of another blocks it. Capped to bound cost on
        large grids; the target is reached well within the cap on real nets.
        """
        ag = env.agents[handle]
        if ag.position is None or ag.direction is None:
            return frozenset()
        pos = (int(ag.position[0]), int(ag.position[1]))
        key = (handle, pos)
        cached = self._path_cache.get(key)
        if cached is not None:
            return cached

        dm = env.distance_map.get()
        dh = dm[handle]
        h, w, _ = dh.shape
        r, c = pos
        cur_dir = int(ag.direction)
        cells = {(r, c)}
        cur_d = float(dh[r, c, cur_dir])
        for _ in range(cap):
            # inf = cell unreachable facing this direction (off-path / invalid);
            # treat as a dead end rather than letting it poison the comparison.
            if math.isinf(cur_d) or cur_d <= 0:
                break
            best = None
            best_d = cur_d
            for ndir, (dr, dc) in _DIR_DELTA.items():
                nr, nc = r + dr, c + dc
                if not (0 <= nr < h and 0 <= nc < w):
                    continue
                nd = float(dh[nr, nc, ndir])
                if not math.isinf(nd) and 0 <= nd < best_d:
                    best = (nr, nc, ndir)
                    best_d = nd
            if best is None:
                break
            r, c, cur_dir = best
            if (r, c) in cells:
                break
            cells.add((r, c))
            cur_d = best_d
        result = frozenset(cells)
        self._path_cache[key] = result
        return result

    def _wait_graph(self, env: RailEnv) -> Dict[int, set]:
        """agent handle → set of on-map agents it is currently waiting on
        (those occupying the cell ahead). Done/waiting/ready-to-depart
        agents are not on the map and take no part."""
        graph: Dict[int, set] = {}
        for h, ag in enumerate(env.agents):
            s = ag.state.name if hasattr(ag.state, "name") else str(ag.state)
            if s in ("DONE", "WAITING", "READY_TO_DEPART"):
                continue
            if ag.position is None or ag.direction is None:
                continue
            dy, dx = _DIR_DELTA.get(int(ag.direction), (0, 0))
            front = (int(ag.position[0]) + dy, int(ag.position[1]) + dx)
            blockers = set()
            for h2, a2 in enumerate(env.agents):
                if h2 == h or a2.position is None:
                    continue
                s2 = a2.state.name if hasattr(a2.state, "name") else str(a2.state)
                if s2 in ("DONE", "WAITING", "READY_TO_DEPART"):
                    continue
                if tuple(a2.position) == front:
                    blockers.add(h2)
            graph[h] = blockers
        return graph

    @staticmethod
    def _sccs_of_size_ge(graph: Dict[int, set], min_size: int = 2) -> List[List[int]]:
        """Strongly connected components of `graph` with at least `min_size`
        nodes, each as a sorted handle list. Mutually-reachable grouping over
        the transitive closure — O(n·(n+e)), fine for Flatland agent counts,
        and avoids the cycle-enumeration dedup trap (one SCC = one cycle, by
        construction). `min_size=2` for all face-to-face cycles; `min_size=3`
        is used by `_detect_deadlock_cycles` so 2-cycles stay with swap."""
        nodes = list(graph.keys())
        # Transitive closure: reach[n] = everything reachable from n.
        reach: Dict[int, set] = {}
        for n in nodes:
            seen: set = set()
            stack = [n]
            while stack:
                x = stack.pop()
                for y in graph.get(x, ()):
                    if y not in seen:
                        seen.add(y)
                        stack.append(y)
            reach[n] = seen
        sccs: List[List[int]] = []
        assigned: set = set()
        for n in nodes:
            if n in assigned:
                continue
            comp = {n} | {
                m for m in nodes
                if m != n and m in reach[n] and n in reach.get(m, set())
            }
            if len(comp) >= min_size:
                sccs.append(sorted(comp))
            assigned |= comp
        return sccs

    # ── public output ───────────────────────────────────────────────

    def get_conflicts(self) -> List[Conflict]:
        """Return all detected conflict events, in chronological order."""
        return list(self._conflicts)

    def get_snapshots(self) -> List[Dict[str, Any]]:
        """Return raw per-step snapshots (for debugging / Marey)."""
        return list(self._snapshots)

    def get_kpis(self) -> Dict[str, Any]:
        """Aggregate counters across the run."""
        kinds: Dict[str, int] = {}
        for c in self._conflicts:
            kinds[c.kind] = kinds.get(c.kind, 0) + 1

        total_delay = sum(
            int(c.info.get("delay", 0))
            for c in self._conflicts
            if c.kind == "overdue_arrival"
        )

        # Agents involved in any non-informational conflict.
        agents_with_conflicts: set = set()
        for c in self._conflicts:
            if c.kind in ("blocked", "swap_attempt", "deadlock_cycle"):
                agents_with_conflicts.update(c.agents)

        return {
            "total_conflicts": len(self._conflicts),
            "by_kind": kinds,
            "num_snapshots": len(self._snapshots),
            "num_done": kinds.get("agent_done", 0),
            "num_overdue": kinds.get("overdue_arrival", 0),
            "num_blocked_events": kinds.get("blocked", 0),
            "num_swap_attempts": kinds.get("swap_attempt", 0),
            "num_deadlock_cycles": kinds.get("deadlock_cycle", 0),
            "num_malfunctions": kinds.get("malfunction", 0),
            "total_delay": int(total_delay),
            "agents_with_conflicts": sorted(agents_with_conflicts),
        }
