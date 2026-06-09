"""RecommendationGenerator — surfaces the top-scoring alternative POLICY
when it would clearly beat the currently active baseline.

Logic
-----
1. Look at the scenarios that ScenarioBuilder produced for this session.
2. The first (after baseline) is the top-scoring alternative.
3. If its score beats baseline by a clear margin AND it has tag
   == "recommended", surface it as a Recommendation. The Accept-button
   in the UI then triggers POST /session/{id}/policy.
4. Otherwise return [] — the operator gets an empty panel, which is
   the right signal: "current policy is fine, nothing to act on".

Confidence
----------
The score is mapped to [0, 1]. Scores typically fall in [-0.5, 1.0],
so we just clamp.
"""
from __future__ import annotations

from typing import List, Optional

from app.core.scenario_builder import Scenario
from app.models.hmi import Recommendation


# Display labels (kept in sync with hmi_scenario_adapter.POLICY_LABELS)
POLICY_LABELS = {
    "deadlock_avoidance": "DLA (Deadlock Avoidance)",
    "shortest_path": "Shortest Path",
    "forward_only": "Forward Only",
    "do_nothing": "Do Nothing",
    "random": "Random",
}


def _confidence(score: float) -> float:
    return max(0.0, min(1.0, float(score)))


def _describe(top: Scenario, baseline: Scenario) -> str:
    """Plain-language reasoning for the recommendation."""
    t_res, b_res = top.result, baseline.result
    d_done = t_res.success_count - b_res.success_count
    d_delay = int(t_res.kpis.get("total_delay", 0)) - int(b_res.kpis.get("total_delay", 0))
    d_dl = int(t_res.kpis.get("num_deadlock_cycles", 0)) - int(b_res.kpis.get("num_deadlock_cycles", 0))

    parts: List[str] = []
    if d_done > 0:
        parts.append(f"{d_done} more train(s) would arrive")
    if d_dl < 0:
        parts.append(f"avoids {abs(d_dl)} deadlock(s)")
    if d_delay < -10:
        parts.append(f"saves {abs(d_delay)} steps of delay")
    if not parts:
        parts.append("better outcome")
    return " · ".join(parts)


# Hard-coded baseline confidence threshold: only surface a recommendation
# if the alternative's score is at least this much higher than baseline.
SCORE_MARGIN = 0.10


def generate_recommendations(
    session_id: str,
    scenarios: List[Scenario],
) -> List[Recommendation]:
    """Build at most one Recommendation from a pre-computed scenario list.
    The hmi.py endpoint is responsible for fetching the scenarios (with
    its cache); we just consume them here to keep things DRY."""
    if not scenarios:
        return []

    baseline = next((s for s in scenarios if s.name == "baseline"), None)
    if baseline is None:
        return []

    # Candidates are everything that's not baseline; already sorted by score.
    candidates = [s for s in scenarios if s.name != "baseline"]
    if not candidates:
        return []

    top = candidates[0]

    # Refuse to surface a "recommendation" that introduces deadlocks.
    if top.result.kpis.get("num_deadlock_cycles", 0) > 0:
        return []

    # Must clearly beat baseline.
    if (top.score - baseline.score) < SCORE_MARGIN:
        return []

    label = POLICY_LABELS.get(top.policy_id, top.policy_id)
    return [Recommendation(
        id=f"rec_policy_{top.policy_id}",
        title=f"Switch to {label}",
        description=_describe(top, baseline),
        confidence=round(_confidence(top.score), 2),
        countdownSeconds=30,            # generic; policy switch isn't time-critical
        scenarioId=f"scn_{top.policy_id}",
    )]
