"""Smoke tests: no shipped hook may EVER crash on malformed stdin.

Hooks run on every Claude Code lifecycle event; a hook that exits nonzero with a
traceback on a weird payload degrades every session. The crash class is real:
`json.loads("null" / "42" / "[]")` returns a non-dict, and a later `.get()`
raises AttributeError (found live in two agent-os hooks, 2026-07-01/02).

Drives each hook exactly as the harness does — subprocess, payload on stdin —
and asserts exit 0 with no traceback. CLAUDE_BRAIN_SKIP_HOOKS is force-unset so
the kill-switch can't make these tests vacuously green.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[2] / "claude-brain" / "hooks"
HOOKS = sorted(p.name for p in HOOKS_DIR.glob("*.py"))

BAD_PAYLOADS = [
    "null", "42", "[]", '"a string"', "true",   # valid JSON, not an object
    "not json at all", "{ broken", "", "   ",     # unparseable / blank
    '{"user_prompt": 12345}',                     # object with wrong value type
]


def run_hook(name: str, stdin_text: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_BRAIN_SKIP_HOOKS="0")
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / name)],
        input=stdin_text, capture_output=True, text=True, timeout=120, env=env,
    )


def test_hooks_are_shipped():
    assert len(HOOKS) >= 6, f"expected the 6 lifecycle hooks, found {HOOKS}"


@pytest.mark.parametrize("hook", HOOKS)
@pytest.mark.parametrize("payload", BAD_PAYLOADS)
def test_hook_never_crashes_on_malformed_stdin(hook, payload):
    r = run_hook(hook, payload)
    assert r.returncode == 0, (
        f"{hook} crashed on {payload!r} (exit {r.returncode}):\n{r.stderr[:600]}"
    )
    assert "Traceback" not in r.stderr, (
        f"{hook} printed a traceback on {payload!r}:\n{r.stderr[:600]}"
    )
