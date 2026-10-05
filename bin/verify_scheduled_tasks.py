#!/usr/bin/env python3
"""verify_scheduled_tasks.py — reconcile the declared job REGISTRY against what the OS
scheduler actually has installed.

`bin/scheduler/jobs.py` is the single declared source of truth for the harness's
background jobs. A declaration that is never checked drifts: a job is added to the
registry and never installed, a task is installed by hand and never declared (so nothing
audits it), a trigger is edited in the OS scheduler and no longer matches. Keeping the two
in step by memory fails within weeks; checking it mechanically does not.

Checks (all name-based and cheap, any OS — see bin/scheduler/introspect.py):
  FAIL  DECLARED-NOT-INSTALLED   REGISTRY promises a job that is not installed
  FAIL  INSTALLED-NOT-DECLARED   an installed harness job nobody declared (unaudited)
  WARN  SCHEDULE-MISMATCH        installed time/day differs from REGISTRY
  WARN  DISABLED                 installed but switched off

Exit codes:
  0  installed jobs match the registry
  1  drift found
  2  cannot tell — the scheduler could not be read, or nothing is installed yet.
     Never reported as a pass.

Read-only: never edits the registry or the scheduler.

    python bin/verify_scheduled_tasks.py
    python bin/verify_scheduled_tasks.py --quiet     # only print drift
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scheduler import introspect as _intro  # noqa: E402
from scheduler import jobs as _jobs  # noqa: E402


def verify(registry=None, os_name: str | None = None, runner=None) -> tuple[str, list[str]]:
    """Return (verdict, lines). verdict is "pass" | "fail" | "unknown"."""
    registry = _jobs.REGISTRY if registry is None else registry
    installed, why = _intro.query(os_name, runner=runner)
    if installed is None:
        return "unknown", [f"UNKNOWN: the scheduler could not be read ({why}) — "
                           f"this is not a pass"]
    if not installed:
        return "unknown", [f"NOT CONFIGURED: no harness jobs are installed ({why}). "
                           f"Run `python bin/scheduler/install.py --apply` to install the "
                           f"{len(registry)} declared job(s)."]
    drift = _intro.reconcile(registry, installed)
    lines = [f"declared: {len(registry)} · installed: {len(installed)}"]
    if not drift:
        return "pass", lines + ["OK: installed jobs match bin/scheduler/jobs.py"]
    lines.append(f"{len(drift)} drift item(s):")
    lines += [f"  {sev:<4} {kind:<23} {jid} — {detail}" for sev, kind, jid, detail in drift]
    return ("fail" if any(s == "FAIL" for s, *_ in drift) else "pass"), lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check installed scheduled jobs against the registry.")
    ap.add_argument("--quiet", action="store_true", help="only print drift / problems")
    args = ap.parse_args(argv)
    verdict, lines = verify()
    for ln in lines:
        if args.quiet and verdict == "pass" and not ln.startswith("  "):
            continue
        print(ln)
    return {"pass": 0, "fail": 1}.get(verdict, 2)


if __name__ == "__main__":
    sys.exit(main())
