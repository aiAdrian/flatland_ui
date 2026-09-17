"""Small in-memory notification manager for session-scoped HMI events."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.models.hmi import AppNotification, RelatedElement


class NotificationManager:
    def __init__(self) -> None:
        # session_id -> list of event dicts
        self._events: Dict[str, List[dict]] = {}

    def add(
        self,
        session_id: str,
        *,
        kind: str,
        title: str,
        message: str,
        timestamp: int,
        related_kind: Optional[str] = None,
        related_id: Optional[str] = None,
        ttl_steps: int = 30,
        code: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        ev_id = f"evt_{uuid.uuid4().hex[:10]}"
        ev = {
            "id": ev_id,
            "kind": kind,
            "title": title,
            "message": message,
            "timestamp": int(timestamp),
            "expires_at": int(timestamp + max(1, ttl_steps)),
            "related_kind": related_kind,
            "related_id": related_id,
            "code": code,
            "params": dict(params) if params else None,
        }
        self._events.setdefault(session_id, []).append(ev)
        # Keep memory bounded.
        if len(self._events[session_id]) > 200:
            self._events[session_id] = self._events[session_id][-200:]
        return ev_id

    def get_active(self, session_id: str, step: int) -> List[AppNotification]:
        cur = self._events.get(session_id, [])
        active = [e for e in cur if int(e.get("expires_at", -1)) >= int(step)]
        self._events[session_id] = active

        out: List[AppNotification] = []
        for e in active:
            rel = None
            if e.get("related_kind") and e.get("related_id"):
                rel = RelatedElement(kind=e["related_kind"], id=str(e["related_id"]))
            out.append(
                AppNotification(
                    id=str(e["id"]),
                    kind=str(e["kind"]),
                    title=str(e["title"]),
                    message=str(e["message"]),
                    timestamp=int(e["timestamp"]),
                    relatedElement=rel,
                    code=e.get("code"),
                    params=e.get("params"),
                )
            )
        return out

    def clear_session(self, session_id: str) -> None:
        self._events.pop(session_id, None)


notification_manager = NotificationManager()
