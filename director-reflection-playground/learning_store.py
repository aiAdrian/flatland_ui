"""Persistence for shared learning candidates and confirmed learnings."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from database import Database

STATUS_PROPOSED = "proposed"
STATUS_CONFIRMED = "confirmed"
STATUS_CORRECTED = "corrected"
STATUS_REJECTED = "rejected"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LearningStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_candidate(
        self, session_id: str, candidate: dict[str, Any]
    ) -> str:
        learning_id = f"L-{uuid.uuid4().hex[:12]}"
        now = _now()
        self.db.execute(
            "INSERT INTO learnings (learning_id, session_id, statement, "
            "conditions_json, boundaries_json, confidence, status, evidence_json, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                learning_id,
                session_id,
                candidate.get("statement", ""),
                json.dumps(candidate.get("conditions", {})),
                json.dumps(candidate.get("boundaries", [])),
                candidate.get("confidence", "Low"),
                STATUS_PROPOSED,
                json.dumps(candidate.get("evidence", {})),
                now,
                now,
            ),
        )
        return learning_id

    def set_status(
        self,
        learning_id: str,
        status: str,
        statement: str | None = None,
    ) -> None:
        if statement is not None:
            self.db.execute(
                "UPDATE learnings SET status = ?, statement = ?, updated_at = ? "
                "WHERE learning_id = ?",
                (status, statement, _now(), learning_id),
            )
        else:
            self.db.execute(
                "UPDATE learnings SET status = ?, updated_at = ? WHERE learning_id = ?",
                (status, _now(), learning_id),
            )

    def confirm(self, learning_id: str) -> None:
        self.set_status(learning_id, STATUS_CONFIRMED)

    def correct(self, learning_id: str, statement: str) -> None:
        self.set_status(learning_id, STATUS_CORRECTED, statement=statement)

    def reject(self, learning_id: str) -> None:
        self.set_status(learning_id, STATUS_REJECTED)

    def learnings(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM learnings WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        result = []
        for row in rows:
            result.append(
                {
                    "learning_id": row["learning_id"],
                    "session_id": row["session_id"],
                    "statement": row["statement"],
                    "conditions": json.loads(row["conditions_json"] or "{}"),
                    "boundaries": json.loads(row["boundaries_json"] or "[]"),
                    "confidence": row["confidence"],
                    "status": row["status"],
                    "evidence": json.loads(row["evidence_json"] or "{}"),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def confirmed_learnings(self, session_id: str) -> list[dict[str, Any]]:
        return [
            learning
            for learning in self.learnings(session_id)
            if learning["status"] in (STATUS_CONFIRMED, STATUS_CORRECTED)
        ]
