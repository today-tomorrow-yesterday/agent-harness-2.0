"""skill-shape-guard must block inert skills and must NOT block ordinary documents.

Driven through subprocess with json.dumps, never hand-built shell JSON. That distinction is not
cosmetic: the first hand-test of a sibling guard returned exit 0 for every case because an invalid
escape in shell-quoted JSON made the hook fail open. The test lied, not the hook.

Every case uses an ISOLATED temp skills root via HARNESS_SKILL_ROOTS, so the suite does not depend
on which skills this clone happens to contain.

The false-positive half (does it stay out of the way?) matters as much as the false-negative half.
A guard that flags legitimate documents is one people switch off, and a switched-off guard protects
nothing.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "skill-shape-guard.py"

VALID = "---\nname: demo\ndescription: does a thing.\n---\n\n# demo\n"
NO_FM = "# Skill: Demo\n\n**Use when:** ...\n"


@pytest.fixture()
def skills_root(tmp_path):
    root = tmp_path / "skills"
    root.mkdir(parents=True)
    return root


def run(tool, tool_input, root=None, env_extra=None, raw=None):
    payload = raw if raw is not None else json.dumps(
        {"tool_name": tool, "tool_input": tool_input}
    )
    env = os.environ.copy()
    env.pop("HARNESS_HOOKS_DISABLED", None)
    if root is not None:
        env["HARNESS_SKILL_ROOTS"] = str(root)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload, capture_output=True, text=True, env=env, timeout=60,
    )
    return proc.returncode, proc.stderr


def denied(rc, err):
    return rc == 2 and "BLOCKED" in err


# ------------------------------------------------------------------ must BLOCK -----------------

def test_blocks_an_essay_named_like_a_skill_outside_any_skills_root(tmp_path, skills_root):
    """The original failure: written to scratch, nowhere near a skills root."""
    target = tmp_path / "scratch" / "git-verified-agent-orchestration-skill.md"
    rc, err = run("Write", {"file_path": str(target), "content": NO_FM}, root=skills_root)
    assert denied(rc, err)
    assert "inert" in err


def test_blocks_content_announcing_itself_as_a_skill(tmp_path, skills_root):
    rc, err = run("Write", {"file_path": str(tmp_path / "notes" / "whatever.md"),
                            "content": NO_FM}, root=skills_root)
    assert denied(rc, err)


def test_blocks_loose_md_in_a_skills_root(skills_root):
    rc, err = run("Write", {"file_path": str(skills_root / "my-new-thing.md"),
                            "content": VALID}, root=skills_root)
    assert denied(rc, err)
    assert "SKILL.md" in err


def test_blocks_skill_md_without_frontmatter(skills_root):
    rc, err = run("Write", {"file_path": str(skills_root / "demo" / "SKILL.md"),
                            "content": NO_FM}, root=skills_root)
    assert denied(rc, err)
    assert "no YAML frontmatter" in err


def test_blocks_skill_md_with_bom(skills_root):
    rc, err = run("Write", {"file_path": str(skills_root / "demo" / "SKILL.md"),
                            "content": "﻿" + VALID}, root=skills_root)
    assert denied(rc, err)


def test_blocks_name_directory_mismatch(skills_root):
    rc, err = run("Write", {"file_path": str(skills_root / "other-name" / "SKILL.md"),
                            "content": VALID}, root=skills_root)
    assert denied(rc, err)
    assert "directory" in err


def test_blocks_edit_of_a_loose_md_without_content(skills_root):
    """Edit provides no content, but the path rule alone is enough."""
    rc, err = run("Edit", {"file_path": str(skills_root / "sneaky.md")}, root=skills_root)
    assert denied(rc, err)


# ------------------------------------------------------------- must NOT block ------------------

def test_allows_a_conforming_skill(skills_root):
    rc, err = run("Write", {"file_path": str(skills_root / "demo" / "SKILL.md"),
                            "content": VALID}, root=skills_root)
    assert rc == 0, err


def test_allows_crlf_frontmatter(skills_root):
    rc, err = run("Write", {"file_path": str(skills_root / "demo" / "SKILL.md"),
                            "content": VALID.replace("\n", "\r\n")}, root=skills_root)
    assert rc == 0, err


def test_allows_underscore_support_files(skills_root):
    for name in ("_index.md", "_action-queue.md"):
        rc, err = run("Write", {"file_path": str(skills_root / name), "content": "# x\n"},
                      root=skills_root)
        assert rc == 0, f"{name}: {err}"


def test_allows_reference_files_inside_a_skill_directory(skills_root):
    rc, err = run("Write", {"file_path": str(skills_root / "demo" / "references" / "notes.md"),
                            "content": "# notes\n"}, root=skills_root)
    assert rc == 0, err


def test_allows_a_document_that_merely_mentions_skills(tmp_path, skills_root):
    """The false-positive class: a naive `*skill*.md` match hit 35 innocent files."""
    for name in ("use_design_skills_for_frontend.md", "skills.md", "SKILL-MODE-PATTERN.md"):
        rc, err = run("Write", {"file_path": str(tmp_path / "docs" / name),
                                "content": "# notes about skills\n"}, root=skills_root)
        assert rc == 0, f"{name}: {err}"


def test_allows_an_ordinary_document(tmp_path, skills_root):
    rc, err = run("Write", {"file_path": str(tmp_path / "docs" / "analysis.md"),
                            "content": "# Some Analysis\n\nprose\n"}, root=skills_root)
    assert rc == 0, err


# ------------------------------------------------------------- contract -----------------------

def test_ignores_non_write_tools(skills_root):
    rc, _ = run("Read", {"file_path": str(skills_root / "loose.md")}, root=skills_root)
    assert rc == 0


def test_env_escape_hatch(skills_root):
    rc, _ = run("Write", {"file_path": str(skills_root / "loose.md"), "content": NO_FM},
                root=skills_root, env_extra={"HARNESS_HOOKS_DISABLED": "1"})
    assert rc == 0


def test_fails_open_on_malformed_input(skills_root):
    for bad in ("", "not json", '{"tool_name":'):
        rc, _ = run("Write", {}, root=skills_root, raw=bad)
        assert rc == 0, f"must fail open on {bad!r}"


def test_ignores_relative_paths(skills_root):
    rc, _ = run("Write", {"file_path": "skills/loose.md", "content": NO_FM}, root=skills_root)
    assert rc == 0


def test_hook_exists_and_compiles():
    assert HOOK.is_file()
    subprocess.run([sys.executable, "-m", "py_compile", str(HOOK)], check=True)
