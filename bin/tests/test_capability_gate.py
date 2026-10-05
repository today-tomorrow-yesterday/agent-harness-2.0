"""Tests for bin/hooks/capability-gate.py -- advisory, once-per-session discovery hints.

The gate must never deny (exit code is always 0), must say each thing once per session, and must
stay quiet on ordinary work. Each test isolates its state dir and settings file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]
HOOK = BIN / "hooks" / "capability-gate.py"
REPO = BIN.parent
SCRUB = ("HARNESS_HOOKS_DISABLED", "CLAUDE_BRAIN_SKIP_HOOKS", "CAPABILITY_GATE")


@pytest.fixture()
def gate(tmp_path):
    session = "test-" + uuid.uuid4().hex[:12]
    settings = tmp_path / "settings.json"

    def run(payload: dict, **env_extra) -> str:
        env = {k: v for k, v in os.environ.items() if k not in SCRUB}
        env.update(HARNESS_HOOK_STATE_DIR=str(tmp_path / "state"),
                   CLAUDE_SETTINGS_PATH=str(settings))
        env.update(env_extra)
        r = subprocess.run([sys.executable, str(HOOK)],
                           input=json.dumps({"session_id": session, **payload}),
                           capture_output=True, text=True, timeout=30, env=env)
        assert r.returncode == 0, r.stderr          # advisory: never denies
        assert "Traceback" not in r.stderr
        if not r.stdout.strip():
            return ""
        out = json.loads(r.stdout)
        return out["hookSpecificOutput"]["additionalContext"]

    run.tool = lambda tool, ti, **kw: run(
        {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": ti}, **kw)
    run.prompt = lambda text, **kw: run(
        {"hook_event_name": "UserPromptSubmit", "prompt": text}, **kw)
    run.settings = settings
    return run


def test_reading_the_keyring_points_at_the_redacting_wrapper(gate):
    ctx = gate.tool("Read", {"file_path": str(REPO / "bin" / "secrets" / "keyring.env")})
    assert "KEYRING" in ctx and "api.py" in ctx


def test_hint_fires_once_per_session(gate):
    ti = {"command": "cat bin/secrets/keyring.env"}
    assert "KEYRING" in gate.tool("Bash", ti)
    assert gate.tool("Bash", ti) == ""


def test_the_keyring_template_is_not_flagged(gate):
    assert gate.tool("Read", {"file_path": "bin/secrets/keyring.env.template"}) == ""


def test_memory_and_skill_writes_get_their_reminders(gate):
    assert "MEMORY.md" in gate.tool("Write", {"file_path": str(REPO / "memory" / "feedback" / "x.md")})
    assert "capability-map-gen" in gate.tool("Edit", {"file_path": str(REPO / "skills" / "x" / "SKILL.md")})


def test_new_bin_script_gets_the_scheduler_reminder(gate):
    assert "jobs.py" in gate.tool("Write", {"file_path": str(REPO / "bin" / "brand_new_tool.py")})
    assert gate.tool("Write", {"file_path": str(REPO / "bin" / "register_hook.py")}) == ""


def test_ordinary_work_is_silent(gate):
    assert gate.tool("Read", {"file_path": str(REPO / "README.md")}) == ""
    assert gate.tool("Bash", {"command": "git status"}) == ""
    assert gate.tool("Write", {"file_path": "/elsewhere/memory/notes.md"}) == ""


def test_prompt_matching_a_skill_trigger_gets_a_skill_hint(gate):
    ctx = gate.prompt("can you convert this into a skill")
    assert "SKILL HINT" in ctx and "/skill-authoring" in ctx


def test_prompt_hints_stay_quiet_on_small_talk(gate):
    assert gate.prompt("what time is it") == ""
    assert gate.prompt("review our nightly runs") == ""


def test_skills_switched_off_in_settings_are_not_suggested(gate):
    gate.settings.write_text(json.dumps({"skillOverrides": {"skill-authoring": "off"}}),
                             encoding="utf-8")
    assert gate.prompt("make this a skill please") == ""


def test_off_switch(gate):
    assert gate.prompt("convert this into a skill", CAPABILITY_GATE="off") == ""
