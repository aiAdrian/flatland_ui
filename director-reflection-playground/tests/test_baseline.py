"""Tests for the counterfactual 'AI unattended' baseline."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from baseline import ai_only_shift  # noqa: E402
from database import create_in_memory_db  # noqa: E402
from director_mode import DirectorSession  # noqa: E402
from live_director import LiveDirector  # noqa: E402
from scenario_engine import load_scenario  # noqa: E402


def test_ai_only_shift_is_deterministic():
    sc = load_scenario("punctuality_trap")
    a = ai_only_shift(sc, sc.seed)
    b = ai_only_shift(sc, sc.seed)
    assert a == b


def test_ai_unattended_strands_passengers_in_the_trap():
    sc = load_scenario("punctuality_trap")
    ai = ai_only_shift(sc, sc.seed)
    # the AI default (minimize_delay) breaks every connection -> many passengers
    assert ai["passengers_affected"] > 0
    assert ai["connections_lost"] >= 5


def test_protecting_beats_ai_unattended_on_passengers():
    sc = load_scenario("punctuality_trap")
    db = create_in_memory_db()
    session = DirectorSession(db, sc)
    c = LiveDirector(session, speed=3.0)
    g = 0
    while c.status != "ended" and g < 200:
        g += 1
        if c.tick(9999) == "await":
            c.decide("protect_critical_connection", "reasoned_accept",
                     reason_tags=["Critical connection"],
                     interaction={"preference_evidence": True})
    ai = ai_only_shift(sc, session.seed)
    # protecting connections should strand far fewer passengers than AI-unattended
    assert c.kpis["passengers_affected"] < ai["passengers_affected"]
