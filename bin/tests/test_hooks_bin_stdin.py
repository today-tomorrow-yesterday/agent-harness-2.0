"""Smoke tests: no hook in bin/hooks/ may EVER crash on malformed stdin.

The sibling suite test_hooks_stdin.py covers claude-brain/hooks; this one covers bin/hooks with
the same contract. Hooks run on every matching tool call -- a hook that exits nonzero with a
traceback on a weird payload degrades every session. The crash class is real:
`json.loads("null" / "42" / "[]")` returns a non-dict, and a later `.get()` raises.

Each hook runs with the "most active" environment (unattended mode on, gates configured), so the
cases reach the code paths that would actually crash. State is isolated to a temp directory.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"
HOOKS = sorted(p.name for p in HOOKS_DIR.glob("*-*.py"))

BAD_PAYLOADS = [
    "null", "42", "[]", '"a string"', "true",              # valid JSON, not an object
    "not json at all", "{ broken", "", "   ",              # unparseable / blank
    "{}",
    '{"tool_input": "not a dict"}',
    '{"tool_name": "Bash", "tool_input": {"command": 12345}}',
    '{"tool_name": "Bash", "tool_input": {"command": null}}',
    '{"tool_name": "Write", "tool_input": {"file_path": ["x"], "content": 3}}',
    '{"tool_name": "MultiEdit", "tool_input": {"edits": "nope"}}',
    '{"tool_name": "Skill", "tool_input": {"skill": {"a": 1}}}',
    '{"hook_event_name": "Stop", "session_id": 7}',
    '{"hook_event_name": "UserPromptSubmit", "prompt": 12345}',
    '{"hook_event_name": "UserPromptSubmit", "prompt": ""}',
]


def test_hooks_are_shipped():
    assert {"pre-tool-guard.py", "safety-queue.py", "design-gate.py", "capability-gate.py",
            "placement-guard.py", "skill-shape-guard.py"} <= set(HOOKS)


@pytest.mark.parametrize("hook", HOOKS)
@pytest.mark.parametrize("payload", BAD_PAYLOADS)
def test_hook_never_crashes_on_malformed_stdin(hook, payload, tmp_path):
    env = dict(os.environ,
               HARNESS_UNATTENDED="1",
               HARNESS_SAFETY_NOTIFY="off",
               HARNESS_SAFETY_DIR=str(tmp_path / "safety"),
               HARNESS_HOOK_STATE_DIR=str(tmp_path / "state"),
               CLAUDE_SETTINGS_PATH=str(tmp_path / "settings.json"),
               DESIGN_GATE_BUILD_SKILLS="ui-builder",
               DESIGN_GATE_REVIEW_SKILLS="look-check")
    for k in ("HARNESS_HOOKS_DISABLED", "CLAUDE_BRAIN_SKIP_HOOKS", "DESIGN_GATE",
              "CAPABILITY_GATE"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, str(HOOKS_DIR / hook)], input=payload,
                       capture_output=True, text=True, timeout=60, env=env, cwd=str(tmp_path))
    assert r.returncode == 0, f"{hook} exited {r.returncode} on {payload!r}:\n{r.stderr[:600]}"
    assert "Traceback" not in r.stderr, f"{hook} printed a traceback on {payload!r}"
