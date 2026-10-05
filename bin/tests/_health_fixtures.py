"""Shared fixtures for the health-program tests (not collected: no test_ prefix).

`hc_env` redirects every harness_common state path to a tmp dir, pins the clock to a
fixed instant (no test may depend on today's date), clears dry-run, and captures Slack
posts instead of sending them.
"""
from __future__ import annotations

import calendar
import time

import pytest

import harness_common as hc

# 2030-01-15T12:00:00Z — an arbitrary fixed instant.
PINNED = float(calendar.timegm(time.strptime("2030-01-15T12:00:00Z", "%Y-%m-%dT%H:%M:%SZ")))


def iso(offset_h: float = 0.0) -> str:
    """UTC '...Z' timestamp `offset_h` hours relative to PINNED (negative = past)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(PINNED + offset_h * 3600))


class Env:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.posts: list[tuple[str, str]] = []
        self.now = PINNED

    def advance(self, hours: float) -> None:
        self.now += hours * 3600


@pytest.fixture
def hc_env(tmp_path, monkeypatch):
    env = Env(tmp_path)
    forge = tmp_path / "forge"
    monkeypatch.setattr(hc, "FORGE", forge)
    monkeypatch.setattr(hc, "STOP_FILE", forge / "STOP")
    monkeypatch.setattr(hc, "ALERTS_LOG", forge / "alerts.log")
    monkeypatch.setattr(hc, "ALERT_STATE", forge / "alert-state.json")
    monkeypatch.setattr(hc, "OUTCOMES_DIR", forge / "outcomes")
    monkeypatch.setattr(hc, "LOCK_DIR", forge / "locks")
    monkeypatch.setattr(hc, "_clock", lambda: env.now)
    monkeypatch.setattr(hc, "_post", lambda text, title: env.posts.append((title, text)))
    hc.set_dry_run(False)
    yield env
    hc.set_dry_run(False)
