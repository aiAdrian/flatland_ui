"""A pre-seeded operator profile so the cross-session effect is visible at once.

The co-learning payoff only shows when a shift starts *warm*: the AI carries
learnings the operator confirmed earlier and visibly shifts its recommendation
because of them. On a cold start that never happens, so a short demo tends to
show the reflection module and nothing of the loop it feeds.

This module writes a plausible previous shift through the normal machinery --
``DirectorSession.commit_decision`` and ``LearningStore`` -- so the profile that
comes out is indistinguishable from one earned by clicking. Nothing here is a
display shortcut: remove the seed and the same code path produces the same UI.
"""

from __future__ import annotations

from typing import Any

from database import Database
from director_mode import DirectorSession
from profile_store import OperatorProfile, ProfileStore
from scenario_engine import load_scenario
from strategies import (
    CONFIRMATION_OVERRIDE,
    CONFIRMATION_REASONED_ACCEPT,
    RATIONALE_REASON_TAGS,
)

DEMO_PROFILE_ID = "nerissa_demo"

# The shift the seeded profile "worked" before. easy_morning has critical
# connections at steps 2, 4 and 6, which is what makes the pattern readable.
_SEED_SCENARIO = "easy_morning"

# (step, strategy, confirmation mode, reason tag) -- all deliberate, because
# passive accepts must not shape a profile.
_SEED_DECISIONS: list[tuple[int, str, str, str]] = [
    (0, "minimize_delay", CONFIRMATION_REASONED_ACCEPT, "Limited additional delay"),
    (2, "protect_critical_connection", CONFIRMATION_REASONED_ACCEPT,
     "Critical connection"),
    (4, "protect_critical_connection", CONFIRMATION_REASONED_ACCEPT,
     "Critical connection"),
    (5, "minimize_delay", CONFIRMATION_REASONED_ACCEPT, "Limited additional delay"),
    (6, "protect_critical_connection", CONFIRMATION_OVERRIDE, "Critical connection"),
]

# What the operator agreed to in the reflection of that shift. The first one is
# the rule that will visibly fire in scenarios with a critical connection; the
# second only applies once the network is under load, so it stays quiet in the
# short demo instead of stacking two effects on top of each other.
_SEED_LEARNINGS: list[dict[str, Any]] = [
    {
        "statement": (
            "Protect critical connections when the additional delay stays limited "
            "and no follow-up conflicts are expected."
        ),
        "target": "protect_critical_connection",
        "conditions": {"extra_delay_limited": True,
                       "follow_up_conflicts_expected": False},
        "boundaries": ["Reconsider when follow-up conflicts are expected."],
        "confidence": "High",
        "supporting": 3,
    },
    {
        "statement": (
            "Stabilise the network first when ripple risk is high, even at the cost "
            "of a connection."
        ),
        "target": "stabilize_network",
        "conditions": {"network_priority": True},
        "boundaries": [],
        "confidence": "Medium",
        "supporting": 2,
    },
]


def is_seeded(db: Database, profile_id: str = DEMO_PROFILE_ID) -> bool:
    return ProfileStore(db, profile_id).load().is_warm


def seed_demo_profile(
    db: Database, profile_id: str = DEMO_PROFILE_ID
) -> OperatorProfile:
    """Write one completed prior shift plus its confirmed learnings.

    Idempotent: if the profile is already warm the existing one is returned, so
    the button cannot pile up duplicate history between demo runs.
    """
    if is_seeded(db, profile_id):
        return ProfileStore(db, profile_id).load()

    scenario = load_scenario(_SEED_SCENARIO)
    session = DirectorSession(db, scenario, seed=scenario.seed, profile_id=profile_id)

    for step, strategy, mode, reason in _SEED_DECISIONS:
        decision_point = scenario.decision_points[step]
        recommended = decision_point.get("baseline_recommendation")
        session.commit_decision(
            step=step,
            decision_point=decision_point,
            selected_strategy=strategy,
            confirmation_mode=mode,
            rationale_mode=RATIONALE_REASON_TAGS,
            rationale_text=None,
            reason_tags=[reason],
            interaction={
                "explanation_viewed": True,
                "confirm_reason": reason,
                "preference_evidence": True,
                # the AI guessed the baseline; it was right where they agreed
                "predicted_strategy": recommended,
                "prediction_correct": strategy == recommended,
            },
            recommended_strategy=recommended,
            learning_adjusted=False,
            recommendation_source="baseline",
        )

    for learning in _SEED_LEARNINGS:
        learning_id = session.learning_store.create_candidate(
            session.session_id,
            {
                "statement": learning["statement"],
                "conditions": {**learning["conditions"],
                               "target_strategy": learning["target"]},
                "boundaries": learning["boundaries"],
                "confidence": learning["confidence"],
                "evidence": {
                    "supporting_decisions": learning["supporting"],
                    "contradictory_decisions": 0,
                    "evidence_basis": "similar_decisions",
                    "target_strategy": learning["target"],
                    "expected_pattern": learning["target"],
                    "supporting_examples": [],
                    "contradictory_examples": [],
                },
            },
        )
        session.learning_store.confirm(learning_id)

    session.complete()
    return ProfileStore(db, profile_id).load()


def reset_profile(db: Database, profile_id: str) -> None:
    """Delete everything stored under this operator: history and learnings.

    The operator has to be able to see and drop what the system keeps about
    them; without this the only way out is deleting the database file.
    """
    rows = db.query(
        "SELECT session_id FROM sessions WHERE profile_id = ?", (profile_id,)
    )
    session_ids = [r["session_id"] for r in rows]
    for session_id in session_ids:
        db.execute("DELETE FROM learnings WHERE session_id = ?", (session_id,))
        db.execute("DELETE FROM decision_episodes WHERE session_id = ?", (session_id,))
        db.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM sessions WHERE profile_id = ?", (profile_id,))
