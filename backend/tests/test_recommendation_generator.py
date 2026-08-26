"""Tests for current RecommendationGenerator."""
import warnings
warnings.filterwarnings("ignore")

from app.core.recommendation_generator import (
    _utility_score,
    estimate_confidence,
    generate_recommendations,
)
from app.core.scenario_builder import Scenario
from app.core.scenario_runner import BranchResult
from app.models.hmi import Recommendation


def _result(success=1, total=1, delay=0, deadlocks=0):
    return BranchResult(
        total_agents=total,
        success_count=success,
        kpis={
            "total_delay": delay,
            "num_blocked_events": 0,
            "num_swap_attempts": 0,
            "num_deadlock_cycles": deadlocks,
        },
    )


def _scenario(name, policy_id, score, result=None, tag=None):
    return Scenario(
        name=name,
        policy_id=policy_id,
        score=score,
        tag=tag,
        result=result or _result(),
    )


def test_utility_score_clamp_bounds():
    assert _utility_score(-1.0) == 0.0
    assert _utility_score(0.0) == 0.0
    assert _utility_score(0.5) == 0.5
    assert _utility_score(1.0) == 1.0
    assert _utility_score(2.0) == 1.0


# ── Confidence estimate ───────────────────────────────────────────────────────
# Confidence answers "does this option really beat the current course?", not
# "is the outcome good?". The two must be able to disagree.

def test_confidence_is_a_coin_flip_when_candidate_ties_baseline():
    baseline = _scenario("baseline", "deadlock_avoidance", 0.60)
    cand = _scenario("Forward Only", "forward_only", 0.60)
    est = estimate_confidence(cand, baseline, [baseline, cand])
    assert est.confidence == 0.5
    assert est.margin == 0.0


def test_confidence_rises_with_margin():
    baseline = _scenario("baseline", "deadlock_avoidance", 0.20)
    near = _scenario("Forward Only", "forward_only", 0.30)
    far = _scenario("Shortest Path", "shortest_path", 0.90)
    pool = [baseline, near, far]
    assert (estimate_confidence(far, baseline, pool).confidence
            > estimate_confidence(near, baseline, pool).confidence
            > 0.5)


def test_wider_disagreement_lowers_confidence_for_the_same_margin():
    # Same candidate, same margin (+0.20), but the second ensemble's branches
    # lie much further apart — the same lead is weaker evidence there.
    baseline = _scenario("baseline", "deadlock_avoidance", 0.50)
    cand = _scenario("Forward Only", "forward_only", 0.70)
    tight = [baseline, cand, _scenario("Random", "random", 0.55)]
    scattered = [baseline, cand, _scenario("Random", "random", -0.90)]
    assert (estimate_confidence(cand, baseline, scattered).confidence
            < estimate_confidence(cand, baseline, tight).confidence)


def test_confidence_never_claims_certainty():
    baseline = _scenario("baseline", "deadlock_avoidance", -5.0)
    cand = _scenario("Forward Only", "forward_only", 5.0)
    est = estimate_confidence(cand, baseline, [baseline, cand])
    assert est.confidence <= 0.98


def test_confidence_basis_marks_a_missing_ensemble():
    baseline = _scenario("baseline", "deadlock_avoidance", 0.50)
    cand = _scenario("Forward Only", "forward_only", 0.70)
    assert estimate_confidence(cand, baseline, [baseline, cand]).basis == "ensemble-margin"
    assert estimate_confidence(cand, baseline, [cand]).basis == "prior-only"


def test_high_utility_can_still_carry_low_confidence():
    # Baseline is already excellent; the alternative is excellent too but barely
    # ahead. Good outcome, weak evidence — the case the "27%" label hid.
    baseline = _scenario("baseline", "deadlock_avoidance", 0.95)
    cand = _scenario("Forward Only", "forward_only", 0.96)
    est = estimate_confidence(cand, baseline, [baseline, cand])
    assert _utility_score(cand.score) > 0.9
    assert est.confidence < 0.6


def test_generate_recommendations_empty_without_scenarios():
    assert generate_recommendations("sid", []) == []


def test_generate_recommendations_empty_without_baseline():
    scenarios = [_scenario("Forward Only", "forward_only", 0.9)]
    assert generate_recommendations("sid", scenarios) == []


def test_generate_recommendations_empty_without_candidates():
    scenarios = [_scenario("baseline", "deadlock_avoidance", 0.8)]
    assert generate_recommendations("sid", scenarios) == []


