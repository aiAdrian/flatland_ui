"""The prepared profile has to produce a visible cross-session effect.

The point of seeding is that a short demo shows the loop, not just the reflection
module. That only holds if the carried-over learning actually changes a
recommendation in the demo scenario.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import create_in_memory_db  # noqa: E402
from demo_profile import (  # noqa: E402
    DEMO_PROFILE_ID,
    is_seeded,
    reset_profile,
    seed_demo_profile,
)
from profile_store import ProfileStore  # noqa: E402
from scenario_engine import load_scenario  # noqa: E402
from user_model import UserModel  # noqa: E402


def test_seeded_profile_is_warm_and_carries_learnings():
    db = create_in_memory_db()
    assert not is_seeded(db)

    profile = seed_demo_profile(db)
    assert profile.is_warm
    assert profile.prior_sessions == 1
    assert profile.confirmed_learnings
    # only deliberate decisions may shape the carried tendencies
    assert profile.preferences.get("protect_critical_connection") == 3


def test_seeding_is_idempotent():
    db = create_in_memory_db()
    first = seed_demo_profile(db)
    second = seed_demo_profile(db)
    assert first.prior_sessions == second.prior_sessions == 1
    assert len(first.confirmed_learnings) == len(second.confirmed_learnings)


def test_seeded_profile_shifts_the_recommendation_in_the_demo_scenario():
    """This is the moment the demo is built around."""
    db = create_in_memory_db()
    profile = seed_demo_profile(db)
    scenario = load_scenario("demo_quick")
    model = UserModel(
        [],
        prior_preferences=profile.preferences,
        confirmed_learnings=profile.confirmed_learnings,
    )

    critical_steps = [
        i for i, dp in enumerate(scenario.decision_points)
        if dp["situation"]["critical_connection"]
    ]
    assert critical_steps, "the demo scenario must contain a critical connection"

    for step in critical_steps:
        rec = model.adaptive_recommendation(scenario.decision_points[step], step=step)
        assert rec.source == "learned_confirmed"
        assert rec.adjusted is True, "the banner only fires when it changes something"
        assert rec.recommended == "protect_critical_connection"
        assert rec.baseline == "minimize_delay"
        assert rec.applied_learning


def test_non_critical_points_are_left_alone():
    """A carried learning must not fire everywhere, or it stops meaning anything."""
    db = create_in_memory_db()
    profile = seed_demo_profile(db)
    scenario = load_scenario("demo_quick")
    model = UserModel([], prior_preferences=profile.preferences,
                      confirmed_learnings=profile.confirmed_learnings)

    plain_steps = [
        i for i, dp in enumerate(scenario.decision_points)
        if not dp["situation"]["critical_connection"]
    ]
    for step in plain_steps:
        rec = model.adaptive_recommendation(scenario.decision_points[step], step=step)
        assert rec.source != "learned_confirmed"


def test_reset_removes_everything_about_the_operator():
    db = create_in_memory_db()
    seed_demo_profile(db)
    reset_profile(db, DEMO_PROFILE_ID)

    assert not ProfileStore(db, DEMO_PROFILE_ID).load().is_warm
    for table in ("sessions", "decision_episodes", "learnings", "events"):
        if table == "sessions":
            rows = db.query("SELECT * FROM sessions WHERE profile_id = ?",
                            (DEMO_PROFILE_ID,))
        else:
            rows = db.query(f"SELECT * FROM {table}")
        assert rows == [], f"{table} still holds data for the deleted profile"
