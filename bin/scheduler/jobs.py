"""Declarative registry of the harness's scheduled background jobs.

One source of truth; the per-OS backends (backends.py) turn each Job into a
cron line / launchd plist / schtasks command. Jobs are invoked repo-relative
(no hardcoded author paths), so they work in any clone on any OS.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Job:
    id: str
    args: list[str]          # argv relative to repo root, e.g. ["bin/security_watch.py"]
    cadence: str             # "daily" | "weekly"
    time: str                # "HH:MM" 24h local
    dow: str | None = None   # weekly only: MON..SUN
    safe_rerun: bool = False # self_loop may re-run this on failure: ONLY for cheap +
                             # idempotent jobs (no claude calls, no external writes)


def repo_root() -> Path:
    """Repo root = two levels up from bin/scheduler/."""
    return Path(__file__).resolve().parents[2]


# Your scheduled jobs. EMPTY by default so `install.py --apply` never installs a
# broken job in a fresh clone. Add your own — each `args` is repo-relative and
# the per-OS backends do the rest. Example:
#
#   REGISTRY = [
#       Job("weekly-planner", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN"),
#       Job("security-watch", ["bin/security_watch.py"], "daily",  "08:00"),
#   ]
#
# Both bundled jobs above are generic + cross-platform and safe to add.
# See bin/scheduler/README.md.
#
# Only jobs whose scripts exist in this repo are wired (a Job pointing at a missing
# script would install a broken scheduled task). All four below are generic and
# present. (A CLONE-style content "daily brief" is intentionally NOT here — that's
# instance-specific; daily-digest covers the generic "what ran autonomously" report.)
REGISTRY: list[Job] = [
    Job("weekly-planner", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN"),  # claude -p → not safe_rerun
    Job("security-watch", ["bin/security_watch.py"], "daily", "08:00", safe_rerun=True),
    Job("brain-embed", ["claude-brain/scripts/batch_embed.py"], "daily", "05:00", safe_rerun=True),
    # self-test runs BEFORE daily-digest so every digest carries a fresh verdict.
    Job("self-test", ["bin/self_test.py"], "daily", "05:30", safe_rerun=True),
    Job("daily-digest", ["bin/runner/digest.py"], "daily", "07:00", safe_rerun=True),
    # self-loop audits + heals the rest of this registry (see bin/self_loop.py).
    Job("self-loop", ["bin/self_loop.py"], "daily", "06:30"),
    # OPT-IN (commented by design — grants an unattended agent WRITE access):
    # Test-Medic repairs a red self-test via headless `claude -p` under a strict
    # contract (no VCS mutation, deterministic re-verify, escalates judgment
    # calls). Read the "Test-Medic trust model" section in README.md, then
    # uncomment to enable:
    #   Job("test-medic", ["bin/test_medic.py"], "weekly", "14:00", dow="MON"),
]
