"""Disturbance files: scripted things that go wrong, at fixed steps.

A disturbance file is the third layer of a premade setup, on top of the scene
(what the network and the missions are) and the plan (what every train is
supposed to do). It says what interferes::

    { "step": 12, "type": "train_delay", "agent_handle": 1, "delay_steps": 5 }

Deliberately separate from the scene and the plan, because the point of the
setup is to run the *same* scenario and the *same* plan against several
disturbance sets — including none at all, which is the control condition.

Event types follow `docs/plans/scripted-events-plan.md` §2.1. `train_delay`
applies as a Flatland malfunction (`malfunction_down_counter`) rather than as
a new concept, so the train state machine, the delay KPI, the map badge and
the notifications all treat it exactly as they treat an emergent breakdown.

Nothing here is random: given a scene, a plan and a set of disturbance files,
the whole episode is reproducible. That only holds while random malfunctions
are off, which is why the scenarios that ship a plan pin `malfunction_rate` to
zero (`scenario_presets`).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

EVENT_TYPES = ("train_delay", "area_block", "warning")


class DisturbanceError(ValueError):
    """A disturbance file is malformed."""


def parse_disturbance(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate one decoded disturbance file. Raises `DisturbanceError`."""
    events = payload.get("events")
    if not isinstance(events, Sequence) or not events:
        raise DisturbanceError("disturbance has no 'events'")

    parsed: List[Dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping):
            raise DisturbanceError("event is not an object")
        kind = event.get("type")
        if kind not in EVENT_TYPES:
            raise DisturbanceError(f"unknown event type {kind!r}")
        try:
            step = int(event["step"])
        except (KeyError, TypeError, ValueError):
            raise DisturbanceError(f"event {event!r} has no integer 'step'")
        if step < 0:
            raise DisturbanceError("event 'step' must not be negative")

        if kind == "train_delay":
            try:
                int(event["agent_handle"])
                if int(event["delay_steps"]) < 1:
                    raise ValueError("delay_steps must be >= 1")
            except (KeyError, TypeError, ValueError) as exc:
                raise DisturbanceError(f"train_delay event {event!r}: {exc}")
        elif kind == "area_block":
            cells = event.get("cells")
            if not isinstance(cells, Sequence) or not cells:
                raise DisturbanceError(f"area_block event {event!r} has no 'cells'")

        parsed.append(dict(event))

    return {
        "id": str(payload.get("id") or ""),
        "name": str(payload.get("name") or payload.get("id") or "Disturbance"),
        "description": str(payload.get("description") or ""),
        "scenario": payload.get("scenario"),
        "events": sorted(parsed, key=lambda e: int(e["step"])),
    }


def load_disturbance(path: str | Path) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    disturbance = parse_disturbance(payload)
    if not disturbance["id"]:
        disturbance["id"] = Path(path).stem
    return disturbance


