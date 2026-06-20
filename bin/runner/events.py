"""The audit log (eyes) for the safety harness — runs + events in forge/runner.db.

Schema adapted from disler's observability layer: raw payload + hoisted, indexed
query columns. WAL mode for concurrent writers. All functions take an optional
db_path for testing against a tmp DB.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "forge" / "runner.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, job TEXT, status TEXT,
  started_at INTEGER, ended_at INTEGER,
  action_count INTEGER DEFAULT 0, cost REAL DEFAULT 0, halt_reason TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, job TEXT,
  event_type TEXT, status TEXT, payload TEXT, cost REAL DEFAULT 0,
  ts INTEGER, needs_attention INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS checkpoints (
  run_id TEXT, step_index INTEGER, output TEXT, ts INTEGER,
  PRIMARY KEY(run_id, step_index));
"""


def _conn(db_path=None) -> sqlite3.Connection:
    p = Path(db_path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p))
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(_SCHEMA)
    return c


def _now() -> int:
    return int(time.time())


def start_run(job: str, db_path=None) -> str:
    run_id = uuid.uuid4().hex[:12]
    with _conn(db_path) as c:
        c.execute("INSERT INTO runs(run_id, job, status, started_at) VALUES (?,?,?,?)",
                  (run_id, job, "running", _now()))
    return run_id


def log_event(run_id: str, event_type: str, status: str = "ok", payload=None,
              cost: float = 0.0, needs_attention: bool = False, job: str = "",
              db_path=None) -> None:
    body = payload if isinstance(payload, str) or payload is None else json.dumps(payload, default=str)
    with _conn(db_path) as c:
        c.execute(
            "INSERT INTO events(run_id, job, event_type, status, payload, cost, ts, needs_attention)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (run_id, job, event_type, status, body, cost, _now(), int(needs_attention)))


def bump_run(run_id: str, actions: int = 0, cost: float = 0.0, db_path=None) -> None:
    with _conn(db_path) as c:
        c.execute("UPDATE runs SET action_count=action_count+?, cost=cost+? WHERE run_id=?",
                  (actions, cost, run_id))


def end_run(run_id: str, status: str, halt_reason=None, db_path=None) -> None:
    with _conn(db_path) as c:
        c.execute("UPDATE runs SET status=?, ended_at=?, halt_reason=? WHERE run_id=?",
                  (status, _now(), halt_reason, run_id))


def get_run(run_id: str, db_path=None) -> dict | None:
    with _conn(db_path) as c:
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None


def get_events(run_id: str, db_path=None) -> list[dict]:
    with _conn(db_path) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        return [dict(r) for r in rows]


def save_checkpoint(run_id: str, step_index: int, output, db_path=None) -> None:
    """Persist a completed step's output so a resumed run can skip it."""
    body = json.dumps(output, default=str)
    with _conn(db_path) as c:
        c.execute("INSERT OR REPLACE INTO checkpoints(run_id, step_index, output, ts) "
                  "VALUES (?,?,?,?)", (run_id, step_index, body, _now()))


def load_checkpoints(run_id: str, db_path=None) -> dict:
    """{step_index: output} for a run's completed steps."""
    with _conn(db_path) as c:
        rows = c.execute("SELECT step_index, output FROM checkpoints WHERE run_id=?",
                         (run_id,)).fetchall()
    out: dict = {}
    for idx, body in rows:
        try:
            out[idx] = json.loads(body)
        except (ValueError, TypeError):
            out[idx] = body
    return out


def fetch_since(since_ts: int, db_path=None) -> tuple[list[dict], list[dict]]:
    with _conn(db_path) as c:
        c.row_factory = sqlite3.Row
        runs = [dict(r) for r in c.execute(
            "SELECT * FROM runs WHERE started_at>=? ORDER BY started_at", (since_ts,)).fetchall()]
        events = [dict(r) for r in c.execute(
            "SELECT * FROM events WHERE ts>=? ORDER BY ts", (since_ts,)).fetchall()]
    return runs, events
