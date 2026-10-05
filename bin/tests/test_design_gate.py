"""Regression tests for bin/hooks/design-gate.py.

The gate names no skills of its own; these tests configure it the way a user would at
registration time (command-line arguments) and through the environment. Each test gets its own
state directory and a unique session id, so state cannot bleed between tests.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[1] / "hooks" / "design-gate.py"
ARGS = ["--build-skills=ui-builder,plugin:layout-kit", "--review-skills=look-check,a11y-check"]
SCRUB = ("DESIGN_GATE", "DESIGN_GATE_BUILD_SKILLS", "DESIGN_GATE_REVIEW_SKILLS",
         "DESIGN_GATE_EXTENSIONS", "HARNESS_HOOKS_DISABLED", "CLAUDE_BRAIN_SKIP_HOOKS")


@pytest.fixture()
def gate(tmp_path):
    session = "test-" + uuid.uuid4().hex[:12]

    def run(payload: dict, args=ARGS, **env_extra) -> tuple[int, str, str]:
        env = {k: v for k, v in os.environ.items() if k not in SCRUB}
        env["HARNESS_HOOK_STATE_DIR"] = str(tmp_path / "state")
        env.update(env_extra)
        r = subprocess.run([sys.executable, str(GATE), *args],
                           input=json.dumps({"session_id": session, **payload}),
                           capture_output=True, text=True, timeout=30, env=env)
        return r.returncode, r.stderr, r.stdout

    run.skill = lambda name, **kw: run(
        {"hook_event_name": "PreToolUse", "tool_name": "Skill", "tool_input": {"skill": name}}, **kw)
    run.edit = lambda path, **kw: run(
        {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": path}}, **kw)
    run.stop = lambda **kw: run({"hook_event_name": "Stop", "stop_hook_active": False}, **kw)
    return run


def test_frontend_edit_without_a_design_skill_is_refused(gate):
    code, err, _ = gate.edit("/repo/components/ui/notice-card.tsx")
    assert code == 2 and "design-gate" in err and "ui-builder" in err


def test_frontend_edit_after_a_build_skill_is_allowed(gate):
    assert gate.skill("ui-builder")[0] == 0
    assert gate.edit("/repo/components/ui/notice-card.tsx")[0] == 0


def test_plugin_prefixed_skill_names_match_either_way(gate):
    assert gate.skill("layout-kit")[0] == 0
    assert gate.edit("/repo/app/page.jsx")[0] == 0


def test_non_frontend_files_are_never_gated(gate):
    for p in ("/repo/lib/ui/notice.ts", "/repo/components/ui/notice.test.tsx",
              "/repo/docs/x.html", "/repo/scripts/smoke.ts", "/repo/node_modules/a/b.css"):
        assert gate.edit(p)[0] == 0, p


def test_stop_is_blocked_until_every_review_skill_runs_after_the_edit(gate):
    gate.skill("ui-builder")
    assert gate.edit("/repo/app/globals.css")[0] == 0
    code, err, _ = gate.stop()
    assert code == 2 and "look-check" in err and "a11y-check" in err
    gate.skill("look-check")
    code, err, _ = gate.stop()
    assert code == 2 and "a11y-check" in err and "look-check" not in err.split("Invoke")[1]
    gate.skill("a11y-check")
    assert gate.stop()[0] == 0


def test_a_review_run_before_the_edit_does_not_count(gate):
    gate.skill("look-check")
    gate.skill("a11y-check")
    gate.skill("ui-builder")
    gate.edit("/repo/components/x.tsx")
    assert gate.stop()[0] == 2


def test_stop_block_is_capped_so_a_session_cannot_loop(gate):
    gate.skill("ui-builder")
    gate.edit("/repo/components/x.tsx")
    assert gate.stop()[0] == 2
    assert gate.stop()[0] == 2
    assert gate.stop()[0] == 0, "third stop passes -- the cap"


def test_stop_without_any_frontend_edit_passes(gate):
    assert gate.stop()[0] == 0


def test_no_review_skills_means_no_stop_check(gate):
    gate.skill("ui-builder", args=["--build-skills=ui-builder"])
    gate.edit("/repo/components/x.tsx", args=["--build-skills=ui-builder"])
    assert gate.stop(args=["--build-skills=ui-builder"])[0] == 0


def test_environment_overrides_registered_arguments(gate):
    code, err, _ = gate.edit("/repo/x.vue", DESIGN_GATE_BUILD_SKILLS="env-skill")
    assert code == 2 and "env-skill" in err and "ui-builder" not in err


def test_unconfigured_gate_does_not_block_but_says_so_once(gate):
    code, _, out = gate.edit("/repo/x.tsx", args=[])
    assert code == 0 and "no build skills configured" in out
    code, _, out = gate.edit("/repo/y.tsx", args=[])
    assert code == 0 and out.strip() == ""


def test_custom_extensions(gate):
    args = ARGS + ["--extensions=astro"]
    assert gate.edit("/repo/page.astro", args=args)[0] == 2
    assert gate.edit("/repo/page.tsx", args=args)[0] == 0


def test_escape_hatch(gate):
    assert gate.edit("/repo/a.tsx", DESIGN_GATE="off")[0] == 0


def test_garbage_input_is_fail_safe():
    r = subprocess.run([sys.executable, str(GATE), *ARGS], input="not json",
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
