"""SQLite persistence for FairClick (stdlib sqlite3, no ORM).

Two separate databases are used:
  * fairclick.db  - FairClick's own records (users, tasks, sessions, evidence ...)
  * sim_sites.db  - data belonging to the *simulated* websites (their "backend")
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator

from .config import ensure_dirs, settings

_write_lock = threading.RLock()

APP_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key      TEXT NOT NULL,
    value    TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_type    TEXT NOT NULL,
    site_id      TEXT NOT NULL,
    inputs_json  TEXT NOT NULL,
    status       TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'user',
    created_at   TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id            TEXT PRIMARY KEY,
    task_id       TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    status        TEXT NOT NULL,
    status_detail TEXT,
    mode          TEXT NOT NULL,
    current_url   TEXT,
    current_step  INTEGER NOT NULL DEFAULT 0,
    live_screenshot TEXT,
    started_at    TEXT NOT NULL,
    ended_at      TEXT
);

CREATE TABLE IF NOT EXISTS agent_actions (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    step        INTEGER NOT NULL,
    agent       TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target      TEXT,
    detail      TEXT,
    page_url    TEXT,
    risk        TEXT,
    outcome     TEXT,
    timestamp   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS detections (
    id             TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    task_id        TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    site_id        TEXT NOT NULL,
    category       TEXT NOT NULL,
    pattern_name   TEXT NOT NULL,
    description    TEXT NOT NULL,
    evidence_text  TEXT NOT NULL,
    location       TEXT NOT NULL,
    severity       TEXT NOT NULL,
    confidence     REAL NOT NULL,
    recommendation TEXT NOT NULL,
    page_url       TEXT NOT NULL,
    page_path      TEXT NOT NULL,
    timestamp      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_records (
    id               TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    task_id          TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    site_id          TEXT NOT NULL,
    detection_id     TEXT REFERENCES detections(id) ON DELETE SET NULL,
    category         TEXT NOT NULL,
    description      TEXT NOT NULL,
    screenshot_path  TEXT,
    page_url         TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    confidence       REAL NOT NULL,
    supporting_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_requests (
    id               TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    action_summary   TEXT NOT NULL,
    reason           TEXT NOT NULL,
    data_json        TEXT NOT NULL,
    consequences     TEXT NOT NULL,
    target_label     TEXT NOT NULL,
    page_url         TEXT NOT NULL,
    screenshot_path  TEXT,
    status           TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_decisions (
    id          TEXT PRIMARY KEY,
    request_id  TEXT NOT NULL UNIQUE REFERENCES approval_requests(id) ON DELETE CASCADE,
    decision    TEXT NOT NULL,
    decided_by  TEXT NOT NULL,
    comment     TEXT,
    decided_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_results (
    id                 TEXT PRIMARY KEY,
    task_id            TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    session_id         TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    outcome            TEXT NOT NULL,
    success            INTEGER NOT NULL,
    summary            TEXT NOT NULL,
    reference          TEXT,
    prepared_document  TEXT,
    interactions       INTEGER NOT NULL,
    pages_visited      INTEGER NOT NULL,
    duration_seconds   REAL NOT NULL,
    patterns_detected  INTEGER NOT NULL,
    evidence_count     INTEGER NOT NULL,
    approvals_requested INTEGER NOT NULL,
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS security_incidents (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,
    description   TEXT NOT NULL,
    evidence_text TEXT NOT NULL,
    page_url      TEXT NOT NULL,
    action_taken  TEXT NOT NULL,
    timestamp     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_task ON agent_sessions(task_id);
CREATE INDEX IF NOT EXISTS idx_actions_session ON agent_actions(session_id);
CREATE INDEX IF NOT EXISTS idx_detections_session ON detections(session_id);
CREATE INDEX IF NOT EXISTS idx_evidence_session ON evidence_records(session_id);
CREATE INDEX IF NOT EXISTS idx_approvals_session ON approval_requests(session_id);
"""

SIM_SCHEMA = """
CREATE TABLE IF NOT EXISTS sim_submissions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    site         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    reference    TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
"""

DEFAULT_USER_ID = "demo-user"
DEFAULT_SETTINGS: dict[str, Any] = {
    "display_name": "Demo User",
    "require_approval_for_consent": True,
    "capture_screenshots": True,
    "headless_browser": True,
    "step_delay_ms": 250,
    "retain_history_days": 90,
    "store_page_text": True,
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def app_db() -> Iterator[sqlite3.Connection]:
    conn = _connect(settings.app_db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@contextmanager
def sim_db() -> Iterator[sqlite3.Connection]:
    conn = _connect(settings.sim_db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    ensure_dirs()
    with _write_lock:
        with app_db() as conn:
            conn.executescript(APP_SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")
            if not conn.execute("SELECT 1 FROM users WHERE id=?", (DEFAULT_USER_ID,)).fetchone():
                conn.execute(
                    "INSERT INTO users(id, display_name, created_at) VALUES (?,?,?)",
                    (DEFAULT_USER_ID, DEFAULT_SETTINGS["display_name"], utcnow()),
                )
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO user_settings(user_id, key, value) VALUES (?,?,?)",
                    (DEFAULT_USER_ID, key, json.dumps(value)),
                )
            # Sessions that were running when the server stopped cannot resume:
            # their browser is gone. Mark them as interrupted, never as approved.
            conn.execute(
                "UPDATE agent_sessions SET status='interrupted', status_detail='Server restarted while session was active', ended_at=? "
                "WHERE status IN ('running','awaiting_approval','starting')",
                (utcnow(),),
            )
            conn.execute(
                "UPDATE approval_requests SET status='expired' WHERE status='pending'"
            )
        with sim_db() as conn:
            conn.executescript(SIM_SCHEMA)


def execute(sql: str, params: Iterable[Any] = ()) -> None:
    with _write_lock:
        with app_db() as conn:
            conn.execute(sql, tuple(params))


def query(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with app_db() as conn:
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def insert(table: str, values: dict[str, Any]) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values.values())


def update(table: str, row_id: str, values: dict[str, Any]) -> None:
    assignments = ", ".join(f"{k}=?" for k in values)
    execute(f"UPDATE {table} SET {assignments} WHERE id=?", [*values.values(), row_id])
