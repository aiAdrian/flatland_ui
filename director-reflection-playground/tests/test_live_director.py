"""Headless end-to-end test of the Live Director controller."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import create_in_memory_db  # noqa: E402
from director_mode import DirectorSession  # noqa: E402
from live_director import LiveDirector  # noqa: E402
from scenario_engine import load_scenario  # noqa: E402
from strategies import CONFIRMATION_DEFERRED, CONFIRMATION_QUICK_ACCEPT  # noqa: E402


def _intervention_count(scenario):
    return sum(
        1 for dp in scenario.decision_points
        if dp.get("event", {}).get("severity") == "intervention"
    )


def _run_shift(decide_fn, scenario_id="easy_morning"):
    db = create_in_memory_db()
    scenario = load_scenario(scenario_id)
    session = DirectorSession(db, scenario)
    controller = LiveDirector(session, speed=100.0)  # fast: jump between events

    guard = 0
    while controller.status != "ended" and guard < 800:
        guard += 1
        token = controller.tick(1.0)
        if token == "await":
            decide_fn(controller)
        elif token == "timeout":
            controller.defer()
    return session, controller


def test_full_shift_accepting_all():
    session, controller = _run_shift(
        lambda c: c.decide(c.current.recommended, CONFIRMATION_QUICK_ACCEPT)
    )
    assert controller.status == "ended"
    # only intervention events require a human decision; info events are AI-handled
    n_interventions = _intervention_count(session.scenario)
    episodes = session.episodes()
    assert len(episodes) == n_interventions
    assert controller.kpis["decisions"] == n_interventions


def test_full_shift_all_deferred_counts_deferrals():
    # never decide -> every intervention should time out and defer to the AI
    session, controller = _run_shift(lambda c: None)
    assert controller.status == "ended"
    n_interventions = _intervention_count(session.scenario)
    episodes = session.episodes()
    assert len(episodes) == n_interventions
    assert controller.kpis["deferrals"] == n_interventions
    modes = {ep["user_decision"]["confirmation_mode"] for ep in episodes}
    assert modes == {CONFIRMATION_DEFERRED}


def test_info_events_are_auto_handled_without_human_decision():
    session, controller = _run_shift(
        lambda c: c.decide(c.current.recommended, CONFIRMATION_QUICK_ACCEPT),
        scenario_id="stress_test",
    )
    n_interventions = _intervention_count(session.scenario)
    # far fewer human decisions than total decision points (most are AI-handled)
    assert len(session.episodes()) == n_interventions
    assert n_interventions < session.num_decisions()
    # the AI-handled events show up in the attention feed
    assert any(item["by"] == "AI" for item in controller.feed)


def test_deferred_uses_recommended_strategy():
    db = create_in_memory_db()
    scenario = load_scenario("busy_junction")
    session = DirectorSession(db, scenario)
    controller = LiveDirector(session, speed=100.0)

    # advance to the first await
    for _ in range(50):
        if controller.tick(1.0) == "await":
            break
    recommended = controller.current.recommended
    episode = controller.defer()
    assert episode["user_decision"]["selected_strategy"] == recommended
    assert episode["user_decision"]["confirmation_mode"] == CONFIRMATION_DEFERRED


def test_outcome_is_deferred_not_immediate():
    db = create_in_memory_db()
    scenario = load_scenario("easy_morning")
    session = DirectorSession(db, scenario)
    controller = LiveDirector(session, speed=1.0)  # 1 sim-min per second

    for _ in range(60):
        if controller.tick(1.0) == "await":
            break
    controller.decide(controller.current.recommended, CONFIRMATION_QUICK_ACCEPT)

    # right after deciding: episode stored, but operational KPIs NOT yet applied
    assert len(session.episodes()) == 1
    assert controller.kpis["decisions"] == 0
    assert len(controller.pending) == 1

    # let enough sim-time pass for the effect to materialise (delay up to 12 min)
    for _ in range(20):
        controller.tick(1.0)
        if controller.kpis["decisions"] == 1:
            break
    assert controller.kpis["decisions"] == 1
    assert controller.consume_resolution() is not None


def _controller(scenario_id="demo_quick"):
    db = create_in_memory_db()
    session = DirectorSession(db, load_scenario(scenario_id))
    return LiveDirector(session, speed=3.0)


def test_is_bad_outcome():
    assert LiveDirector._is_bad_outcome({"connection": "Broken"})
    assert LiveDirector._is_bad_outcome({"follow_up_conflicts": 1})
    assert LiveDirector._is_bad_outcome({"network_state": "unstable"})
    assert not LiveDirector._is_bad_outcome(
        {"connection": "Protected", "follow_up_conflicts": 0, "network_state": "stable"})


def test_bad_resolution_seeds_a_consequence():
    c = _controller()
    c._apply_resolution({
        "observed": {"connection": "Broken", "follow_up_conflicts": 1},
        "deferred": True, "kind": "human", "time_label": "08:03",
    })
    assert c.pending_consequence is not None
    assert c.pending_consequence["source_time"] == "08:03"
    assert "AI" in c.pending_consequence["cause"]  # deferred -> "you let the AI decide"
    assert c.pending_consequence["carried_delay"] >= 1
    assert c.pending_consequence["mechanism"]


def test_carry_penalty_adds_follow_up_conflict():
    c = _controller()
    before = c.kpis["follow_up_conflicts"]
    c._apply_resolution({
        "observed": {"connection": "Protected", "follow_up_conflicts": 0,
                     "network_state": "stable"},
        "deferred": False, "kind": "human", "time_label": "08:06",
        "carry_penalty": True,
    })
    assert c.kpis["follow_up_conflicts"] == before + 1


def test_consequence_carries_into_next_decision():
    c = _controller()
    c.pending_consequence = {"source_time": "08:03", "reason": "a broken connection propagated"}
    # open an intervention decision point (demo_quick has one at index 1)
    c._open_decision(1)
    assert c.current is not None
    assert c.current.carry_forward is not None
    assert c.current.carry_forward["source_time"] == "08:03"
    # consumed, so it doesn't leak into the following moment
    assert c.pending_consequence is None


def test_skip_to_next_moment_reaches_intervention():
    db = create_in_memory_db()
    scenario = load_scenario("demo_quick")
    session = DirectorSession(db, scenario)
    controller = LiveDirector(session, speed=3.0)
    controller.skip_to_next_moment()
    assert controller.status == "awaiting"
    assert controller.current is not None
    # at least one routine info event was auto-handled on the way
    assert any(item["by"] == "AI" for item in controller.feed)


def test_kpis_accumulate():
    session, controller = _run_shift(
        lambda c: c.decide(c.current.recommended, CONFIRMATION_QUICK_ACCEPT)
    )
    k = controller.kpis
    assert k["decisions"] > 0
    assert k["added_delay_min"] >= 0
    assert k["connections_kept"] + k["connections_lost"] >= 0
