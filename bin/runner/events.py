"""The audit log (eyes) for the safety harness — runs + events in forge/runner.db.

Schema adapted from disler's observability layer: raw payload + hoisted, indexed
query columns. WAL mode for concurrent writers. All functions take an optional
db_path for testing against a tmp DB.
"""
from __future__ import annotations

import contextlib
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
-- PER-ITEM PROGRESS. `checkpoints` is keyed on step_index, so many items processed
-- INSIDE one step are all-or-nothing: item 37 failing discards items 1-36 and the
-- whole batch is redone next run. One row per ITEM makes progress durable at the
-- granularity work actually happens at. Keyed on (job, item_id), not item_id alone:
-- two jobs may legitimately process the same logical id.
CREATE TABLE IF NOT EXISTS work_item (
  job TEXT, item_id TEXT, batch_id TEXT,
  status TEXT,                      -- running | done | failed | quarantined
  attempts INTEGER DEFAULT 0,
  input_ref TEXT, result TEXT, error TEXT,
  prompt_sha TEXT, model TEXT, cli_version TEXT,
  updated_at INTEGER,
  PRIMARY KEY(job, item_id));
CREATE INDEX IF NOT EXISTS idx_work_item_job ON work_item(job, status);
"""

# The message arrived fine but the receiver cannot process it, so more attempts will
# not help: after this many consecutive failures an item is quarantined.
ITEM_QUARANTINE_ATTEMPTS = 3


def _conn(db_path=None) -> sqlite3.Connection:
    p = Path(db_path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p))
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=10000")   # concurrent writers: wait, don't fail instantly with SQLITE_BUSY
    c.executescript(_SCHEMA)
    # Migration: `status` distinguishes a step that STARTED from one that COMPLETED, so
    # a crash between "step ran" and "output persisted" is visible instead of silently
    # re-running the step on resume. Legacy rows are NULL and mean 'done' -- they were
    # only ever written after a successful step. Idempotent.
    try:
        c.execute("ALTER TABLE checkpoints ADD COLUMN status TEXT")
    except sqlite3.OperationalError:
        pass    # already migrated
    return c


@contextlib.contextmanager
def _tx(db_path=None):
    """A connection that COMMITS **and CLOSES**.

    `with sqlite3.connect(...) as c:` commits or rolls back but does NOT close the
    handle, so every log_event / save_checkpoint used to leak a connection and re-run
    the schema script. Every function in this module uses this wrapper.
    """
    c = _conn(db_path)
    try:
        with c:              # commit on success, rollback on exception
            yield c
    finally:
        c.close()


def _now() -> int:
    return int(time.time())


def start_run(job: str, db_path=None) -> str:
    run_id = uuid.uuid4().hex[:12]
    with _tx(db_path) as c:
        c.execute("INSERT INTO runs(run_id, job, status, started_at) VALUES (?,?,?,?)",
                  (run_id, job, "running", _now()))
    return run_id


def log_event(run_id: str, event_type: str, status: str = "ok", payload=None,
              cost: float = 0.0, needs_attention: bool = False, job: str = "",
              db_path=None) -> None:
    body = payload if isinstance(payload, str) or payload is None else json.dumps(payload, default=str)
    with _tx(db_path) as c:
        c.execute(
            "INSERT INTO events(run_id, job, event_type, status, payload, cost, ts, needs_attention)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (run_id, job, event_type, status, body, cost, _now(), int(needs_attention)))


def bump_run(run_id: str, actions: int = 0, cost: float = 0.0, db_path=None) -> None:
    with _tx(db_path) as c:
        c.execute("UPDATE runs SET action_count=action_count+?, cost=cost+? WHERE run_id=?",
                  (actions, cost, run_id))


def end_run(run_id: str, status: str, halt_reason=None, db_path=None) -> None:
    with _tx(db_path) as c:
        c.execute("UPDATE runs SET status=?, ended_at=?, halt_reason=? WHERE run_id=?",
                  (status, _now(), halt_reason, run_id))


def get_run(run_id: str, db_path=None) -> dict | None:
    with _tx(db_path) as c:
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None


def get_events(run_id: str, db_path=None) -> list[dict]:
    with _tx(db_path) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        return [dict(r) for r in rows]


def begin_step(run_id: str, step_index: int, db_path=None) -> None:
    """Mark a step STARTED *before* running it, closing the crash window.

    Without this, a crash between `out = step()` and `save_checkpoint(...)` was
    invisible: on resume the step had no checkpoint, so it silently RE-RAN — a wasted
    model call at best, a duplicate commit / file write / Slack post at worst. A
    'started' row with no output is detectable via load_incomplete(), so the caller
    can flag it instead of quietly repeating a side effect.
    """
    with _tx(db_path) as c:
        c.execute("INSERT OR IGNORE INTO checkpoints(run_id, step_index, output, ts, status) "
                  "VALUES (?,?,?,?,?)", (run_id, step_index, None, _now(), "started"))


def save_checkpoint(run_id: str, step_index: int, output, db_path=None) -> bool:
    """Persist a completed step's output so a resumed run can skip it.

    STRICT serialization. `json.dumps(output, default=str)` used to stringify anything
    non-JSON-native — an object came back as '<Obj ...>' — so a resumed run could hand
    a downstream step a string where the original was an object: silent type
    corruption on exactly the path you depend on after a crash.

    Now, if the output cannot be faithfully persisted, no fake checkpoint is written.
    The step stays un-checkpointed (status 'unserializable') and re-runs on resume —
    honest, because we cannot claim to skip a step whose result we failed to store.
    Returns True if checkpointed.
    """
    try:
        body = json.dumps(output)            # no default=str — fidelity or nothing
    except (TypeError, ValueError):
        # INSERT OR REPLACE, not UPDATE: a caller that skipped begin_step must still
        # leave a visible trace rather than nothing at all.
        with _tx(db_path) as c:
            c.execute("INSERT OR REPLACE INTO checkpoints(run_id, step_index, output, ts, status) "
                      "VALUES (?,?,?,?,?)", (run_id, step_index, None, _now(), "unserializable"))
        return False
    with _tx(db_path) as c:
        c.execute("INSERT OR REPLACE INTO checkpoints(run_id, step_index, output, ts, status) "
                  "VALUES (?,?,?,?,?)", (run_id, step_index, body, _now(), "done"))
    return True


def load_checkpoints(run_id: str, db_path=None) -> dict:
    """{step_index: output} for a run's COMPLETED steps only.

    Legacy rows predate the `status` column and are NULL — they only ever existed
    after a successful step, so NULL counts as done. 'started' / 'unserializable'
    rows are excluded, so an interrupted step is re-run rather than resumed with
    missing or corrupt output.
    """
    with _tx(db_path) as c:
        rows = c.execute("SELECT step_index, output FROM checkpoints WHERE run_id=? "
                         "AND (status IS NULL OR status='done')", (run_id,)).fetchall()
    out: dict = {}
    for idx, body in rows:
        try:
            out[idx] = json.loads(body)
        except (ValueError, TypeError):
            out[idx] = body
    return out


def load_incomplete(run_id: str, db_path=None) -> list[int]:
    """Step indexes that STARTED but never completed — the crash window actually fired.
    The caller should surface these (they may have half-applied a side effect) rather
    than silently re-running them."""
    with _tx(db_path) as c:
        rows = c.execute("SELECT step_index FROM checkpoints WHERE run_id=? "
                         "AND status IN ('started','unserializable') ORDER BY step_index",
                         (run_id,)).fetchall()
    return [r[0] for r in rows]


# --- per-item progress -------------------------------------------------------------
# Usage in a batch job:
#
#     for item in items:
#         if not events.should_process(job, item.id):
#             continue                      # already done in an earlier (killed) run
#         events.start_item(job, item.id, batch_id=bid, input_ref=item.path)
#         try:
#             result = do_work(item)
#         except Exception as exc:
#             events.fail_item(job, item.id, repr(exc)); continue
#         events.complete_item(job, item.id, result)
#
# Every state change commits immediately, so a kill at any point loses at most the
# item in flight — not the batch.

def should_process(job: str, item_id: str, db_path=None, batch_id: str | None = None) -> bool:
    """False if this item is already done or quarantined. The idempotency gate.

    `item_id` must be a LOGICAL work id (a session id, a file name) — never a prompt
    hash, which changes whenever the prompt is edited and would silently redo
    everything.

    RECURRING jobs pass `batch_id` (e.g. the ISO week). An item completed in an
    EARLIER batch becomes processable again, while its attempt count — and therefore
    quarantine — carries across batches. Folding the week into item_id instead makes
    every week a brand-new row whose attempts reset to 1, so a three-strike
    quarantine could never fire on a weekly job. Quarantine must outlive the cycle;
    "already done" must not.
    """
    with _tx(db_path) as c:
        row = c.execute("SELECT status, batch_id FROM work_item WHERE job=? AND item_id=?",
                        (job, item_id)).fetchone()
    if not row:
        return True
    status, row_batch = row[0], (row[1] or "")
    if status == "quarantined":
        return False
    if status == "done":
        return bool(batch_id) and row_batch != batch_id
    return True


def start_item(job: str, item_id: str, batch_id: str = "", input_ref: str = "",
               db_path=None) -> int:
    """Mark an item in-flight and increment its attempt count. Returns attempts so far."""
    with _tx(db_path) as c:
        c.execute(
            "INSERT INTO work_item(job, item_id, batch_id, status, attempts, input_ref, updated_at)"
            " VALUES (?,?,?,'running',1,?,?)"
            " ON CONFLICT(job, item_id) DO UPDATE SET"
            "   status='running', attempts=attempts+1, batch_id=excluded.batch_id,"
            "   input_ref=excluded.input_ref, updated_at=excluded.updated_at",
            (job, item_id, batch_id, input_ref, _now()))
        row = c.execute("SELECT attempts FROM work_item WHERE job=? AND item_id=?",
                        (job, item_id)).fetchone()
    return int(row[0]) if row else 1


def complete_item(job: str, item_id: str, result=None, db_path=None) -> None:
    try:
        body = json.dumps(result) if result is not None else None
    except (TypeError, ValueError):
        body = None      # same fidelity-or-nothing rule as save_checkpoint
    with _tx(db_path) as c:
        # attempts resets on success: for a recurring job, three failures spread over
        # a year are not the same signal as three in a row; only the latter quarantines.
        c.execute("UPDATE work_item SET status='done', result=?, error=NULL, attempts=0,"
                  " updated_at=? WHERE job=? AND item_id=?", (body, _now(), job, item_id))


def fail_item(job: str, item_id: str, error: str = "", *, permanent: bool = False,
              db_path=None) -> str:
    """Record a failed attempt. Quarantines at ITEM_QUARANTINE_ATTEMPTS (or at once if
    `permanent`). Returns the resulting status so the caller can log it.

    A quarantined item stops being retried, which is the whole point: a permanently
    broken item must never consume a per-run slot forever and starve the rest.
    """
    with _tx(db_path) as c:
        row = c.execute("SELECT attempts FROM work_item WHERE job=? AND item_id=?",
                        (job, item_id)).fetchone()
        attempts = int(row[0]) if row else 1
        status = "quarantined" if (permanent or attempts >= ITEM_QUARANTINE_ATTEMPTS) else "failed"
        c.execute("UPDATE work_item SET status=?, error=?, updated_at=?"
                  " WHERE job=? AND item_id=?",
                  (status, str(error)[:2000], _now(), job, item_id))
    return status


def item_counts(job: str | None = None, db_path=None) -> dict:
    """{status: count} — so a growing quarantine pile is visible, not silent."""
    q = "SELECT status, COUNT(*) FROM work_item"
    args: tuple = ()
    if job:
        q += " WHERE job=?"
        args = (job,)
    q += " GROUP BY status"
    with _tx(db_path) as c:
        return {row[0]: row[1] for row in c.execute(q, args).fetchall()}


def quarantined_items(job: str | None = None, limit: int = 20, db_path=None) -> list[dict]:
    q = ("SELECT job, item_id, attempts, error, updated_at FROM work_item "
         "WHERE status='quarantined'")
    args: list = []
    if job:
        q += " AND job=?"
        args.append(job)
    q += " ORDER BY updated_at DESC LIMIT ?"
    args.append(limit)
    with _tx(db_path) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(q, tuple(args)).fetchall()]


def fetch_since(since_ts: int, db_path=None) -> tuple[list[dict], list[dict]]:
    with _tx(db_path) as c:
        c.row_factory = sqlite3.Row
        runs = [dict(r) for r in c.execute(
            "SELECT * FROM runs WHERE started_at>=? ORDER BY started_at", (since_ts,)).fetchall()]
        events = [dict(r) for r in c.execute(
            "SELECT * FROM events WHERE ts>=? ORDER BY ts", (since_ts,)).fetchall()]
    return runs, events
