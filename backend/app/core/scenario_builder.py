"""ScenarioBuilder — what-if simulation across alternative POLICIES.

Operator question: "What if I switched to policy X for the whole fleet?"
We answer by running each candidate policy from the current env state
forward over a short horizon and reporting outcome KPIs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from flatland.envs.rail_env import RailEnv

from app.core.scenario_runner import BranchResult, TrajectoryBranchRunner
from app.policies.base import Policy


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
    ):
        self._env = base_env
        self._baseline_id = baseline_policy_id
        self._baseline_factory = baseline_policy_factory
        self._weights = scoring_weights

    def generate_scenarios(
        self,
        candidate_policies: List[PolicyEntry],
        horizon: int = 50,
        blocked_threshold: int = 3,
    ) -> List[Scenario]:
        baseline_runner = TrajectoryBranchRunner(self._env, self._baseline_factory)
        baseline_result = baseline_runner.run_branch(
            overrides={}, max_steps=horizon, blocked_threshold=blocked_threshold,
        )
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
                result = runner.run_branch(
                    overrides={}, max_steps=horizon, blocked_threshold=blocked_threshold,
                )
            except Exception:
                continue
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
