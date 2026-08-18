"""Builds and persists Decision Episodes.

A Decision Episode is a compact, self-contained record of one decision point:
context, what was recommended, what the human did, and what happened. These are
the primary units the pattern analyzer and reflection selector operate on.
"""

from __future__ import annotations

import json
from typing import Any

from database import Database
from scenario_engine import classify_outcome


def _relation_to_recommendation(selected: str, recommended: str) -> str:
    return "followed" if selected == recommended else "overridden"


def build_decision_episode(
    decision_id: str,
    session_id: str,
    step: int,
    decision_point: dict[str, Any],
    selected_strategy: str,
    confirmation_mode: str,
    rationale_mode: str,
    rationale_text: str | None,
    reason_tags: list[str] | None,
    interaction: dict[str, Any],
    observed_outcome: dict[str, Any],
    recommended_strategy: str | None = None,
    learning_adjusted: bool | None = None,
    recommendation_source: str | None = None,
    applied_learning: str | None = None,
) -> dict[str, Any]:
    situation = decision_point.get("situation", {})
    baseline = decision_point.get("baseline_recommendation")
    personalized = decision_point.get("personalized_recommendation")
    # Prefer the recommendation actually shown to the user (adaptive model);
    # fall back to the scenario's static hint for standalone/testing use.
    recommended = recommended_strategy or personalized or baseline
    if learning_adjusted is None:
        learning_influence = bool(decision_point.get("learning_influence", False))
    else:
        learning_influence = bool(learning_adjusted)

    expected_outcome = (
        decision_point.get("outcomes", {})
        .get(selected_strategy, {})
        .get("expected", {})
    )

    episode = {
        "decision_id": decision_id,
        "session_id": session_id,
        "simulation_step": step,
        "context": {
            "time_label": decision_point.get("time_label"),
            "operational_pressure": decision_point.get("operational_pressure"),
            "critical_connection": situation.get("critical_connection", False),
            "connection_buffer_min": situation.get("connection_buffer_min"),
            "extra_delay_minutes": situation.get("current_delay_min"),
            "ripple_risk": situation.get("ripple_risk"),
            "expected_follow_up_conflicts": situation.get(
                "expected_follow_up_conflicts", 0
            ),
            "forecast_confidence": situation.get("forecast_confidence"),
        },
        "recommendation": {
            "baseline_strategy": baseline,
            "recommended_strategy": recommended,
            "learning_adjustment_applied": learning_influence,
            "source": recommendation_source,
            "applied_learning": applied_learning,
        },
        "user_decision": {
            "selected_strategy": selected_strategy,
            "relation_to_recommendation": _relation_to_recommendation(
                selected_strategy, recommended
            ),
            "confirmation_mode": confirmation_mode,
            "rationale_mode": rationale_mode,
            "rationale_text": rationale_text,
            "reason_tags": reason_tags or [],
            "interaction": interaction,
        },
        "outcome": {
            "expected": expected_outcome,
            "observed": observed_outcome,
            "status": classify_outcome(expected_outcome, observed_outcome),
            "follow_up_conflicts": observed_outcome.get("follow_up_conflicts"),
            "network_state": observed_outcome.get("network_state"),
        },
    }
    return episode


def save_decision_episode(
    db: Database,
    episode: dict[str, Any],
    pattern: dict[str, Any] | None = None,
    reflection_score: float | None = None,
) -> None:
    db.execute(
        "INSERT OR REPLACE INTO decision_episodes "
        "(decision_id, session_id, simulation_step, context_json, "
        "recommendation_json, user_decision_json, outcome_json, pattern_json, "
        "reflection_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            episode["decision_id"],
            episode["session_id"],
            episode["simulation_step"],
            json.dumps(episode["context"]),
            json.dumps(episode["recommendation"]),
            json.dumps(episode["user_decision"]),
            json.dumps(episode["outcome"]),
            json.dumps(pattern or {}),
            reflection_score,
        ),
    )


def load_decision_episodes(db: Database, session_id: str) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT * FROM decision_episodes WHERE session_id = ? ORDER BY simulation_step",
        (session_id,),
    )
    episodes = []
    for row in rows:
        episodes.append(
            {
                "decision_id": row["decision_id"],
                "session_id": row["session_id"],
                "simulation_step": row["simulation_step"],
                "context": json.loads(row["context_json"] or "{}"),
                "recommendation": json.loads(row["recommendation_json"] or "{}"),
                "user_decision": json.loads(row["user_decision_json"] or "{}"),
                "outcome": json.loads(row["outcome_json"] or "{}"),
                "pattern": json.loads(row["pattern_json"] or "{}"),
                "reflection_score": row["reflection_score"],
            }
        )
    return episodes
