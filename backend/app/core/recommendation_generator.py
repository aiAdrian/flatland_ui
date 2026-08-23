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

Utility score vs. confidence
----------------------------
These are two different numbers and the panel used to show only one of them,
mislabelled (see docs/reading/2026-08-22-hmi-review-workshop.md, "27%"):

* **utility score** — how good the option's simulated outcome is on the weighted
  KPI scale (``Scenario.score``, driven by the operator's own KPI sliders),
  clamped to [0, 1].
* **confidence** — how sure we are that the option really beats the course
  currently being flown. Estimated from the *ensemble of policy branches* the
  ScenarioBuilder already runs: the candidate's margin over the baseline,
  measured against how far apart the branches lie overall. A margin that is
  large relative to the spread is strong evidence; the same margin among widely
  scattered branches is weak evidence.

Honest limits of that estimate — the UI must not claim more than this:
each branch is a *single deterministic rollout* from the current state, so the
spread expresses disagreement between policies, not the stochastic variance of
any one policy. The number is therefore *model-reported*, not calibrated
against observed outcomes. Calibration needs logged decision outcomes and the
evidential-NN work tracked in docs/plans/widget-a1-risk-uncertainty.md §4.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import pstdev
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
    "goal_directed": "Director Plan",
}


def _utility_score(score: float) -> float:
    """Outcome quality on the weighted KPI scale, clamped to [0, 1].

    Scores typically fall in [-0.5, 1.0], so clamping is enough. This is NOT a
    confidence — see the module docstring.
    """
    return max(0.0, min(1.0, float(score)))


# Floor for the ensemble spread. Without it a run where every branch scores
# almost the same would divide a tiny margin by a tinier spread and report
# near-certainty off rounding noise. Same order of magnitude as SCORE_MARGIN.
_MIN_DISPERSION = 0.05

# A single deterministic rollout per policy cannot justify claiming certainty,
# so the estimate is kept off the 0/1 rails on principle.
_CONFIDENCE_FLOOR = 0.02
_CONFIDENCE_CEILING = 0.98


@dataclass(frozen=True)
class ConfidenceEstimate:
    """The confidence number plus the evidence it rests on."""
    confidence: float
    margin: float
    dispersion: float
    basis: str


def estimate_confidence(
    candidate: Scenario,
    baseline: Scenario,
    scenarios: List[Scenario],
) -> ConfidenceEstimate:
    """P(candidate beats the current course), from the branch ensemble.

    ``margin / spread`` is squashed through a logistic, so a candidate that
    merely ties the baseline lands at 0.5 — an honest coin flip — and confidence
    grows only as the margin outgrows the disagreement between branches.
    """
    margin = float(candidate.score) - float(baseline.score)
    scores = [float(s.score) for s in scenarios]

    if len(scores) >= 2:
        dispersion = pstdev(scores)
        basis = "ensemble-margin"
    else:
        dispersion = 0.0
        basis = "prior-only"

    scale = max(dispersion, _MIN_DISPERSION)
    confidence = 1.0 / (1.0 + math.exp(-margin / scale))
    confidence = max(_CONFIDENCE_FLOOR, min(_CONFIDENCE_CEILING, confidence))

    return ConfidenceEstimate(
        confidence=round(confidence, 2),
        margin=round(margin, 3),
        dispersion=round(dispersion, 3),
        basis=basis,
    )


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
    guarantee: bool = False,
) -> List[Recommendation]:
    """Build recommendations from a pre-computed scenario list. The hmi.py
    endpoint fetches the scenarios (with its cache); we just consume them here
    to keep things DRY.

    ``guarantee`` (demo/study mode): when no candidate beats the baseline by
    ``SCORE_MARGIN`` the panel is normally empty ("current policy is fine").
    For a demo we don't want an empty panel for a whole run, so if nothing
    clears the margin we fall back to surfacing the single best non-deadlock
    alternative anyway — the operator always has a concrete option to weigh.
    Only guaranteed options with a real trade-off would be surfaced; a strictly
    worse-or-equal alternative is still shown so the human can consciously keep
    the current policy (that decision moment is the point). This never invents
    deadlock-causing options and never overrides the normal margin ranking."""
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
        recs.append(_to_recommendation(cand, baseline, scenarios))

    # Demo guarantee: nothing cleared the margin → surface the best
    # deadlock-free alternative so the panel is never silently empty.
    if not recs and guarantee:
        best = next(
            (c for c in candidates
             if c.result.kpis.get("num_deadlock_cycles", 0) == 0),
            None,
        )
        if best is not None:
            recs.append(_to_recommendation(best, baseline, scenarios))

    return recs


def _to_recommendation(
    cand: Scenario,
    baseline: Scenario,
    scenarios: List[Scenario],
) -> Recommendation:
    label = POLICY_LABELS.get(cand.policy_id, cand.policy_id)
    estimate = estimate_confidence(cand, baseline, scenarios)
    return Recommendation(
        id=f"rec_policy_{cand.policy_id}",
        title=f"Switch to {label}",
        description="",                 # no explanation (by design)
        confidence=estimate.confidence,
        countdownSeconds=30,            # generic; policy switch isn't time-critical
        scenarioId=f"scn_{cand.policy_id}",
        utilityScore=round(_utility_score(cand.score), 2),
        margin=estimate.margin,
        dispersion=estimate.dispersion,
        confidenceBasis=estimate.basis,
    )
