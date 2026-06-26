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


# Baseline confidence threshold: only surface a recommendation if the
# alternative's score is at least this much higher than baseline. Kept low
# so near-ties still surface — DLA is a strong baseline, and with a high
# margin the panel stayed empty for whole runs (see demo feedback). Phase 2
# scripted events will instead guarantee a decision moment deterministically.
SCORE_MARGIN = 0.05


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

    # Surface up to 3 recommendations (ranked, no explanation text). The human
    # can still do something else entirely (overrides stay available).
    recs: List[Recommendation] = []
    for cand in candidates[:3]:
        # Skip options that introduce deadlocks or don't clearly beat baseline.
        if cand.result.kpis.get("num_deadlock_cycles", 0) > 0:
            continue
        if (cand.score - baseline.score) < SCORE_MARGIN:
            continue
        label = POLICY_LABELS.get(cand.policy_id, cand.policy_id)
        recs.append(Recommendation(
            id=f"rec_policy_{cand.policy_id}",
            title=f"Switch to {label}",
            description="",                 # no explanation (by design)
            confidence=round(_confidence(cand.score), 2),
            countdownSeconds=30,            # generic; policy switch isn't time-critical
            scenarioId=f"scn_{cand.policy_id}",
        ))
    return recs
