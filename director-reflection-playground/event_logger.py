"""Structured event logging.

Every meaningful interaction produces an event row in SQLite. Events can also be
exported to JSONL for offline inspection. Event types and actors are kept as
module constants so callers use a controlled vocabulary.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database import Database

# -- actors ----------------------------------------------------------------- #
ACTOR_HUMAN = "human"
ACTOR_DIRECTOR_MODE = "director_mode"
ACTOR_REFLECTION_AGENT = "fake_reflection_agent"
ACTOR_SCENARIO_ENGINE = "scenario_engine"

# -- event types ------------------------------------------------------------ #
EVENT_SESSION_STARTED = "session_started"
EVENT_SCENARIO_SELECTED = "scenario_selected"
EVENT_RECOMMENDATION_CREATED = "recommendation_created"
EVENT_PREDICTION_MADE = "prediction_made"
EVENT_AI_AUTONOMOUS = "ai_autonomous_action"
EVENT_EXPLANATION_OPENED = "explanation_opened"
EVENT_ALTERNATIVE_INSPECTED = "alternative_inspected"
EVENT_DECISION_COMMITTED = "decision_committed"
EVENT_RATIONALE_SUBMITTED = "rationale_submitted"
EVENT_OUTCOME_OBSERVED = "outcome_observed"
EVENT_REFLECTION_STARTED = "reflection_started"
EVENT_REFLECTION_CASE_SELECTED = "reflection_case_selected"
EVENT_REFLECTION_ANSWER_SUBMITTED = "reflection_answer_submitted"
EVENT_LEARNING_PROPOSED = "learning_proposed"
EVENT_LEARNING_CONFIRMED = "learning_confirmed"
EVENT_LEARNING_EDITED = "learning_edited"
EVENT_LEARNING_REJECTED = "learning_rejected"
EVENT_SESSION_COMPLETED = "session_completed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventLogger:
    def __init__(self, db: Database, session_id: str) -> None:
        self.db = db
        self.session_id = session_id

    def log(
        self,
        event_type: str,
        actor: str,
        payload: dict[str, Any] | None = None,
        simulation_step: int | None = None,
    ) -> str:
        event_id = f"E-{uuid.uuid4().hex[:12]}"
        self.db.execute(
            "INSERT INTO events (event_id, session_id, timestamp, simulation_step, "
            "actor, event_type, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                self.session_id,
                _now(),
                simulation_step,
                actor,
                event_type,
                json.dumps(payload or {}),
            ),
        )
        return event_id

    # -- retrieval --------------------------------------------------------- #
    def events(self) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp",
            (self.session_id,),
        )
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            result.append(item)
        return result

    def export_jsonl(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for event in self.events():
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return path
