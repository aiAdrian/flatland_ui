"""Tests for current RecommendationGenerator."""
import warnings
warnings.filterwarnings("ignore")

from app.core.recommendation_generator import _confidence, generate_recommendations
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


def test_confidence_clamp_bounds():
    assert _confidence(-1.0) == 0.0
    assert _confidence(0.0) == 0.0
    assert _confidence(0.5) == 0.5
    assert _confidence(1.0) == 1.0
    assert _confidence(2.0) == 1.0


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
