"""TrajectoryBranchRunner — runs hypothetical "what-if" trajectories.

Given a base env and a set of action overrides for the next step (or for
every step), forks the env, runs it forward under the default policy with
the user's overrides applied at decision cells, and collects conflicts
+ KPIs via ConflictDetectionCallbacks.

Usage
-----
    runner = TrajectoryBranchRunner(
        base_env=env,
        default_policy_factory=DeadLockAvoidancePolicy,
    )
    result = runner.run_branch(
        overrides={0: RailEnvActions.MOVE_LEFT},
        max_steps=20,
        blocked_threshold=3,
    )
    # result.conflicts, result.kpis, result.snapshots, result.success_rate

Design notes
------------
* The env is forked via RailEnvPersister.save/load_new — that path is
  the supported way in Flatland 4.2.6 to clone an env deterministically
  without deepcopy headaches.
* The detector is driven directly via on_episode_start/_step/_end (no
  PolicyRunner wrapper) so we keep full control of the step loop and
  can short-circuit when all agents are done.
* Overrides are applied via our existing OverridePolicy, but with a
  *temporary* override store keyed by a synthetic session_id, so we
  don't pollute the real session's overrides.
"""
from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from flatland.envs.persistence import RailEnvPersister
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions

STOP_MOVING_ACTION_VALUE = int(RailEnvActions.STOP_MOVING.value)

from app.core.conflict_detector import Conflict, ConflictDetectionCallbacks
from app.policies.base import Policy
from app.policies.override_policy import OverridePolicy


# ── Public types ────────────────────────────────────────────────────



# Direction → (dy, dx) for the next cell in front of an agent.
# Flatland convention: 0=N, 1=E, 2=S, 3=W
_DIR_DELTA = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}


def count_deadlocked_agents(env) -> int:
    """Post-mortem deadlock count after a branch finished.

    An agent is deadlocked iff it is on the map (not DONE, not WAITING),
    facing a cell that's occupied by another on-map agent. Both sides
    of such a face-to-face (and convoys blocked by a head) get counted,
    matching the operator's definition: 'agents that can never reach
    their target anymore'.
    """
    agents_at_pos = {}
    for h, a in enumerate(env.agents):
        if a.position is not None:
            agents_at_pos[tuple(a.position)] = h

    deadlocked = set()
    for h, a in enumerate(env.agents):
        s = a.state.name if hasattr(a.state, "name") else str(a.state)
        if s in ("DONE", "WAITING"):
            continue
        if a.position is None or a.direction is None:
            continue
        dy, dx = _DIR_DELTA.get(int(a.direction), (0, 0))
        front = (int(a.position[0]) + dy, int(a.position[1]) + dx)
        if front in agents_at_pos:
            deadlocked.add(h)
            deadlocked.add(agents_at_pos[front])
    return len(deadlocked)


@dataclass
class BranchResult:
    """Result of a single what-if trajectory run."""
    conflicts: List[Conflict] = field(default_factory=list)
    kpis: Dict[str, Any] = field(default_factory=dict)
    snapshots: List[Dict[str, Any]] = field(default_factory=list)

    # Outcome summary
    total_agents: int = 0
    success_count: int = 0          # agents in DONE state
    elapsed_steps: int = 0
    finished: bool = False  # True if all_done; False if horizon hit
    terminated_early: bool = False  # True if all agents done before max_steps

    @property
    def success_rate(self) -> float:
        if self.total_agents == 0:
            return 0.0
        return self.success_count / self.total_agents

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflicts": [c.to_dict() for c in self.conflicts],
            "kpis": dict(self.kpis),
            "snapshots": list(self.snapshots),
            "total_agents": int(self.total_agents),
            "success_count": int(self.success_count),
            "elapsed_steps": int(self.elapsed_steps),
            "finished": bool(self.finished),
            "terminated_early": bool(self.terminated_early),
            "success_rate": float(self.success_rate),
        }


# ── Runner ──────────────────────────────────────────────────────────


PolicyFactory = Callable[[], Policy]


