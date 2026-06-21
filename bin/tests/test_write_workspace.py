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
