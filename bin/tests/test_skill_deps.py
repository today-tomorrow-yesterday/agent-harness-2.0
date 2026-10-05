"""skill_deps.py: when a document a skill distils changes after the skill was last reconciled,
the skill must be raised as stale. Without this, knowledge can change with no consequence for
the skills that encode it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import skill_deps as sd


def skill(p: Path, fm: str) -> None:
    p.mkdir(parents=True, exist_ok=True)
    (p / "SKILL.md").write_text(f"---\nname: {p.name}\ndescription: x.\n{fm}\n---\n\n# body\n",
                                encoding="utf-8")


def doc(root: Path, rel: str) -> None:
    fp = root / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("# doc\n", encoding="utf-8")


# ------------------------------------------------------------------ parsing

def test_parses_block_list_form():
    docs, synced = sd.parse_declaration(
        "---\nname: s\nknowledge:\n  - docs/a.md\n  - 'docs/b.md'\nknowledge_synced: 2026-08-01\n"
        "---\n")
    assert docs == ["docs/a.md", "docs/b.md"] and synced == "2026-08-01"


def test_parses_inline_list_form():
    docs, _ = sd.parse_declaration("---\nname: s\nknowledge: [docs/a.md, \"docs/b.md\"]\n---\n")
    assert docs == ["docs/a.md", "docs/b.md"]


def test_list_ends_at_the_next_key():
    docs, synced = sd.parse_declaration(
        "---\nname: s\nknowledge:\n  - docs/a.md\ndescription: not a doc\n"
        "knowledge_synced: 2026-08-01\n---\n")
    assert docs == ["docs/a.md"] and synced == "2026-08-01"


def test_similar_key_names_are_not_confused():
    docs, synced = sd.parse_declaration(
        "---\nname: s\nknowledge_base: x\nknowledge:\n  - docs/a.md\n---\n")
    assert docs == ["docs/a.md"] and synced is None


def test_crlf_bom_and_no_frontmatter():
    text = "﻿---\r\nname: s\r\nknowledge:\r\n  - docs/a.md\r\n---\r\n"
    assert sd.parse_declaration(text)[0] == ["docs/a.md"]
    assert sd.parse_declaration("# no frontmatter\n") == ([], None)


# ------------------------------------------------------------------ the signal

def test_doc_changed_after_sync_marks_skill_stale(tmp_path, monkeypatch):
    root, skills = tmp_path / "kb", tmp_path / "skills"
    doc(root, "docs/a.md")
    skill(skills / "s1", "knowledge:\n  - docs/a.md\nknowledge_synced: 2026-07-01")
    monkeypatch.setattr(sd, "git_dates", lambda _r: {"docs/a.md": "2026-07-20"})
    d = sd.analyse(skills, root)[0]
    assert d.severity == "ORANGE" and d.stale == [("docs/a.md", "2026-07-20")]
    assert "has since been revised" in "\n".join(sd.render([d]))


def test_doc_changed_before_sync_is_green(tmp_path, monkeypatch):
    root, skills = tmp_path / "kb", tmp_path / "skills"
    doc(root, "docs/a.md")
    skill(skills / "s1", "knowledge:\n  - docs/a.md\nknowledge_synced: 2026-08-01")
    monkeypatch.setattr(sd, "git_dates", lambda _r: {"docs/a.md": "2026-07-20"})
    assert sd.analyse(skills, root)[0].severity == "GREEN"


def test_declared_doc_that_does_not_exist_is_red(tmp_path, monkeypatch):
    root, skills = tmp_path / "kb", tmp_path / "skills"
    root.mkdir()
    skill(skills / "s1", "knowledge:\n  - docs/gone.md\nknowledge_synced: 2026-08-01")
    monkeypatch.setattr(sd, "git_dates", lambda _r: {})
    d = sd.analyse(skills, root)[0]
    assert d.severity == "RED" and d.missing == ["docs/gone.md"]


def test_never_synced_and_undeclared(tmp_path, monkeypatch):
    root, skills = tmp_path / "kb", tmp_path / "skills"
    doc(root, "docs/a.md")
    skill(skills / "s1", "knowledge:\n  - docs/a.md")
    skill(skills / "plain", "")
    monkeypatch.setattr(sd, "git_dates", lambda _r: {})
    deps = sd.analyse(skills, root)
    assert [d.skill for d in deps] == ["s1"]
    assert "synced NEVER" in "\n".join(sd.render(deps))


def test_reverse_map_is_the_blast_radius(tmp_path, monkeypatch):
    root, skills = tmp_path / "kb", tmp_path / "skills"
    doc(root, "docs/shared.md")
    for s in ("s1", "s2"):
        skill(skills / s, "knowledge:\n  - docs/shared.md\nknowledge_synced: 2026-08-01")
    monkeypatch.setattr(sd, "git_dates", lambda _r: {})
    assert sorted(sd.reverse_map(sd.analyse(skills, root))["docs/shared.md"]) == ["s1", "s2"]


def test_zero_declarations_says_so():
    assert "No skill declares" in "\n".join(sd.render([]))


def test_strict_exit_code(tmp_path, monkeypatch):
    root, skills = tmp_path / "kb", tmp_path / "skills"
    root.mkdir()
    skill(skills / "s1", "knowledge:\n  - docs/gone.md")
    monkeypatch.setattr(sd, "git_dates", lambda _r: {})
    args = ["--skills-dir", str(skills), "--knowledge-root", str(root)]
    assert sd.main(args) == 0
    assert sd.main(args + ["--strict"]) == 1


# ------------------------------------------------------------------ real git, pinned dates

def _git(root: Path, *args: str, date: str | None = None) -> None:
    env = None
    if date:
        import os
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def test_git_dates_reads_latest_commit_per_file_relative_to_root(tmp_path):
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    doc(repo, "kb/docs/a.md")
    _git(repo, "add", "kb/docs/a.md")
    _git(repo, "commit", "-q", "-m", "one", date="2026-07-01T10:00:00+00:00")
    (repo / "kb" / "docs" / "a.md").write_text("# changed\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "two", date="2026-07-20T10:00:00+00:00")
    assert sd.git_dates(repo / "kb") == {"docs/a.md": "2026-07-20"}
    assert sd.git_dates(tmp_path / "not-a-repo") == {}
