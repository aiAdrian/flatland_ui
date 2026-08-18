"""Tests for the live user model (adaptive recommendation + prediction)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from user_model import UserModel  # noqa: E402


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


def _dp(critical=True, delay=2, ripple="low",
        baseline="minimize_delay", personalized=None,
        strategies=("minimize_delay", "protect_critical_connection", "stabilize_network")):
    return {
        "situation": {
            "critical_connection": critical,
            "current_delay_min": delay,
            "ripple_risk": ripple,
        },
        "baseline_recommendation": baseline,
        "personalized_recommendation": personalized,
        "strategies": list(strategies),
    }


def test_cold_start_prediction_is_empty():
    model = UserModel([])
    pred = model.predict(_dp(), step=0)
    assert pred.strategy is None
    assert pred.basis == "cold_start"


def test_prediction_uses_similar_context():
    episodes = [
        _episode(0, "protect_critical_connection"),
        _episode(1, "protect_critical_connection"),
        _episode(2, "protect_critical_connection"),
    ]
    model = UserModel(episodes)
    pred = model.predict(_dp(critical=True), step=3)
    assert pred.strategy == "protect_critical_connection"
    assert pred.basis == "similar_context"
    assert pred.confidence >= 0.6


def test_learned_preference_overrides_baseline():
    episodes = [
        _episode(0, "protect_critical_connection"),
        _episode(1, "protect_critical_connection"),
        _episode(2, "protect_critical_connection"),
    ]
    model = UserModel(episodes)
    rec = model.adaptive_recommendation(_dp(baseline="minimize_delay"), step=3)
    assert rec.recommended == "protect_critical_connection"
    assert rec.adjusted is True
    assert rec.source == "learned"


def test_falls_back_to_scenario_personalization_without_history():
    model = UserModel([])
    rec = model.adaptive_recommendation(
        _dp(baseline="minimize_delay", personalized="protect_critical_connection"),
        step=0,
    )
    assert rec.recommended == "protect_critical_connection"
    assert rec.source == "scenario"


def test_falls_back_to_baseline_when_nothing_known():
    model = UserModel([])
    rec = model.adaptive_recommendation(_dp(baseline="minimize_delay"), step=0)
    assert rec.recommended == "minimize_delay"
    assert rec.adjusted is False
    assert rec.source == "baseline"


def test_preferences_are_normalised_and_sorted():
    episodes = [
        _episode(0, "protect_critical_connection"),
        _episode(1, "protect_critical_connection"),
        _episode(2, "stabilize_network"),
    ]
    model = UserModel(episodes)
    prefs = model.preferences()
    assert prefs[0][0] == "protect_critical_connection"
    assert abs(sum(w for _, w, _ in prefs) - 1.0) < 1e-6
