"""Cross-session operator profile.

This is what closes the co-learning loop: confirmed learnings and decision
tendencies persist across sessions for a given operator (``profile_id``). A new
session starts *warm* — the AI already carries a picture of you and applies the
learnings you confirmed before.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from database import Database
from learning_store import STATUS_CONFIRMED, STATUS_CORRECTED


@dataclass
class OperatorProfile:
    profile_id: str
    prior_sessions: int = 0
    prior_decisions: int = 0
    prior_deferrals: int = 0
    preferences: dict[str, int] = field(default_factory=dict)
    confirmed_learnings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_warm(self) -> bool:
        return self.prior_decisions > 0 or bool(self.confirmed_learnings)


class ProfileStore:
    def __init__(self, db: Database, profile_id: str) -> None:
        self.db = db
        self.profile_id = profile_id

    def _prior_session_ids(self, exclude_session_id: str | None) -> list[str]:
        rows = self.db.query(
            "SELECT session_id FROM sessions WHERE profile_id = ?",
            (self.profile_id,),
        )
        return [r["session_id"] for r in rows if r["session_id"] != exclude_session_id]

    def load(self, exclude_session_id: str | None = None) -> OperatorProfile:
        session_ids = self._prior_session_ids(exclude_session_id)
        profile = OperatorProfile(profile_id=self.profile_id,
                                  prior_sessions=len(session_ids))
        if not session_ids:
            return profile

        placeholders = ",".join("?" for _ in session_ids)

        # aggregate human decision tendencies from prior sessions
        rows = self.db.query(
            f"SELECT user_decision_json FROM decision_episodes "
            f"WHERE session_id IN ({placeholders})",
            tuple(session_ids),
        )
        # passive accepts and deadline deferrals are NOT confirmed preference
        passive = {"quick_accept", "deferred_to_ai"}
        for r in rows:
            ud = json.loads(r["user_decision_json"] or "{}")
            strat = ud.get("selected_strategy")
            mode = ud.get("confirmation_mode")
            if strat:
                profile.prior_decisions += 1
                if mode == "deferred_to_ai":
                    profile.prior_deferrals += 1
                if mode not in passive:  # only deliberate choices shape preferences
                    profile.preferences[strat] = profile.preferences.get(strat, 0) + 1

        # confirmed / corrected learnings carried across sessions
        lrows = self.db.query(
            f"SELECT * FROM learnings WHERE session_id IN ({placeholders}) "
            f"AND status IN (?, ?)",
            tuple(session_ids) + (STATUS_CONFIRMED, STATUS_CORRECTED),
        )
        for r in lrows:
            profile.confirmed_learnings.append(
                {
                    "learning_id": r["learning_id"],
                    "statement": r["statement"],
                    "conditions": json.loads(r["conditions_json"] or "{}"),
                    "confidence": r["confidence"],
                    "status": r["status"],
                    "evidence": json.loads(r["evidence_json"] or "{}"),
                }
            )
        return profile

    def prediction_accuracy_history(self) -> list[tuple[str, float]]:
        """Per-session prediction accuracy (%), oldest first — shows the AI
        getting better at anticipating this operator over time."""
        rows = self.db.query(
            "SELECT session_id, started_at FROM sessions "
            "WHERE profile_id = ? ORDER BY started_at",
            (self.profile_id,),
        )
        history: list[tuple[str, float]] = []
        for idx, r in enumerate(rows, start=1):
            eps = self.db.query(
                "SELECT user_decision_json FROM decision_episodes WHERE session_id = ?",
                (r["session_id"],),
            )
            seen = hits = 0
            for e in eps:
                ud = json.loads(e["user_decision_json"] or "{}")
                inter = ud.get("interaction", {})
                if inter.get("predicted_strategy"):
                    seen += 1
                    if inter.get("prediction_correct"):
                        hits += 1
            if seen:
                history.append((f"S{idx}", round(hits / seen * 100, 1)))
        return history
