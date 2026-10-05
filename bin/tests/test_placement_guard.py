"""placement-guard must REFUSE a new top-level directory in a protected root -- and stay out of
the way of everything else.

Driven through subprocess with json.dumps. The first hand-test of the original guard was
inconclusive because shell-quoted JSON produced an invalid escape, the hook took its fail-open
path, and every case returned 0 -- which looked exactly like "the guard does not work".

Most cases protect an isolated temp root through HARNESS_PLACEMENT_POLICY, so the suite does not
depend on this checkout's layout. Two cases exercise the built-in repo policy.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]
HOOK = BIN / "hooks" / "placement-guard.py"
REPO = BIN.parent
SCRUB = ("HARNESS_HOOKS_DISABLED", "CLAUDE_BRAIN_SKIP_HOOKS", "HARNESS_PLACEMENT_POLICY")


@pytest.fixture()
def root(tmp_path):
    r = tmp_path / "work"
    (r / "existing" / "deep").mkdir(parents=True)
    return r


@pytest.fixture()
def policy(tmp_path, root):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"include_repo": False,
                             "roots": {str(root): ["tools", "clients"]}}), encoding="utf-8")
    return p


def run_hook(payload, policy=None, cwd=None, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in SCRUB}
    if policy is not None:
        env["HARNESS_PLACEMENT_POLICY"] = str(policy)
    env.update(env_extra)
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, cwd=str(cwd) if cwd else None, timeout=30)
    return p.returncode, p.stderr or ""


def write(path) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": str(path)}}


def shell(cmd: str, tool: str = "Bash") -> dict:
    return {"tool_name": tool, "tool_input": {"command": cmd}}


# ---------------------------------------------------------------- must DENY -----------------

@pytest.mark.parametrize("rel", ["newthing/notes.md", "scratchpad/a/b/c.txt"])
def test_write_denies_new_toplevel_dir(root, rel, policy):
    code, err = run_hook(write(root / rel), policy)
    assert code == 2, err
    assert "new top-level directory" in err and "tools" in err


def test_multiedit_is_covered(root, policy):
    payload = {"tool_name": "MultiEdit",
               "tool_input": {"edits": [{"file_path": str(root / "sneaky" / "x.md")}]}}
    assert run_hook(payload, policy)[0] == 2


@pytest.mark.parametrize("cmd", [
    "mkdir -p {r}/scratchpad",
    "mkdir {r}/scratchpad",
    "New-Item -ItemType Directory -Path {r}/junk -Force",
    "cd /tmp && md {r}/junk",
])
def test_shell_denies_mkdir_of_new_toplevel(root, cmd, policy):
    code, err = run_hook(shell(cmd.format(r=root.as_posix())), policy)
    assert code == 2, f"{cmd}: {err}"


def test_relative_mkdir_resolves_against_the_cwd(root, policy):
    assert run_hook(shell("mkdir newdir"), policy, cwd=root)[0] == 2
    assert run_hook(shell("mkdir existing/newdir"), policy, cwd=root)[0] == 0


def test_repo_policy_blocks_a_new_toplevel_dir_in_this_repo():
    code, err = run_hook(write(REPO / "definitely-not-allowed-dir" / "x.md"))
    assert code == 2 and "this repository" in err


# ---------------------------------------------------------------- must ALLOW ----------------

@pytest.mark.parametrize("rel", [
    "existing/whatever.md",                # existing top level
    "existing/new-nested/record.md",       # NEW nested dir under an existing one
    "tools/new-tool/README.md",            # allowlisted but not yet created
    "top-level-file.md",                   # plain files at the top are not policed
])
def test_write_allows_legitimate_places(root, rel, policy):
    code, err = run_hook(write(root / rel), policy)
    assert code == 0, f"{rel}: {err}"


def test_repo_policy_allows_nested_dirs_in_this_repo():
    assert run_hook(write(REPO / "docs" / "brand-new-subdir" / "x.md"))[0] == 0


def test_outside_every_protected_root_is_ignored(root, tmp_path, policy):
    assert run_hook(write(tmp_path / "elsewhere" / "x.md"), policy)[0] == 0


def test_mentioning_a_path_in_a_quoted_string_is_not_a_violation(root, policy):
    """Text ABOUT a path must pass. Over-blocking teaches people to disable the guard."""
    cmd = f'grep -r "mkdir {root.as_posix()}/foo" ./docs'
    assert run_hook(shell(cmd), policy)[0] == 0


def test_reading_is_never_blocked(root, policy):
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(root / "newthing" / "x.md")}}
    assert run_hook(payload, policy)[0] == 0


def test_unreadable_policy_falls_back_to_repo_default(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ nope", encoding="utf-8")
    assert run_hook(write(tmp_path / "anything" / "x.md"), bad)[0] == 0


# ---------------------------------------------------------------- fail-open -----------------

def test_malformed_json_fails_open():
    p = subprocess.run([sys.executable, str(HOOK)], input='{"tool_name":"Write", BROKEN',
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0


def test_disable_switch_is_honoured(root, policy):
    assert run_hook(write(root / "newthing" / "x.md"), policy,
                    HARNESS_HOOKS_DISABLED="1")[0] == 0
