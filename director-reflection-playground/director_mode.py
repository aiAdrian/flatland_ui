"""Director Mode session controller.

This is the application-level orchestrator that ties together the database,
event logger, scenario engine, decision-episode builder and learning store. The
Streamlit UI (``app.py``) drives a ``DirectorSession`` and never talks to the
lower-level modules directly for state changes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import event_logger as ev
from database import Database
from decision_episode_builder import (
    build_decision_episode,
    load_decision_episodes,
    save_decision_episode,
)
from event_logger import EventLogger
from learning_store import LearningStore
from pattern_analyzer import analyze_pattern
from scenario_engine import Scenario, select_observed_outcome


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DirectorSession:
    """Holds the lifecycle of one director-mode + reflection session."""

    def __init__(self, db: Database, scenario: Scenario, seed: int | None = None,
                 profile_id: str = "default") -> None:
        self.db = db
        self.scenario = scenario
        self.session_id = f"S-{uuid.uuid4().hex[:12]}"
        self.seed = seed if seed is not None else scenario.seed
        self.profile_id = profile_id
        self.logger = EventLogger(db, self.session_id)
        self.learning_store = LearningStore(db)
        self._decision_counter = 0

        db.execute(
            "INSERT INTO sessions (session_id, started_at, ended_at, scenario_id, "
            "difficulty, seed, status, profile_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self.session_id,
                _now(),
                None,
                scenario.scenario_id,
                scenario.difficulty,
                self.seed,
                "running",
                profile_id,
            ),
        )
        self.logger.log(
            ev.EVENT_SESSION_STARTED,
            ev.ACTOR_DIRECTOR_MODE,
            {"scenario_id": scenario.scenario_id, "seed": self.seed},
        )
        self.logger.log(
            ev.EVENT_SCENARIO_SELECTED,
            ev.ACTOR_HUMAN,
            {"scenario_id": scenario.scenario_id, "name": scenario.name},
        )

    # -- decision points --------------------------------------------------- #
    def decision_point(self, index: int) -> dict[str, Any]:
        return self.scenario.decision_points[index]

    def num_decisions(self) -> int:
        return self.scenario.num_decisions

    def log_recommendation(self, step: int, decision_point: dict[str, Any]) -> None:
        self.logger.log(
            ev.EVENT_RECOMMENDATION_CREATED,
            ev.ACTOR_DIRECTOR_MODE,
            {
                "baseline": decision_point.get("baseline_recommendation"),
                "personalized": decision_point.get("personalized_recommendation"),
                "learning_influence": decision_point.get("learning_influence", False),
            },
            simulation_step=step,
        )

    def log_prediction(
        self,
        step: int,
        predicted: str | None,
        confidence: float,
        basis: str,
    ) -> None:
        self.logger.log(
            ev.EVENT_PREDICTION_MADE,
            ev.ACTOR_DIRECTOR_MODE,
            {"predicted": predicted, "confidence": confidence, "basis": basis},
            simulation_step=step,
        )

    def log_explanation_opened(self, step: int, strategy_id: str | None = None) -> None:
        self.logger.log(
            ev.EVENT_EXPLANATION_OPENED,
            ev.ACTOR_HUMAN,
            {"strategy": strategy_id},
            simulation_step=step,
        )

    def log_alternative_inspected(self, step: int, strategy_id: str) -> None:
        self.logger.log(
            ev.EVENT_ALTERNATIVE_INSPECTED,
            ev.ACTOR_HUMAN,
            {"strategy": strategy_id},
            simulation_step=step,
        )

    def commit_decision(
        self,
        step: int,
        decision_point: dict[str, Any],
        selected_strategy: str,
        confirmation_mode: str,
        rationale_mode: str,
        rationale_text: str | None,
        reason_tags: list[str] | None,
        interaction: dict[str, Any],
        recommended_strategy: str | None = None,
        learning_adjusted: bool | None = None,
        recommendation_source: str | None = None,
        applied_learning: str | None = None,
    ) -> dict[str, Any]:
        """Record a committed decision, observe an outcome, build the episode."""
        self._decision_counter += 1
        decision_id = f"D-{self.session_id[-6:]}-{self._decision_counter:03d}"

        self.logger.log(
            ev.EVENT_DECISION_COMMITTED,
            ev.ACTOR_HUMAN,
            {
                "decision_id": decision_id,
                "selected_strategy": selected_strategy,
                "confirmation_mode": confirmation_mode,
            },
            simulation_step=step,
        )
        if rationale_mode != "none" or reason_tags or rationale_text:
            self.logger.log(
                ev.EVENT_RATIONALE_SUBMITTED,
                ev.ACTOR_HUMAN,
                {
                    "rationale_mode": rationale_mode,
                    "reason_tags": reason_tags or [],
                    "rationale_text": rationale_text,
                },
                simulation_step=step,
            )

        observed_outcome = select_observed_outcome(
            decision_point, selected_strategy, self.seed, step
        )
        self.logger.log(
            ev.EVENT_OUTCOME_OBSERVED,
            ev.ACTOR_SCENARIO_ENGINE,
            {"strategy": selected_strategy, "observed": observed_outcome},
            simulation_step=step,
        )

        episode = build_decision_episode(
            decision_id=decision_id,
            session_id=self.session_id,
            step=step,
            decision_point=decision_point,
            selected_strategy=selected_strategy,
            confirmation_mode=confirmation_mode,
            rationale_mode=rationale_mode,
            rationale_text=rationale_text,
            reason_tags=reason_tags,
            interaction=interaction,
            observed_outcome=observed_outcome,
            recommended_strategy=recommended_strategy,
            learning_adjusted=learning_adjusted,
            recommendation_source=recommendation_source,
            applied_learning=applied_learning,
        )

        # compute pattern based on episodes so far (before this one is stored)
        prior = load_decision_episodes(self.db, self.session_id)
        pattern = analyze_pattern(prior + [episode], episode)
        save_decision_episode(self.db, episode, pattern=pattern)
        return episode

    # -- reflection & completion ------------------------------------------ #
    def episodes(self) -> list[dict[str, Any]]:
        return load_decision_episodes(self.db, self.session_id)

    def start_reflection(self) -> None:
        self.logger.log(ev.EVENT_REFLECTION_STARTED, ev.ACTOR_REFLECTION_AGENT)

    def complete(self) -> None:
        self.db.execute(
            "UPDATE sessions SET ended_at = ?, status = ? WHERE session_id = ?",
            (_now(), "completed", self.session_id),
        )
        self.logger.log(ev.EVENT_SESSION_COMPLETED, ev.ACTOR_DIRECTOR_MODE)

    # -- summary ----------------------------------------------------------- #
    def decision_summary(self) -> dict[str, int]:
        from strategies import (
            CONFIRMATION_DEFERRED,
            CONFIRMATION_INFORMED_ACCEPT,
            CONFIRMATION_OVERRIDE,
            CONFIRMATION_QUICK_ACCEPT,
            CONFIRMATION_REASONED_ACCEPT,
            RATIONALE_FREE_TEXT,
        )

        summary = {
            "total": 0,
            "quick_accepts": 0,
            "informed_accepts": 0,
            "reasoned_accepts": 0,
            "overrides": 0,
            "overrides_free_text": 0,
            "deferrals": 0,
        }
        for ep in self.episodes():
            user = ep.get("user_decision", {})
            mode = user.get("confirmation_mode")
            summary["total"] += 1
            if mode == CONFIRMATION_QUICK_ACCEPT:
                summary["quick_accepts"] += 1
            elif mode == CONFIRMATION_INFORMED_ACCEPT:
                summary["informed_accepts"] += 1
            elif mode == CONFIRMATION_REASONED_ACCEPT:
                summary["reasoned_accepts"] += 1
            elif mode == CONFIRMATION_OVERRIDE:
                summary["overrides"] += 1
                if user.get("rationale_mode") == RATIONALE_FREE_TEXT:
                    summary["overrides_free_text"] += 1
            elif mode == CONFIRMATION_DEFERRED:
                summary["deferrals"] += 1
        return summary
