"""Tests for cross-session profile persistence and the closed learning loop."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import create_in_memory_db  # noqa: E402
from director_mode import DirectorSession  # noqa: E402
from profile_store import ProfileStore  # noqa: E402
from scenario_engine import load_scenario  # noqa: E402
from strategies import (  # noqa: E402
    CONFIRMATION_QUICK_ACCEPT,
    CONFIRMATION_REASONED_ACCEPT,
)
from user_model import UserModel, learning_applies, learning_target  # noqa: E402


def _confirm_learning(session, statement, target):
    candidate = {
        "statement": statement,
        "conditions": {"target_strategy": target},
        "boundaries": [],
        "confidence": "High",
        "evidence": {"expected_pattern": target, "supporting_decisions": 4},
    }
    lid = session.learning_store.create_candidate(session.session_id, candidate)
    session.learning_store.confirm(lid)


def test_learning_target_and_applies():
    lg = {"conditions": {"target_strategy": "protect_critical_connection"}}
    assert learning_target(lg) == "protect_critical_connection"
    assert learning_applies(lg, {"critical_connection": True,
                                 "expected_follow_up_conflicts": 0}) is True
    assert learning_applies(lg, {"critical_connection": False}) is False


def test_profile_persists_preferences_and_learnings():
    db = create_in_memory_db()
    scenario = load_scenario("easy_morning")

    # session 1: make a few decisions and confirm a learning
    s1 = DirectorSession(db, scenario, profile_id="op")
    for step in (2, 4):  # critical decision points
        s1.commit_decision(
            step=step,
            decision_point=scenario.decision_points[step],
            selected_strategy="protect_critical_connection",
            confirmation_mode=CONFIRMATION_REASONED_ACCEPT,
            rationale_mode="none",
            rationale_text=None,
            reason_tags=None,
            interaction={},
        )
    _confirm_learning(
        s1,
        "Protect critical connections when additional delay is limited.",
        "protect_critical_connection",
    )

    # a different operator must NOT see op's data
    other = ProfileStore(db, "someone_else").load()
    assert not other.is_warm

    profile = ProfileStore(db, "op").load()
    assert profile.is_warm
    assert profile.prior_decisions == 2
    assert profile.preferences.get("protect_critical_connection") == 2
    assert len(profile.confirmed_learnings) == 1


def test_confirmed_learning_drives_recommendation_next_session():
    db = create_in_memory_db()
    scenario = load_scenario("easy_morning")

    s1 = DirectorSession(db, scenario, profile_id="op")
    _confirm_learning(
        s1,
        "Protect critical connections when additional delay is limited.",
        "protect_critical_connection",
    )

    profile = ProfileStore(db, "op").load()
    # a fresh session's model, warm-started from the profile
    model = UserModel([], prior_preferences=profile.preferences,
                      confirmed_learnings=profile.confirmed_learnings)

    critical_dp = scenario.decision_points[2]  # critical connection, baseline minimize_delay
    rec = model.adaptive_recommendation(critical_dp, step=0)
    assert rec.source == "learned_confirmed"
    assert rec.recommended == "protect_critical_connection"
    assert rec.adjusted is True
    assert rec.applied_learning


def test_prediction_accuracy_history():
    db = create_in_memory_db()
    scenario = load_scenario("easy_morning")
    s1 = DirectorSession(db, scenario, profile_id="op")
    # two decisions with predictions: one hit, one miss
    for step, correct in ((2, True), (4, False)):
        s1.commit_decision(
            step=step,
            decision_point=scenario.decision_points[step],
            selected_strategy="protect_critical_connection",
            confirmation_mode=CONFIRMATION_REASONED_ACCEPT,
            rationale_mode="none",
            rationale_text=None,
            reason_tags=None,
            interaction={"predicted_strategy": "protect_critical_connection",
                         "prediction_correct": correct},
        )
    hist = ProfileStore(db, "op").prediction_accuracy_history()
    assert len(hist) == 1
    assert hist[0][1] == 50.0  # 1 of 2 correct


def test_warm_start_prediction_uses_profile():
    db = create_in_memory_db()
    scenario = load_scenario("easy_morning")
    s1 = DirectorSession(db, scenario, profile_id="op")
    for step in (2, 4):
        s1.commit_decision(
            step=step,
            decision_point=scenario.decision_points[step],
            selected_strategy="protect_critical_connection",
            confirmation_mode=CONFIRMATION_REASONED_ACCEPT,
            rationale_mode="none",
            rationale_text=None,
            reason_tags=None,
            interaction={},
        )
    profile = ProfileStore(db, "op").load()
    model = UserModel([], prior_preferences=profile.preferences)
    # non-critical point so no confirmed-learning branch; prediction from profile
    pred = model.predict(scenario.decision_points[0], step=0)
    assert pred.strategy == "protect_critical_connection"
    assert pred.basis == "profile"
