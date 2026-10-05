#!/usr/bin/env python3
"""
distill_pending.py - Find sessions lacking real notes and distill them.

Phase 3 (2026-05-27): scheduled distill entry point. Picks the oldest N sessions
whose notes are NULL / empty / start with the "AUTO-GENERATED FALLBACK"
sentinel and runs distill_session on each, with a small inter-session sleep
to be friendly to the Claude subscription rate limit.

Usage:
    python3 scripts/distill_pending.py [--limit N] [--newest-first] [--dry-run]

Defaults: --limit 5  (deliberately small; raise it for backfill runs).
"""

import argparse
import datetime
import json
import os
import pathlib
import sqlite3
import sys
import time

import yaml

ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from distill_session import distill_session, setup_logging  # noqa: E402


def load_config():
    config_path = os.path.join(ROOT, "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def connect_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    return conn


# Sessions count as "pending" if notes are NULL, empty, or the fallback sentinel.
# The fallback prefix is written by hooks/session-end.py when no real notes exist.
PENDING_WHERE = """
    notes IS NULL OR notes = ''
    OR notes LIKE 'AUTO-GENERATED FALLBACK%'
    OR notes LIKE '%AUTO-GENERATED FALLBACK%'
"""


def find_pending(conn, limit, newest_first=False, min_messages=3):
    """Return session_ids that need distillation.

    Skips very short sessions (< min_messages) — usually not worth the round trip.
    """
    order = "DESC" if newest_first else "ASC"
    rows = conn.execute(f"""
        SELECT session_id, project, started_at, ended_at, message_count
        FROM sys_sessions
        WHERE ({PENDING_WHERE})
          AND message_count >= ?
        ORDER BY started_at {order}
        LIMIT ?
    """, (min_messages, limit)).fetchall()
    return rows


def main():
    parser = argparse.ArgumentParser(description="Distill pending sessions (no notes / fallback notes)")
    parser.add_argument("--limit", type=int, default=5,
                        help="Max sessions to distill this run (default 5). Raise for backfill.")
    parser.add_argument("--newest-first", action="store_true",
                        help="Distill most-recent pending sessions first (default: oldest first)")
    parser.add_argument("--min-messages", type=int, default=3,
                        help="Skip sessions with fewer than this many messages (default 3)")
    parser.add_argument("--sleep", type=int, default=5,
                        help="Seconds to sleep between sessions (default 5; protects rate limit)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be distilled but don't call claude")
    parser.add_argument("--model", default=None,
                        help="Override claude CLI model (default: user's session model)")
    args = parser.parse_args()

    config = load_config()
    db_path = config["storage"]["local_db_path"]
    logger = setup_logging()

    conn = connect_db(db_path)
    try:
        pending = find_pending(conn, args.limit, args.newest_first, args.min_messages)
    finally:
        conn.close()

    if not pending:
        print("No pending sessions. Brain is fully distilled.")
        return 0

    print(f"Pending: {len(pending)} session(s) selected.")
    for r in pending:
        print(f"  {r['session_id'][:12]}... project={r['project']} msgs={r['message_count']} started={r['started_at']}")

    if args.dry_run:
        return 0

    results = []
    for i, r in enumerate(pending, 1):
        sid = r["session_id"]
        print(f"\n[{i}/{len(pending)}] distilling {sid[:12]}... (msgs={r['message_count']})")
        try:
            result = distill_session(sid, dry_run=False, model=args.model)
            print(f"  -> {json.dumps(result)}")
            results.append({"session_id": sid, **result})
        except Exception as e:
            logger.error("Distill failed for %s: %s", sid, e)
            print(f"  ERROR: {e}")
            results.append({"session_id": sid, "status": "error", "error": str(e)})

        if i < len(pending):
            time.sleep(args.sleep)

    # Summary
    ok = sum(1 for r in results if r.get("status") == "ok")
    err = sum(1 for r in results if r.get("status") == "error")
    skipped = sum(1 for r in results if r.get("status") in ("skipped_active", "empty"))
    print(f"\nSummary: {ok} distilled, {err} errors, {skipped} skipped, "
          f"{len(results) - ok - err - skipped} other.")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
