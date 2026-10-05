#!/usr/bin/env python3
"""Idea Cultivation Loop — Slack nudge.

Posts the seeds due for watering to Slack (digest route — routine traffic, not an
alert). Reuses notify_slack, the secret-scrubbing egress chokepoint. Schedule it
through bin/scheduler if you want it between weekly briefings; the weekly planner
surfaces due seeds on its own either way.

No-ops cleanly when no seeds are due. When Slack is NOT configured it also does NOT
mark the seeds surfaced, so they stay due until a channel exists (or until the
weekly briefing shows them).

    python bin/seed-nudge.py            # post due seeds
    python bin/seed-nudge.py --dry-run  # print what would be posted; change nothing
"""
from __future__ import annotations

import argparse
import datetime
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from goal_loop import seeds          # noqa: E402


def main(argv=None, *, now_ts=None, path=None, post=None) -> int:
    ap = argparse.ArgumentParser(prog="seed-nudge")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the review that would be posted; post nothing, mark nothing.")
    args = ap.parse_args(argv)

    now = int(now_ts if now_ts is not None else time.time())
    due = seeds.due_for_review(now, seeds.DEFAULT_CADENCE_DAYS, path=path)
    if not due:
        print("seed-nudge: no seeds due")
        return 0
    today = datetime.datetime.fromtimestamp(now).date().isoformat()
    md = seeds.render_review(due, today=today)
    if args.dry_run:
        print(md)
        print(f"seed-nudge: dry-run — {len(due)} seed(s) due; nothing posted or marked")
        return 0
    if post is None:
        from notify_slack import post_slack as post
    res = post(md, title="Seed Review — water / refine / let go", route="digest")
    if res is None:
        print(f"seed-nudge: {len(due)} due, but Slack not configured (no-op); not marking surfaced")
        return 2
    if res:
        seeds.mark_surfaced([s["id"] for s in due], now, path=path)
    print(f"seed-nudge: posted {len(due)} seed(s) to Slack (sent={res})")
    return 0 if res else 1


if __name__ == "__main__":
    raise SystemExit(main())
