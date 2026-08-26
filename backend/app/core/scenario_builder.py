"""ScenarioBuilder — what-if simulation across alternative POLICIES.

Operator question: "What if I switched to policy X for the whole fleet?"
We answer by running each candidate policy from the current env state
forward over a short horizon and reporting outcome KPIs.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from flatland.envs.rail_env import RailEnv

from app.core.scenario_runner import BranchResult, TrajectoryBranchRunner
from app.policies.base import Policy
from app.utils.agent_compat import agent_direction, agent_position

_perf_log = logging.getLogger("flatland.perf")
_perf_log.setLevel(logging.INFO)
if not _perf_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _perf_log.addHandler(_h)



PolicyFactory = Callable[[], Policy]
PolicyEntry = Tuple[str, PolicyFactory]


@dataclass
class Scenario:
    name: str
    policy_id: str
    result: BranchResult
    score: float = 0.0
    tag: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "policy_id": self.policy_id,
            "score": float(self.score),
            "tag": self.tag,
            "result": self.result.to_dict(),
        }


@dataclass
class ScoringWeights:
    done: float = 1.0
    delay: float = 0.4
    deadlock: float = 0.5


def scoring_weights_from_kpi(
    time: float = 1.0,
    energy: float = 0.5,
    platform_routing: float = 0.5,
    train_routing: float = 0.5,
) -> ScoringWeights:
    """Map the four HMI KPI sliders onto the branch-scoring weights.

    The sliders are normalised (so the absolute slider scale doesn't matter) and
    mapped onto the available branch KPIs (success rate, delay, deadlocks):
      - time            → delay sensitivity
      - energy          → efficiency, folded into delay (no separate steps KPI yet)
      - platform/train routing → throughput (done) + routing safety (deadlock)
    Provisional operationalisation; tune here as the study needs evolve.
    """
    vals = [max(0.0, time), max(0.0, energy), max(0.0, platform_routing), max(0.0, train_routing)]
    s = sum(vals) or 1.0
    t, e, p, r = (v / s for v in vals)
    routing = p + r
    return ScoringWeights(
        done=0.5 + routing,
        delay=t + 0.5 * e,
        deadlock=0.5 + 0.5 * routing,
    )


def score_branch(result: BranchResult,
                 weights: ScoringWeights = ScoringWeights()) -> float:
    sr = result.success_rate
    n_agents = max(1, result.total_agents)
    total_delay = float(result.kpis.get("total_delay", 0))
    norm_delay = min(1.0, total_delay / (50.0 * n_agents))
    n_dl = float(result.kpis.get("num_deadlock_cycles", 0))
    deadlock = weights.deadlock if n_dl > 0 else 0.0
    return weights.done * sr - weights.delay * norm_delay - deadlock


def tag_for(scenario_score: float,
            baseline_score: float,
            result: BranchResult) -> Optional[str]:
    if result.kpis.get("num_deadlock_cycles", 0) > 0:
        return "avoid"
    diff = scenario_score - baseline_score
    if diff > 0.10:
        return "recommended"
    if diff < -0.10:
        return "avoid"
    return None


class ScenarioBuilder:
    def __init__(
        self,
        base_env: RailEnv,
        baseline_policy_id: str,
        baseline_policy_factory: PolicyFactory,
        scoring_weights: ScoringWeights = ScoringWeights(),
        session_id: str | None = None,
    ):
        self._env = base_env
        self._baseline_id = baseline_policy_id
        self._baseline_factory = baseline_policy_factory
        self._weights = scoring_weights
        self._session_id = session_id

    def generate_scenarios(
        self,
        candidate_policies: List[PolicyEntry],
        horizon: int = 50,
        blocked_threshold: int = 3,
    ) -> List[Scenario]:
        # Pull current operator overrides for this session — they apply
        # equally to baseline and all alternative-policy branches.
        overrides: dict = {}
        if self._session_id is not None:
            try:
                from app.core.override_manager import override_manager
                overrides = dict(override_manager.get_all(self._session_id))
            except Exception:
                overrides = {}

        try:
            n_agents = len(self._env.get_agent_handles())
        except Exception:
            n_agents = 0

        # Capture the base env state for history snapshot
        base_elapsed = int(getattr(self._env, "_elapsed_steps", 0) or 0)
        base_snapshot = self._capture_env_state(self._env, base_elapsed)

        baseline_runner = TrajectoryBranchRunner(self._env, self._baseline_factory)
        t0 = time.perf_counter()
        baseline_result = baseline_runner.run_branch(
            overrides=overrides, max_steps=horizon, blocked_threshold=blocked_threshold,
        )
        t_ms = (time.perf_counter() - t0) * 1000
        _perf_log.info(
            f"[SCN] policy={self._baseline_id} role=baseline "
            f"agents={n_agents} horizon={horizon} compute={t_ms:.1f}ms"
        )
        
        # Prepend history snapshot to forecast snapshots
        baseline_result.snapshots = [base_snapshot] + (baseline_result.snapshots or [])
        
        baseline_score = score_branch(baseline_result, self._weights)
        baseline = Scenario(
            name="baseline",
            policy_id=self._baseline_id,
            result=baseline_result,
            score=baseline_score,
            tag=None,
        )

        candidates: List[Scenario] = []
        for cand_id, cand_factory in candidate_policies:
            if cand_id == self._baseline_id:
                continue
            runner = TrajectoryBranchRunner(self._env, cand_factory)
            try:
                t0 = time.perf_counter()
                result = runner.run_branch(
                    overrides=overrides, max_steps=horizon, blocked_threshold=blocked_threshold,
                )
                t_ms = (time.perf_counter() - t0) * 1000
                _perf_log.info(
                    f"[SCN] policy={cand_id} role=candidate "
                    f"agents={n_agents} horizon={horizon} compute={t_ms:.1f}ms"
                )
            except Exception as e:
                _perf_log.info(
                    f"[SCN] policy={cand_id} role=candidate FAILED: {e!r}"
                )
                continue
            
            # Prepend history snapshot
            result.snapshots = [base_snapshot] + (result.snapshots or [])
            
            sc = score_branch(result, self._weights)
            candidates.append(Scenario(
                name=cand_id,
                policy_id=cand_id,
                result=result,
                score=sc,
                tag=tag_for(sc, baseline_score, result),
            ))

        candidates.sort(key=lambda s: s.score, reverse=True)
        return [baseline] + candidates

    @staticmethod
    def _capture_env_state(env: RailEnv, step: int) -> dict:
        """Capture current env state as a snapshot for history."""
        agents_dict = {}
        for h, agent in enumerate(env.agents):
            pos, direction = agent_position(agent), agent_direction(agent)
            if pos is None:
                continue
            agents_dict[str(h)] = {
                "pos": (int(pos[0]), int(pos[1])),
                "dir": int(direction) if direction is not None else 0,
            }
        return {
            "step": int(step),
            "agents": agents_dict,
        }