def list_disturbances(directory: str | Path | None) -> List[Dict[str, Any]]:
    """Every `*.json` in a scenario's disturbance directory, id-sorted.

    A malformed file is skipped rather than raised: one broken variant must
    not make the scenario that owns it unselectable in the picker.
    """
    if directory is None:
        return []
    folder = Path(directory)
    if not folder.is_dir():
        return []
    found: List[Dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            found.append(load_disturbance(path))
        except (DisturbanceError, ValueError):
            continue
    return found


class DisturbanceScheduler:
    """Fires the events of the selected disturbance files at their steps.

    `tick` is called once per executed env step. Blocked areas are reverted
    when their `duration` expires, so a temporary closure really is temporary.
    """

    def __init__(self, disturbances: Sequence[Mapping[str, Any]] = ()):
        self.events: List[Dict[str, Any]] = sorted(
            (dict(event) for disturbance in disturbances
             for event in disturbance.get("events", [])),
            key=lambda e: int(e["step"]),
        )
        self._fired: set[int] = set()
        self._active_blocks: List[Tuple[Dict[str, Any], int]] = []
        self._saved_transitions: Dict[Tuple[int, int], int] = {}

    def __bool__(self) -> bool:
        return bool(self.events)

    def tick(self, env, step: int) -> List[Dict[str, Any]]:
        """Apply everything due at `step`; return what fired, for the UI."""
        fired: List[Dict[str, Any]] = []
        for index, event in enumerate(self.events):
            if index in self._fired or int(event["step"]) != int(step):
                continue
            self._fired.add(index)
            if self._apply(env, event):
                fired.append(event)

        for block, expires_at in list(self._active_blocks):
            if step >= expires_at:
                self._revert_block(env, block)
                self._active_blocks.remove((block, expires_at))
        return fired

    # ── internals ────────────────────────────────────────────────────
    def _apply(self, env, event: Mapping[str, Any]) -> bool:
        kind = event.get("type")
        if kind == "train_delay":
            return self._apply_train_delay(env, event)
        if kind == "area_block":
            return self._apply_area_block(env, event)
        # "warning" has no grid effect; it exists to be shown.
        return True

    def _apply_train_delay(self, env, event: Mapping[str, Any]) -> bool:
        handle = int(event["agent_handle"])
        agents = getattr(env, "agents", [])
        if handle < 0 or handle >= len(agents):
            return False
        handler = getattr(agents[handle], "malfunction_handler", None)
        if handler is None:
            return False
        # Flatland's own stopped-train mechanism, so every downstream consumer
        # (state machine, delay KPI, map badge) already understands it.
        handler.malfunction_down_counter = int(event["delay_steps"])
        return True

    def _apply_area_block(self, env, event: Mapping[str, Any]) -> bool:
        blocked = False
        for cell in event.get("cells", []):
            try:
                row, col = int(cell[0]), int(cell[1])
            except (TypeError, ValueError, IndexError):
                continue
            key = (row, col)
            if key not in self._saved_transitions:
                self._saved_transitions[key] = int(
                    env.rail.get_full_transitions(row, col)
                )
            env.rail.set_transitions(key, 0)
            blocked = True
        duration = int(event.get("duration") or 0)
        if blocked and duration > 0 and event.get("revert", True):
            self._active_blocks.append((dict(event), int(event["step"]) + duration))
        return blocked

    def _revert_block(self, env, event: Mapping[str, Any]) -> None:
        for cell in event.get("cells", []):
            try:
                key = (int(cell[0]), int(cell[1]))
            except (TypeError, ValueError, IndexError):
                continue
            saved = self._saved_transitions.pop(key, None)
            if saved is not None:
                env.rail.set_transitions(key, saved)


def notification_for(event: Mapping[str, Any]) -> Tuple[str, str, str, Optional[str]]:
    """`(kind, title, message, related_agent_id)` for the notification panel."""
    severity = str(event.get("severity") or "medium")
    kind = "error" if severity == "high" else "warning"
    title = str(event.get("label") or f"Disturbance: {event.get('type')}")
    message = str(event.get("description") or "")
    handle = event.get("agent_handle")
    return kind, title, message, None if handle is None else str(handle)


def apply_due_disturbances(session_id: str, session, env) -> List[Dict[str, Any]]:
    """Fire whatever is due at the env's current step; notify for each.

    Called from every place that advances a live session — the step endpoint
    and the play loop — so a scripted delay lands identically whether the user
    single-steps or presses Play. A fired event becomes a notification, which
    is how an emergent malfunction already announces itself.
    """
    from app.core.notification_manager import notification_manager

    scheduler = getattr(session, "disturbance_scheduler", None)
    if not scheduler:
        return []
    try:
        step = int(getattr(env, "_elapsed_steps", 0) or 0)
    except (TypeError, ValueError):
        return []

    fired = scheduler.tick(env, step)
    for event in fired:
        kind, title, message, related_id = notification_for(event)
        notification_manager.add(
            session_id,
            kind=kind,
            title=title,
            message=message,
            timestamp=step,
            # "train" is the only agent-shaped value `models.hmi.ElementKind`
            # allows; anything else fails validation in `generate_notifications`,
            # which drops the whole merged block, override alerts included.
            related_kind="train" if related_id is not None else None,
            related_id=related_id,
        )
    return fired


__all__ = [
    "DisturbanceError",
    "DisturbanceScheduler",
    "EVENT_TYPES",
    "apply_due_disturbances",
    "list_disturbances",
    "load_disturbance",
    "notification_for",
    "parse_disturbance",
]