class TrajectoryBranchRunner:
    """Run hypothetical what-if trajectories on a forked env.

    Parameters
    ----------
    base_env : RailEnv
        The env to fork from. NOT modified; we always work on a clone.
    default_policy_factory : Callable[[], Policy]
        Zero-arg factory that produces a fresh default policy per branch.
        We need a *factory* (not an instance) because policies hold
        per-episode state (DLA's distance maps etc.).
    """

    def __init__(
        self,
        base_env: RailEnv,
        default_policy_factory: PolicyFactory,
    ):
        self._base_env = base_env
        self._policy_factory = default_policy_factory

    # ── public API (filled in Part 2/3) ─────────────────────────────

    def run_branch(
        self,
        overrides: Optional[Dict[int, RailEnvActions]] = None,
        max_steps: int = 50,
        blocked_threshold: int = 3,
        detect_deadlocks: bool = True,
    ) -> BranchResult:
        """Fork the env, apply overrides, run forward, collect KPIs.

        Steps:
          1. Fork the base env (deterministic clone).
          2. Build OverridePolicy(DefaultPolicy, session_id) with the
             user's overrides pushed into a temporary override store.
          3. Drive the env forward: per step, call policy.start_step,
             policy.act_many, env.step, policy.end_step, then feed
             on_episode_step to the conflict detector.
          4. On termination (all done, or max_steps reached, or
             "Episode is done"), call detector.on_episode_end and
             assemble the BranchResult.
        """
        from app.core.override_manager import override_manager

        overrides = overrides or {}

        # Manual STOP override semantics:
        # STOP_MOVING is persistent in forecasts as well. If user stops a train,
        # the predicted branch must keep issuing STOP until the forecast horizon,
        # because no future release step is known.
        persistent_stop_overrides = {
            int(h): RailEnvActions.STOP_MOVING
            for h, a in overrides.items()
            if int(a.value if hasattr(a, "value") else a) == STOP_MOVING_ACTION_VALUE
        }
        env = self._fork_env()

        policy, session_id = self._make_override_policy(env, overrides)
        detector = ConflictDetectionCallbacks(
            blocked_threshold=blocked_threshold,
            detect_deadlocks=detect_deadlocks,
        )

        try:
            detector.on_episode_start(env=env)
            policy.start_episode()

            steps_run = 0
            terminated_early = False
            for _ in range(max_steps):
                if self._all_done(env):
                    terminated_early = True
                    break

                handles = env.get_agent_handles()
                observations = {h: env for h in handles}  # FullEnv-style fallback

                policy.start_step()
                actions = policy.act_many(handles, observations)

                try:
                    env.step(actions)
                except Exception as e:
                    if "Episode is done" in str(e):
                        policy.end_step()
                        terminated_early = True
                        break
                    raise

                policy.end_step()
                detector.on_episode_step(env=env)
                steps_run += 1

            policy.end_episode()
            detector.on_episode_end(env=env)

            kpis = detector.get_kpis()
            # Override with post-mortem deadlock count (operator definition:
            # agents physically blocked face-to-face, can't reach target).
            kpis = dict(kpis)
            kpis["deadlocks"] = count_deadlocked_agents(env)
            result = BranchResult(
                conflicts=detector.get_conflicts(),
                kpis=kpis,
                snapshots=detector.get_snapshots(),
                total_agents=len(env.agents),
                success_count=self._count_done(env),
                elapsed_steps=int(getattr(env, "_elapsed_steps", steps_run)),
                finished=terminated_early,
                terminated_early=terminated_early,
            )
            return result
        finally:
            # Always clean up the temporary override store entry.
            try:
                override_manager.clear_all(session_id)
            except Exception:
                pass

    # ── internals ───────────────────────────────────────────────────

    def _fork_env(self) -> RailEnv:
        """Return a deterministic clone of the base env.

        Uses RailEnvPersister.save → load_new so the clone is a fresh
        RailEnv instance with the same rail layout, agents, schedule
        and current state (incl. current step count) as the base env.
        
        The forked env inherits _elapsed_steps from base_env so the
        branch continues from the current simulation step.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"branch-{uuid.uuid4().hex}.pkl"
            RailEnvPersister.save(self._base_env, str(path))
            forked, _ = RailEnvPersister.load_new(str(path))
        
        # Preserve the current step count from the base env so the branch
        # continues from where the main simulation currently is.
        if hasattr(self._base_env, "_elapsed_steps"):
            forked._elapsed_steps = self._base_env._elapsed_steps
        
        return forked

    def _make_override_policy(
        self,
        env: RailEnv,
        overrides: Dict[int, RailEnvActions],
    ) -> OverridePolicy:
        """Wire up an OverridePolicy with a temporary session_id, push
        the user's overrides into the global override_manager under
        that session_id, and return the wrapped policy."""
        from app.core.override_manager import override_manager

        session_id = f"branch-{uuid.uuid4().hex[:8]}"
        for handle, action in overrides.items():
            # Accept RailEnvActions enum members or plain ints.
            try:
                action_int = int(action.value)  # IntEnum-style member
            except AttributeError:
                action_int = int(action)
            override_manager.set(session_id, int(handle), action_int)

        default = self._policy_factory()
        default.reset(env)
        wrapped = OverridePolicy(default, session_id)
        wrapped.reset(env)
        return wrapped, session_id

    @staticmethod
    def _all_done(env: RailEnv) -> bool:
        from flatland.envs.step_utils.states import TrainState
        return all(getattr(a, "state", None) == TrainState.DONE for a in env.agents)

    @staticmethod
    def _count_done(env: RailEnv) -> int:
        from flatland.envs.step_utils.states import TrainState
        return sum(
            1 for a in env.agents
            if getattr(a, "state", None) == TrainState.DONE
        )
