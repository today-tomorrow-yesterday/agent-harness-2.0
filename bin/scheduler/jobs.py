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


# The scheduled jobs. Every entry here is generic, cross-platform, and points at a script
# that exists in this repo (bin/tests/test_fleet_integrity.py fails the suite otherwise —
# a Job pointing at a missing script would install a broken scheduled task). Nothing is
# installed until you run `install.py --apply`. Add your own — each `args` is repo-
# relative and the per-OS backends do the rest. See bin/scheduler/README.md.
#
# Jobs that spend your subscription (`claude -p`), write to your repo unattended, or delete
# files are listed COMMENTED OUT at the bottom: each is opt-in, with the reason given.
#
# (An instance-specific content "daily brief" is intentionally NOT here; daily-digest
# covers the generic "what ran autonomously" report.)
REGISTRY: list[Job] = [
    Job("weekly-planner", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN"),  # claude -p → not safe_rerun
    Job("security-watch", ["bin/security_watch.py"], "daily", "08:00", safe_rerun=True),
    Job("brain-embed", ["claude-brain/scripts/batch_embed.py"], "daily", "05:00", safe_rerun=True),
    # self-test runs BEFORE daily-digest so every digest carries a fresh verdict.
    Job("self-test", ["bin/self_test.py"], "daily", "05:30", safe_rerun=True),
    Job("daily-digest", ["bin/runner/digest.py"], "daily", "07:00", safe_rerun=True),
    # structural drift (registry vs installed, hooks, skills, secrets, ...). Read-only;
    # reports through its outcome + alerts and exits 0, so a re-run is cheap and harmless.
    Job("conformance-check", ["bin/conformance_check.py"], "daily", "06:00", safe_rerun=True),
    # self-loop audits + heals the rest of this registry (see bin/self_loop.py).
    Job("self-loop", ["bin/self_loop.py"], "daily", "06:30"),
    # read-only status view; also the dead-man's switch that watches self-loop's heartbeat.
    Job("fleet-status", ["bin/fleet_status.py"], "daily", "07:15", safe_rerun=True),
    # OPT-IN (commented by design — grants an unattended agent WRITE access):
    # Test-Medic repairs a red self-test via headless `claude -p` under a strict
    # contract (no VCS mutation, deterministic re-verify, escalates judgment
    # calls). Read the "Test-Medic trust model" section in README.md, then
    # uncomment to enable:
    #   Job("test-medic", ["bin/test_medic.py"], "weekly", "14:00", dow="MON"),
    #
    # OPT-IN — spends ONE `claude -p` call per week on your subscription to notice model /
    # CLI behaviour drift (bin/golden_run.py, cases in forge/golden/):
    #   Job("golden-run", ["bin/golden_run.py"], "weekly", "10:00", dow="SAT"),
    # OPT-IN — one tiny `claude -p` call to prove the subscription login works from an
    # unattended session (bin/auth_canary.py). Worth running once after install:
    #   Job("auth-canary", ["bin/auth_canary.py"], "weekly", "10:30", dow="SAT"),
    # OPT-IN — DELETES files older than 14 days from <repo>/tmp (or $HARNESS_TMP_DIR).
    # Only enable once you treat that directory as disposable (bin/tmp_purge.py):
    #   Job("tmp-purge", ["bin/tmp_purge.py"], "daily", "04:30", safe_rerun=True),
]
