"""Tests for bin/register_hook.py -- wiring hooks into a Claude Code settings.json.

Always against a temp settings file via CLAUDE_SETTINGS_PATH; the real profile is never touched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]
REG = BIN / "register_hook.py"
HOOKS = BIN / "hooks"

sys.path.insert(0, str(BIN))
import register_hook  # noqa: E402


def run(settings: Path, *args) -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_SETTINGS_PATH=str(settings), PYTHONIOENCODING="utf-8")
    env.pop("DESIGN_GATE_BUILD_SKILLS", None)
    return subprocess.run([sys.executable, str(REG), *args], capture_output=True, text=True,
                          env=env, timeout=60)


def load(settings: Path) -> dict:
    return json.loads(settings.read_bytes().decode("utf-8-sig"))


def test_every_hook_on_disk_is_in_the_catalog_and_vice_versa():
    on_disk = set(register_hook.available_hooks())
    assert on_disk == set(register_hook.CATALOG), (
        "bin/hooks/*-*.py and register_hook.CATALOG disagree -- a hook nobody can register, or a "
        "catalog entry with no script")


def test_register_all_then_idempotent(tmp_path):
    s = tmp_path / "settings.json"
    r = run(s, "--all")
    assert r.returncode == 0, r.stdout + r.stderr
    data = load(s)
    for name, plan in register_hook.CATALOG.items():
        for event, matcher in plan:
            entries = [e for e in data["hooks"][event]
                       if any(f"hooks/{name}.py" in h["command"] for h in e["hooks"])]
            assert len(entries) == 1, (name, event)
            assert entries[0].get("matcher") == matcher
    before = s.read_bytes()
    assert run(s, "--all").returncode == 0
    assert s.read_bytes() == before


def test_registration_preserves_unrelated_settings_and_bom(tmp_path):
    s = tmp_path / "settings.json"
    s.write_bytes(b"\xef\xbb\xbf" + json.dumps({"theme": "light", "hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-hook"}]}]}}).encode())
    assert run(s, "pre-tool-guard").returncode == 0
    raw = s.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    data = load(s)
    assert data["theme"] == "light"
    cmds = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert "other-hook" in cmds and any("pre-tool-guard.py" in c for c in cmds)


def test_no_bom_is_introduced(tmp_path):
    s = tmp_path / "settings.json"
    run(s, "safety-queue")
    assert not s.read_bytes().startswith(b"\xef\xbb\xbf")


def test_hook_args_are_passed_and_updated_in_place(tmp_path):
    s = tmp_path / "settings.json"
    assert run(s, "design-gate", "--hook-arg=--build-skills=a,b").returncode == 0
    assert run(s, "design-gate", "--hook-arg=--build-skills=c").returncode == 0
    data = load(s)
    pre = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert len(pre) == 1 and "--build-skills=c" in pre[0] and "a,b" not in pre[0]
    assert "design-gate.py" in data["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "matcher" not in data["hooks"]["Stop"][0]


# --- review P2: an unchanged command must not short-circuit matcher/timeout updates ------------

def _entries(settings: Path, event: str, name: str) -> list[dict]:
    return [e for e in load(settings)["hooks"].get(event, [])
            if any(f"hooks/{name}.py" in h["command"] for h in e["hooks"])]


def test_rerun_with_new_timeout_updates_it(tmp_path):
    s = tmp_path / "settings.json"
    run(s, "pre-tool-guard")
    r = run(s, "pre-tool-guard", "--timeout", "30")
    assert r.returncode == 0 and "updated" in r.stdout
    (entry,) = _entries(s, "PreToolUse", "pre-tool-guard")
    assert entry["hooks"][0]["timeout"] == 30
    run(s, "pre-tool-guard")                       # a plain re-run keeps the chosen timeout
    assert _entries(s, "PreToolUse", "pre-tool-guard")[0]["hooks"][0]["timeout"] == 30


def test_rerun_restores_a_narrowed_catalog_matcher(tmp_path):
    """A guard narrowed to `Read` by hand never sees Bash; re-registering must repair that."""
    s = tmp_path / "settings.json"
    run(s, "pre-tool-guard")
    data = load(s)
    data["hooks"]["PreToolUse"][0]["matcher"] = "Read"
    s.write_text(json.dumps(data), encoding="utf-8")
    r = run(s, "pre-tool-guard")
    assert r.returncode == 0 and "updated" in r.stdout
    (entry,) = _entries(s, "PreToolUse", "pre-tool-guard")
    assert entry["matcher"] == "Bash|PowerShell"


def test_matcher_fix_leaves_other_hooks_in_a_shared_entry_alone(tmp_path):
    s = tmp_path / "settings.json"
    cmd = register_hook.hook_command("pre-tool-guard")
    s.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [
        {"type": "command", "command": "other-hook", "timeout": 5},
        {"type": "command", "command": cmd, "timeout": 10}]}]}}), encoding="utf-8")
    run(s, "pre-tool-guard")
    pre = load(s)["hooks"]["PreToolUse"]
    assert pre[0] == {"matcher": "Read", "hooks": [
        {"type": "command", "command": "other-hook", "timeout": 5}]}
    (entry,) = _entries(s, "PreToolUse", "pre-tool-guard")
    assert entry["matcher"] == "Bash|PowerShell"


def test_duplicate_registrations_collapse_to_one(tmp_path):
    s = tmp_path / "settings.json"
    cmd = register_hook.hook_command("safety-queue")
    dup = {"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": cmd,
                                                    "timeout": 10}]}
    s.write_text(json.dumps({"hooks": {"PreToolUse": [dup, dup]}}), encoding="utf-8")
    assert run(s, "safety-queue").returncode == 0
    assert len(_entries(s, "PreToolUse", "safety-queue")) == 1


def test_rerun_without_hook_args_keeps_the_configured_ones(tmp_path):
    s = tmp_path / "settings.json"
    run(s, "design-gate", "--hook-arg=--build-skills=ui-builder")
    r = run(s, "--all")
    assert r.returncode == 0
    for event in ("PreToolUse", "Stop"):
        (entry,) = _entries(s, event, "design-gate")
        assert "--build-skills=ui-builder" in entry["hooks"][0]["command"]
    assert "no --build-skills" not in r.stdout


def test_unconfigured_design_gate_is_announced(tmp_path):
    r = run(tmp_path / "settings.json", "design-gate")
    assert "no --build-skills" in r.stdout


def test_remove(tmp_path):
    s = tmp_path / "settings.json"
    run(s, "capability-gate", "pre-tool-guard")
    r = run(s, "capability-gate", "--remove")
    assert r.returncode == 0, r.stdout
    data = load(s)
    assert "UserPromptSubmit" not in data["hooks"]
    cmds = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert len(cmds) == 1 and "pre-tool-guard" in cmds[0]


def test_legacy_single_event_form_still_works(tmp_path):
    s = tmp_path / "settings.json"
    r = run(s, "skill-shape-guard", "--event", "PreToolUse", "--matcher", "Write|Edit")
    assert r.returncode == 0
    assert load(s)["hooks"]["PreToolUse"][0]["matcher"] == "Write|Edit"


def test_verify_changes_nothing_and_reports_missing(tmp_path):
    s = tmp_path / "settings.json"
    r = run(s, "pre-tool-guard", "--verify")
    assert r.returncode == 1 and not s.exists()


def test_unknown_hook_is_refused(tmp_path):
    r = run(tmp_path / "settings.json", "no-such-hook")
    assert r.returncode == 1 and "no such hook" in r.stderr


def test_list(tmp_path):
    s = tmp_path / "settings.json"
    run(s, "pre-tool-guard")
    out = run(s, "--list").stdout
    assert "pre-tool-guard" in out and "PreToolUse=yes" in out and "design-gate" in out


@pytest.mark.parametrize("name", sorted(register_hook.CATALOG))
def test_registered_command_actually_runs_the_hook(name, tmp_path):
    """The command line written to settings.json must execute and exit 0 on an empty payload --
    the same quoting works from every shell Claude Code may use."""
    cmd = register_hook.hook_command(name)
    r = subprocess.run(cmd, shell=True, input="{}", capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
