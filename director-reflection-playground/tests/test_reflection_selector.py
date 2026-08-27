"""Tests for the reflection moment selector."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reflection_selector import (  # noqa: E402
    MAX_REFLECTION_MOMENTS,
    score_episode,
    select_reflection_moments,
)
from strategies import (  # noqa: E402
    CASE_OVERRIDE,
    CASE_PATTERN_DEVIATION,
    CASE_UNEXPECTED_OUTCOME,
    CONFIRMATION_OVERRIDE,
    CONFIRMATION_QUICK_ACCEPT,
    CONFIRMATION_REASONED_ACCEPT,
    RATIONALE_FREE_TEXT,
    RATIONALE_NONE,
)


def _episode(step, strategy, confirmation, rationale=RATIONALE_NONE,
             status="Mostly as expected", learning=False, critical=True):
    return {
        "decision_id": f"D-{step}",
        "simulation_step": step,
        "context": {
            "critical_connection": critical,
            "extra_delay_minutes": 2,
            "ripple_risk": "low",
        },
        "recommendation": {
            "recommended_strategy": "protect_critical_connection",
            "learning_adjustment_applied": learning,
        },
        "user_decision": {
            "selected_strategy": strategy,
            "confirmation_mode": confirmation,
            "rationale_mode": rationale,
        },
        "outcome": {"status": status},
    }


def test_override_free_text_scores_high():
    episodes = [
        _episode(1, "protect_critical_connection", CONFIRMATION_REASONED_ACCEPT),
        _episode(2, "protect_critical_connection", CONFIRMATION_REASONED_ACCEPT),
        _episode(3, "stabilize_network", CONFIRMATION_OVERRIDE, RATIONALE_FREE_TEXT),
    ]
    scored = score_episode(episodes[2], episodes)
    # deviation (+5) + override free text (+4)
    assert scored["score"] >= 9
    assert scored["case_type"] in (CASE_PATTERN_DEVIATION, CASE_OVERRIDE)


def test_passive_accepts_do_not_establish_a_pattern():
    """A clicked-through recommendation must not come back as the user's pattern.

    The UI tells the operator that a quick accept is not counted as preference
    evidence, so the reflection may not contradict that afterwards.
    """
    episodes = [
        _episode(1, "protect_critical_connection", CONFIRMATION_QUICK_ACCEPT),
        _episode(2, "protect_critical_connection", CONFIRMATION_QUICK_ACCEPT),
        _episode(3, "stabilize_network", CONFIRMATION_OVERRIDE, RATIONALE_FREE_TEXT),
    ]
    scored = score_episode(episodes[2], episodes)
    assert scored["pattern"]["sample_size"] == 0
    assert scored["pattern_relation"] == "no_pattern"
    assert scored["case_type"] == CASE_OVERRIDE  # still worth reflecting on

    deliberate = [
        _episode(1, "protect_critical_connection", CONFIRMATION_REASONED_ACCEPT),
        _episode(2, "protect_critical_connection", CONFIRMATION_REASONED_ACCEPT),
        _episode(3, "stabilize_network", CONFIRMATION_OVERRIDE, RATIONALE_FREE_TEXT),
    ]
    assert score_episode(deliberate[2], deliberate)["pattern"]["sample_size"] == 2


def test_unexpected_outcome_is_flagged():
    ep = _episode(1, "protect_critical_connection", CONFIRMATION_QUICK_ACCEPT,
                  status="Unexpected outcome")
    scored = score_episode(ep, [ep])
    assert scored["score"] >= 4


def test_selects_at_most_three_moments():
    episodes = [
        _episode(i, "protect_critical_connection", CONFIRMATION_QUICK_ACCEPT)
        for i in range(1, 8)
    ]
    episodes.append(
        _episode(8, "stabilize_network", CONFIRMATION_OVERRIDE, RATIONALE_FREE_TEXT)
    )
    moments = select_reflection_moments(episodes)
    assert len(moments) <= MAX_REFLECTION_MOMENTS


def test_empty_returns_empty():
    assert select_reflection_moments([]) == []


def test_prefers_diverse_case_types():
    episodes = [
        _episode(1, "protect_critical_connection", CONFIRMATION_QUICK_ACCEPT),
        _episode(2, "protect_critical_connection", CONFIRMATION_QUICK_ACCEPT),
        _episode(3, "stabilize_network", CONFIRMATION_OVERRIDE, RATIONALE_FREE_TEXT),
        _episode(4, "protect_critical_connection", CONFIRMATION_QUICK_ACCEPT,
                 status="Unexpected outcome"),
    ]
    moments = select_reflection_moments(episodes)
    case_types = {m["case_type"] for m in moments}
    # should include more than one distinct case type
    assert len(case_types) >= 2
