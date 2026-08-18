"""Tests for the rule-based pattern analyzer."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pattern_analyzer import analyze_pattern, pattern_relation  # noqa: E402


def _episode(step, strategy, critical=True, delay=2, ripple="low"):
    return {
        "decision_id": f"D-{step}",
        "simulation_step": step,
        "context": {
            "critical_connection": critical,
            "extra_delay_minutes": delay,
            "ripple_risk": ripple,
        },
        "user_decision": {"selected_strategy": strategy},
    }


def test_detects_dominant_pattern():
    episodes = [
        _episode(1, "protect_critical_connection"),
        _episode(2, "protect_critical_connection"),
        _episode(3, "protect_critical_connection"),
        _episode(4, "protect_critical_connection"),
        _episode(5, "stabilize_network"),
    ]
    # reference is a later, similar decision
    ref = _episode(6, "stabilize_network")
    pattern = analyze_pattern(episodes, ref)

    assert pattern["expected_strategy"] == "protect_critical_connection"
    assert pattern["sample_size"] == 5
    assert pattern["counts"]["protect_critical_connection"] == 4
    assert 0.7 <= pattern["confidence"] <= 0.9


def test_only_prior_decisions_count():
    episodes = [
        _episode(1, "protect_critical_connection"),
        _episode(2, "stabilize_network"),
        _episode(3, "stabilize_network"),
    ]
    ref = episodes[0]  # step 1, nothing prior
    pattern = analyze_pattern(episodes, ref)
    assert pattern["sample_size"] == 0
    assert pattern["expected_strategy"] is None


def test_similarity_filters_dissimilar_contexts():
    episodes = [
        _episode(1, "protect_critical_connection", critical=True),
        _episode(2, "minimize_delay", critical=False),  # dissimilar
    ]
    ref = _episode(3, "protect_critical_connection", critical=True)
    pattern = analyze_pattern(episodes, ref)
    # only the critical=True prior episode counts
    assert pattern["sample_size"] == 1
    assert pattern["expected_strategy"] == "protect_critical_connection"


def test_pattern_relation():
    pattern = {"expected_strategy": "protect_critical_connection", "sample_size": 4}
    assert pattern_relation(pattern, "protect_critical_connection") == "confirmation"
    assert pattern_relation(pattern, "stabilize_network") == "deviation"
    assert pattern_relation({"sample_size": 0}, "x") == "no_pattern"
