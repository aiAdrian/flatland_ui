"""Tests for the event logger and SQLite persistence."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import event_logger as ev  # noqa: E402
from database import create_in_memory_db  # noqa: E402
from event_logger import EventLogger  # noqa: E402


def test_log_and_retrieve_events():
    db = create_in_memory_db()
    logger = EventLogger(db, "S-test")

    logger.log(ev.EVENT_SESSION_STARTED, ev.ACTOR_DIRECTOR_MODE, {"scenario_id": "easy"})
    logger.log(
        ev.EVENT_DECISION_COMMITTED,
        ev.ACTOR_HUMAN,
        {"selected_strategy": "minimize_delay"},
        simulation_step=1,
    )

    events = logger.events()
    assert len(events) == 2
    assert events[0]["event_type"] == ev.EVENT_SESSION_STARTED
    assert events[1]["payload"]["selected_strategy"] == "minimize_delay"
    assert events[1]["simulation_step"] == 1


def test_events_are_scoped_by_session():
    db = create_in_memory_db()
    a = EventLogger(db, "S-a")
    b = EventLogger(db, "S-b")
    a.log(ev.EVENT_SESSION_STARTED, ev.ACTOR_DIRECTOR_MODE)
    b.log(ev.EVENT_SESSION_STARTED, ev.ACTOR_DIRECTOR_MODE)
    b.log(ev.EVENT_SESSION_COMPLETED, ev.ACTOR_DIRECTOR_MODE)

    assert len(a.events()) == 1
    assert len(b.events()) == 2


def test_jsonl_export(tmp_path):
    db = create_in_memory_db()
    logger = EventLogger(db, "S-export")
    logger.log(ev.EVENT_SESSION_STARTED, ev.ACTOR_DIRECTOR_MODE, {"k": "v"})
    out = logger.export_jsonl(tmp_path / "events.jsonl")
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert '"k": "v"' in lines[0]
