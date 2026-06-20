"""Durable approval queue: when policy says PAUSE, the action is parked to disk
(an `approvals` row in runner.db) and survives restarts. The operator resolves it
later via the CLI; a resumed run re-invokes the action. Additive table — no changes
to the runner's existing runs/events/checkpoints.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner import events  # noqa: E402  (shares runner.db + WAL + base schema)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT, created_at INTEGER,
  action_class TEXT, risk_level TEXT, blast_radius TEXT,
  summary TEXT, payload TEXT,
  status TEXT DEFAULT 'pending',
  resolved_at INTEGER, resolved_by TEXT);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
"""


def _conn(db_path=None):
    c = events._conn(db_path)   # ensures base schema + WAL on runner.db
    c.executescript(_SCHEMA)
    return c


def request(run_id: str, action_class: str, risk, summary: str,
            payload=None, db_path=None) -> int:
    body = json.dumps(payload, default=str) if payload is not None else None
    with _conn(db_path) as c:
        cur = c.execute(
            "INSERT INTO approvals(run_id, created_at, action_class, risk_level,"
            " blast_radius, summary, payload, status) VALUES (?,?,?,?,?,?,?, 'pending')",
            (run_id, int(time.time()), action_class, risk.level,
             risk.blast_radius, summary, body))
        return cur.lastrowid


def get(approval_id: int, db_path=None) -> dict | None:
    import sqlite3
    with _conn(db_path) as c:
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        return dict(r) if r else None


def pending(db_path=None) -> list[dict]:
    import sqlite3
    with _conn(db_path) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM approvals WHERE status='pending' ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def resolve(approval_id: int, approved: bool, by: str = "operator", db_path=None) -> bool:
    status = "approved" if approved else "rejected"
    with _conn(db_path) as c:
        cur = c.execute(
            "UPDATE approvals SET status=?, resolved_at=?, resolved_by=? "
            "WHERE id=? AND status='pending'",
            (status, int(time.time()), by, approval_id))
        return cur.rowcount > 0
