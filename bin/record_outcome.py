#!/usr/bin/env python3
"""record_outcome.py — CLI so a job that is NOT Python (a shell script, a cron one-liner,
a PowerShell task) can still report what it did.

For a job with no outcome sidecar, "exit 0" is the only evidence any work happened, and
exit 0 is exactly what a job prints when its login silently died. Python jobs call
harness_common.record_outcome() directly; everything else calls this at the END of the
job, on every path:

    python bin/record_outcome.py brain-embed --status ok --produced 412
    python bin/record_outcome.py brain-embed --status error --detail "embedding server down"

The job name MUST be the scheduler job id from bin/scheduler/jobs.py — self_loop looks the
sidecar up by that id. Status vocabulary (anything else would read as healthy):
ok | empty | transient | auth_failed | rate_limited | error. `empty` = ran correctly and
there was legitimately nothing to do.

Always exits 0: a reporting failure must never turn a successful job into a failed one.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_common import OUTCOME_STATUSES  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write a scheduled job's outcome sidecar.")
    ap.add_argument("job", help="scheduler job id, e.g. brain-embed (see bin/scheduler/jobs.py)")
    ap.add_argument("--status", default="ok", choices=OUTCOME_STATUSES)
    ap.add_argument("--produced", default=None,
                    help="count of things this run actually made. status=ok with produced=0 "
                         "is the shape of a silent failure, so pass it.")
    ap.add_argument("--detail", default="", help="short human detail (truncated to 200 chars)")
    args = ap.parse_args(argv)

    produced = args.produced
    if produced is not None:
        try:
            produced = int(produced)
        except (TypeError, ValueError):
            pass            # keep the raw string rather than dropping the signal
    try:
        from harness_common import record_outcome  # noqa: PLC0415
        record_outcome(args.job, status=args.status, produced=produced, detail=args.detail)
        print(f"[record-outcome] {args.job}: status={args.status} produced={produced!r}")
    except Exception as exc:  # noqa: BLE001 — never fail the caller
        print(f"[record-outcome] WARNING could not record {args.job}: {exc!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
