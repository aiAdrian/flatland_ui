"""Tests for the value profile and the passengers-affected metric."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import create_in_memory_db  # noqa: E402
from director_mode import DirectorSession  # noqa: E402
from live_director import LiveDirector  # noqa: E402
from scenario_engine import load_scenario  # noqa: E402
from values import value_profile  # noqa: E402


def _ep(strategy, mode="reasoned_accept"):
    return {"user_decision": {"selected_strategy": strategy, "confirmation_mode": mode}}


def test_value_profile_dominant():
    eps = [
        _ep("minimize_delay"),
        _ep("minimize_delay"),
        _ep("minimize_delay"),
        _ep("protect_critical_connection"),
    ]
    vp = value_profile(eps)
    assert vp["dominant"] == "Punctuality"
    assert vp["label"] == "Punctuality-first"
    assert vp["dominant_pct"] == 75


def test_value_profile_ignores_passive():
    eps = [
        _ep("minimize_delay", mode="quick_accept"),
        _ep("minimize_delay", mode="deferred_to_ai"),
        _ep("protect_critical_connection", mode="reasoned_accept"),
    ]
    vp = value_profile(eps)
    # only the deliberate protect decision counts
    assert vp["dominant"] == "Passengers & connections"
    assert vp["total"] == 1


def test_passengers_affected_accumulates_on_broken_connection():
    c = LiveDirector(DirectorSession(create_in_memory_db(),
                                     load_scenario("easy_morning")), speed=3.0)
    c._apply_resolution({
        "observed": {"connection": "Broken", "follow_up_conflicts": 0},
        "deferred": False, "kind": "human", "time_label": "09:00",
        "passengers": 120,
    })
    assert c.kpis["passengers_affected"] == 120


def test_punctuality_trap_scenario_shape():
    sc = load_scenario("punctuality_trap")
    assert sc.difficulty == "Story"
    assert len(sc.decision_points) == 9
    for dp in sc.decision_points:
        s = dp["situation"]
        assert s["critical_connection"] is True
        assert isinstance(s["passengers"], int) and s["passengers"] > 0
        # the AI defaults to punctuality (the tempting option)
        assert dp["baseline_recommendation"] == "minimize_delay"
        # minimize_delay reliably breaks the connection here
        obs = dp["outcomes"]["minimize_delay"]["observed"]
        assert any(o["values"]["connection"] == "Broken" for o in obs)


def test_passengers_not_affected_when_protected():
    c = LiveDirector(DirectorSession(create_in_memory_db(),
                                     load_scenario("easy_morning")), speed=3.0)
    c._apply_resolution({
        "observed": {"connection": "Protected", "follow_up_conflicts": 0},
        "deferred": False, "kind": "human", "time_label": "09:00",
        "passengers": 120,
    })
    assert c.kpis["passengers_affected"] == 0