def test_generate_recommendations_empty_when_margin_too_small():
    # Candidate beats baseline by only 0.03, below SCORE_MARGIN (0.05).
    scenarios = [
        _scenario("baseline", "deadlock_avoidance", 0.80),
        _scenario("Forward Only", "forward_only", 0.83),
    ]
    assert generate_recommendations("sid", scenarios) == []


def test_generate_recommendations_empty_when_top_has_deadlock():
    scenarios = [
        _scenario("baseline", "deadlock_avoidance", 0.20),
        _scenario("Forward Only", "forward_only", 0.95,
                  result=_result(success=1, total=1, deadlocks=1)),
    ]
    assert generate_recommendations("sid", scenarios) == []


def test_generate_recommendations_returns_top_policy_recommendation():
    scenarios = [
        _scenario("baseline", "deadlock_avoidance", 0.20,
                  result=_result(success=0, total=2, delay=50)),
        _scenario("Forward Only", "forward_only", 0.90,
                  result=_result(success=2, total=2, delay=0)),
        _scenario("Do Nothing", "do_nothing", 0.10),
    ]

    recs = generate_recommendations("sid", scenarios)

    assert len(recs) == 1
    rec = recs[0]
    assert isinstance(rec, Recommendation)
    assert rec.id == "rec_policy_forward_only"
    assert rec.scenarioId == "scn_forward_only"
    assert "Switch to" in rec.title
    assert 0.0 <= rec.confidence <= 1.0
    assert rec.countdownSeconds >= 5
    # The two numbers travel together, each with its own meaning.
    assert rec.utilityScore == 0.9
    assert rec.margin == 0.7
    assert rec.confidence > 0.5
    assert rec.confidenceBasis == "ensemble-margin"


def test_guarantee_surfaces_best_alternative_below_margin():
    # Candidate beats baseline by only 0.03 (below SCORE_MARGIN). Normally empty,
    # but with guarantee=True the demo must still surface a decision moment.
    scenarios = [
        _scenario("baseline", "deadlock_avoidance", 0.80),
        _scenario("Forward Only", "forward_only", 0.83),
    ]
    assert generate_recommendations("sid", scenarios) == []
    recs = generate_recommendations("sid", scenarios, guarantee=True)
    assert len(recs) == 1
    assert recs[0].id == "rec_policy_forward_only"


def test_guarantee_surfaces_best_even_when_worse_than_baseline():
    # Every alternative is worse than DLA. The guarantee still surfaces the best
    # deadlock-free one so the operator can consciously keep the current policy.
    scenarios = [
        _scenario("baseline", "deadlock_avoidance", 0.90),
        _scenario("Forward Only", "forward_only", 0.40),
        _scenario("Random", "random", 0.20),
    ]
    recs = generate_recommendations("sid", scenarios, guarantee=True)
    assert len(recs) == 1
    assert recs[0].id == "rec_policy_forward_only"


def test_guarantee_never_surfaces_deadlock_option():
    # The only alternative deadlocks → guarantee must NOT surface it, even in demo.
    scenarios = [
        _scenario("baseline", "deadlock_avoidance", 0.20),
        _scenario("Forward Only", "forward_only", 0.95,
                  result=_result(success=1, total=1, deadlocks=1)),
    ]
    assert generate_recommendations("sid", scenarios, guarantee=True) == []


def test_guarantee_does_not_duplicate_when_margin_already_met():
    # A candidate already clears the margin → guarantee changes nothing.
    scenarios = [
        _scenario("baseline", "deadlock_avoidance", 0.20),
        _scenario("Forward Only", "forward_only", 0.90),
    ]
    normal = generate_recommendations("sid", scenarios)
    guaranteed = generate_recommendations("sid", scenarios, guarantee=True)
    assert [r.id for r in normal] == [r.id for r in guaranteed]
    assert len(guaranteed) == 1


def test_generate_recommendations_caps_at_three_ranked():
    # The generator surfaces up to 3 qualifying alternatives, ranked by score
    # (best first). All of these clearly beat the baseline.
    scenarios = [
        _scenario("baseline", "deadlock_avoidance", 0.0),
        _scenario("Forward Only", "forward_only", 0.9),
        _scenario("Random", "random", 0.8),
        _scenario("Shortest Path", "shortest_path", 0.7),
        _scenario("Do Nothing", "do_nothing", 0.6),
    ]
    recs = generate_recommendations("sid", scenarios)
    assert len(recs) <= 3
    assert recs[0].id == "rec_policy_forward_only"
