"""SQLite persistence layer for the Director Mode Reflection Playground.

A single connection is created per process. Tables are created lazily on first
use. All higher-level modules (event logger, decision episode builder, learning
store) go through the ``Database`` helper defined here.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "reflection.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    started_at   TEXT,
    ended_at     TEXT,
    scenario_id  TEXT,
    difficulty   TEXT,
    seed         INTEGER,
    status       TEXT,
    profile_id   TEXT
);

CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    session_id      TEXT,
    timestamp       TEXT,
    simulation_step INTEGER,
    actor           TEXT,
    event_type      TEXT,
    payload_json    TEXT
);

CREATE TABLE IF NOT EXISTS decision_episodes (
    decision_id         TEXT PRIMARY KEY,
    session_id          TEXT,
    simulation_step     INTEGER,
    context_json        TEXT,
    recommendation_json TEXT,
    user_decision_json  TEXT,
    outcome_json        TEXT,
    pattern_json        TEXT,
    reflection_score    REAL
);

CREATE TABLE IF NOT EXISTS learnings (
    learning_id     TEXT PRIMARY KEY,
    session_id      TEXT,
    statement       TEXT,
    conditions_json TEXT,
    boundaries_json TEXT,
    confidence      TEXT,
    status          TEXT,
    evidence_json   TEXT,
    created_at      TEXT,
    updated_at      TEXT
);
"""


class Database:
    """Thin wrapper around a sqlite3 connection with a shared lock."""

    def __init__(self, db_path: str | os.PathLike | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            # lightweight migration for older DBs missing profile_id
            try:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN profile_id TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
            self._conn.commit()

    # -- generic helpers --------------------------------------------------- #
    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def create_in_memory_db() -> Database:
    """Convenience constructor used by the test-suite."""
    db = Database.__new__(Database)
    db.db_path = Path(":memory:")
    db._lock = threading.Lock()
    db._conn = sqlite3.connect(":memory:", check_same_thread=False)
    db._conn.row_factory = sqlite3.Row
    db._init_schema()
    return db
