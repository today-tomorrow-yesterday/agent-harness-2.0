"""Tests for the WriteWorkspace action: it must PARK for approval (disabled class),
be reversible, and refuse to write its own guardrails or escape the workspace."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # bin/ on path
from execution.actions.write_workspace import WriteWorkspace  # noqa: E402
from execution.execute import execute  # noqa: E402


def test_parks_for_approval_and_does_not_write(tmp_path):
    a = WriteWorkspace(path="notes/x.md", content="hi", root=str(tmp_path))
    res = execute(a, db_path=str(tmp_path / "r.db"))
    assert res["status"] == "pending"            # disabled class -> approval queue
    assert res["decision"] == "PAUSE"
    assert not (tmp_path / "notes" / "x.md").exists()   # nothing written autonomously


def test_run_writes_and_backs_up_existing(tmp_path):
    (tmp_path / "a.md").write_text("old", encoding="utf-8")
    out = WriteWorkspace(path="a.md", content="new", root=str(tmp_path)).run()
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "new"
    assert (tmp_path / "a.md.bak").read_text(encoding="utf-8") == "old"   # reversible
    assert out["wrote"] == "a.md" and out["backup"] == "a.md.bak"


def test_run_creates_new_file_no_backup(tmp_path):
    out = WriteWorkspace(path="sub/new.md", content="x", root=str(tmp_path)).run()
    assert (tmp_path / "sub" / "new.md").read_text(encoding="utf-8") == "x"
    assert out["backup"] is None


def test_denies_protected_policy_file(tmp_path):
    with pytest.raises(PermissionError):
        WriteWorkspace(path="forge/execution_policy.json", content="{}", root=str(tmp_path)).run()


def test_denies_execution_code_subtree(tmp_path):
    with pytest.raises(PermissionError):
        WriteWorkspace(path="bin/runner/guard.py", content="x", root=str(tmp_path)).run()


def test_denies_path_escape(tmp_path):
    with pytest.raises(ValueError):
        WriteWorkspace(path="../escape.md", content="x", root=str(tmp_path)).run()


# ------------------------------------------------------- guardrail paths are refused
@pytest.mark.parametrize("path", [
    "bin/hooks/some-guard.py",        # a hook that gates every shell command
    "bin/hooks/nested/deep.py",       # whole subtree, not just the top level
    "bin/secrets/keyring.env",
    "bin/scheduler/jobs.py",          # registering a job = persistence
    "bin/self_loop.py",               # the supervisor of autonomous work
    "forge/STOP",                     # the kill-switch
    "forge/runner.db",                # the audit log + approval queue
    "CLAUDE.md",                      # the standing rules
    "memory/MEMORY.md",
])
def test_denies_guardrail_paths(tmp_path, path):
    with pytest.raises(PermissionError):
        WriteWorkspace(path=path, content="import sys; sys.exit(0)", root=str(tmp_path)).run()
    assert not (tmp_path / path).exists(), "a denied write must leave nothing behind"


# ------------------------------------------------- deny-list anchored to the repo
# Every deny-list entry is REPO-relative, but `root` is a caller-supplied field. A root
# deeper than the repo used to shorten the checked path out of the list's reach while
# containment still passed.
@pytest.mark.parametrize("root_sub, path", [
    ("bin", "hooks/some-guard.py"),
    ("bin", "secrets/probe-does-not-exist.env"),
    ("bin", "execution/policy.py"),
    ("bin", "runner/events.py"),
    ("forge", "STOP"),
    ("forge", "execution_policy.json"),
    ("memory", "user.md"),
])
def test_deny_list_is_anchored_to_the_repo_not_the_callers_root(root_sub, path):
    from execution.actions.write_workspace import REPO
    root = REPO / root_sub
    target = root / path
    before = target.read_bytes() if target.exists() else None
    with pytest.raises(PermissionError, match="protected path"):
        WriteWorkspace(path=path, content="# clobbered", root=str(root)).run()
    after = target.read_bytes() if target.exists() else None
    assert after == before, f"{path} was modified despite being protected"


def test_root_relative_deny_still_applies_outside_the_repo(tmp_path):
    with pytest.raises(PermissionError, match="protected path"):
        WriteWorkspace(path="forge/STOP", content="x", root=str(tmp_path)).run()
    assert not (tmp_path / "forge" / "STOP").exists()


def test_a_second_write_never_overwrites_the_first_backup(tmp_path):
    (tmp_path / "a.md").write_text("v1", encoding="utf-8")
    WriteWorkspace(path="a.md", content="v2", root=str(tmp_path)).run()
    out = WriteWorkspace(path="a.md", content="v3", root=str(tmp_path)).run()
    assert (tmp_path / "a.md.bak").read_text(encoding="utf-8") == "v1"    # original kept
    assert (tmp_path / "a.md.bak1").read_text(encoding="utf-8") == "v2"
    assert out["backup"] == "a.md.bak1"
