"""Durable approval queue: when policy says PAUSE, the action is parked to disk
(an `approvals` row in runner.db) and survives restarts. The operator resolves it
later via the CLI. Approving does not run anything by itself: the job that parked the
action calls execute() again with approved_id=<row id>, the action runs once, and
the row moves approved -> executed. Additive table — no changes to the runner's
existing runs/events/checkpoints.

Secrets are scrubbed from the summary and payload BEFORE they are stored (a URL or
argument can carry `?api_key=...`), so every lookup by summary compares the
scrubbed form against the scrubbed row. Scrubbing alone would widen an approval:
two actions that differ only inside a secret scrub to the same text. So each row
also stores `action_digest`, a SHA-256 of the RAW summary, and an approval covers
only the action whose raw summary hashes to it (see matches()).

status: pending -> approved | rejected;  approved -> executed (spent).
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner import events  # noqa: E402  (shares runner.db + WAL + base schema)
from execution import redaction  # noqa: E402  (scrub secrets before they hit the DB)

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
    # Migration: rows written before this column existed have NULL (see matches()).
    try:
        c.execute("ALTER TABLE approvals ADD COLUMN action_digest TEXT")
    except Exception:  # noqa: BLE001 — sqlite3.OperationalError: already migrated
        pass
    return c


def action_digest(summary: str) -> str:
    """Identity of the exact action behind a (possibly scrubbed) summary."""
    return hashlib.sha256((summary or "").encode("utf-8")).hexdigest()


def matches(row: dict, summary: str, action_class: str) -> bool:
    """Does this approval row cover the action with this RAW summary and class?

    The scrubbed summary must equal the stored one (what the operator read), and the
    raw summary must hash to the stored digest (the exact action, secret included).
    A legacy row without a digest stored its summary unscrubbed, so the scrubbed
    comparison only matches it when the summary never contained a secret — the same
    actions the earlier exact comparison matched, and no others.
    """
    if not row or row.get("action_class") != action_class:
        return False
    if row.get("summary") != redaction.scrub(summary):
        return False
    stored = row.get("action_digest")
    return stored is None or stored == action_digest(summary)


@contextlib.contextmanager
def _tx(db_path=None):
    """A connection that COMMITS **and CLOSES** — the approval-queue twin of events._tx.

    `with _conn(...) as c:` commits or rolls back but does NOT close the handle, so
    every request/get/pending/resolve used to leak a connection (and re-run the schema
    script). A long-lived process that parks approvals in a loop — the weekly goal-loop
    batch — accumulated one open handle per call.
    """
    c = _conn(db_path)
    try:
        with c:              # commit on success, rollback on exception
            yield c
    finally:
        c.close()


def request(run_id: str, action_class: str, risk, summary: str,
            payload=None, db_path=None) -> int:
    body = json.dumps(payload, default=str) if payload is not None else None
    digest = action_digest(summary)
    # Scrub secrets (e.g. ?api_key=sk-... in a URL or argument) before they persist.
    summary = redaction.scrub(summary)
    if body:
        body = redaction.scrub(body)
    with _tx(db_path) as c:
        cur = c.execute(
            "INSERT INTO approvals(run_id, created_at, action_class, risk_level,"
            " blast_radius, summary, payload, status, action_digest)"
            " VALUES (?,?,?,?,?,?,?, 'pending', ?)",
            (run_id, int(time.time()), action_class, risk.level,
             risk.blast_radius, summary, body, digest))
        return cur.lastrowid


def get(approval_id: int, db_path=None) -> dict | None:
    import sqlite3
    with _tx(db_path) as c:
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        return dict(r) if r else None


def pending(db_path=None) -> list[dict]:
    import sqlite3
    with _tx(db_path) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM approvals WHERE status='pending' ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def latest_for(summary: str, action_class: str, db_path=None) -> dict | None:
    """The most recent approval row for this exact action, any status.

    `summary` is the identity of a parked action: it is what the operator read when
    deciding, so an approval covers the action with that summary and no other.
    Compared post-scrub, because request() scrubs the summary before storing it.
    """
    import sqlite3
    with _tx(db_path) as c:
        c.row_factory = sqlite3.Row
        r = c.execute(
            "SELECT * FROM approvals WHERE summary=? AND action_class=?"
            " AND (action_digest IS NULL OR action_digest=?) ORDER BY id DESC LIMIT 1",
            (redaction.scrub(summary), action_class, action_digest(summary))).fetchone()
        return dict(r) if r else None


def consume(approval_id: int, db_path=None) -> bool:
    """Spend an approval: approved -> executed. True only for the caller that made
    the transition, so one approval authorizes exactly one run even if two jobs race."""
    with _tx(db_path) as c:
        cur = c.execute(
            "UPDATE approvals SET status='executed' WHERE id=? AND status='approved'",
            (approval_id,))
        return cur.rowcount > 0


def resolve(approval_id: int, approved: bool, by: str = "operator", db_path=None) -> bool:
    status = "approved" if approved else "rejected"
    with _tx(db_path) as c:
        cur = c.execute(
            "UPDATE approvals SET status=?, resolved_at=?, resolved_by=? "
            "WHERE id=? AND status='pending'",
            (status, int(time.time()), by, approval_id))
        return cur.rowcount > 0
