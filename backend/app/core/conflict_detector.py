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

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flatland.callbacks.callbacks import FlatlandCallbacks
from flatland.envs.rail_env import RailEnv
from flatland.envs.step_utils.states import TrainState


# ── Public types ────────────────────────────────────────────────────


ConflictKind = str  # "blocked" | "malfunction" | "swap_attempt"
                    # | "deadlock_cycle" | "agent_done" | "overdue_arrival"


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

    # ── detection stubs (filled in Part 2/3) ────────────────────────

    def _detect_blocked(self, env: RailEnv) -> None:
        pass

    def _detect_swap(self, env: RailEnv) -> None:
        pass

    def _detect_malfunctions(self, env: RailEnv) -> None:
        pass

    def _detect_done(self, env: RailEnv) -> None:
        pass

    def _detect_deadlock_cycles(self, env: RailEnv) -> None:
        pass

    def _detect_overdue(self, env: RailEnv) -> None:
        pass

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
