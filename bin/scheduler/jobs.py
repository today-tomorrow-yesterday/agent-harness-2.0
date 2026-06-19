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
    args: list[str]          # argv relative to repo root, e.g. ["bin/daily-brief.py"]
    cadence: str             # "daily" | "weekly"
    time: str                # "HH:MM" 24h local
    dow: str | None = None   # weekly only: MON..SUN


def repo_root() -> Path:
    """Repo root = two levels up from bin/scheduler/."""
    return Path(__file__).resolve().parents[2]


# The harness's background agents. Add jobs here; the backends handle the rest.
REGISTRY: list[Job] = [
    Job("daily-brief",    ["bin/daily-brief.py"],    "daily",  "07:00"),
    Job("weekly-planner", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN"),
]
