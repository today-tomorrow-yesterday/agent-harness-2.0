"""Every skill in this repo must actually be invokable.

Guards a real, shipped failure. An agent asked to "convert this into a skill" produced a 51-line
markdown essay with no frontmatter, under a filename nothing looks for. It read like a skill and
could never be loaded. Reviewing for it found a second instance ALREADY IN THIS REPO --
skills/session-reflect/SKILL.md carried a UTF-8 BOM ahead of its `---`, silently breaking
frontmatter parsing while looking perfect in an editor.

Both failures are invisible at runtime: nothing errors, the skill simply never loads. That is
exactly the class of bug that needs a test, because there is no symptom to notice.

Policy lives in bin/skill_policy.py and is shared with bin/hooks/skill-shape-guard.py.
"""
from __future__ import annotations

import pytest

import skill_policy
from skill_policy import (
    DOCUMENTED_FLAT_FILES,
    audit_all,
    check_skill_bytes,
    check_skill_text,
    is_support_file,
    owned_skill_roots,
)

VALID = b"---\nname: demo\ndescription: does a thing.\n---\n\n# demo\n"


# --------------------------------------------------------------- the live state ----------------

def test_every_skill_in_this_repo_is_invokable():
    findings = audit_all()
    if findings:
        detail = "\n".join(f"  {p}\n      {why}" for p, why in findings)
        pytest.fail(
            f"{len(findings)} skill(s) cannot be invoked:\n{detail}\n\n"
            "A skill must be <root>/<name>/SKILL.md opening with BOM-free "
            "--- / name: / description: / --- frontmatter whose name equals its directory."
        )


def test_skills_root_exists_and_is_not_empty():
    """Without this, a renamed root would make the suite pass by scanning nothing."""
    roots = owned_skill_roots()
    assert roots, "no skills roots resolved"
    found = [d for r in roots if r.is_dir() for d in r.iterdir()
             if d.is_dir() and not is_support_file(d.name)]
    assert found, f"no skill directories under {[str(r) for r in roots]}"


def test_roots_are_repo_relative_not_hardcoded():
    """This repo is handed to other people. A machine-specific path would break on clone."""
    for root in owned_skill_roots():
        assert root.is_absolute(), root
        # resolved from skill_policy.ROOT, so it must live inside the repo
        assert skill_policy.ROOT in root.parents or root.parent == skill_policy.ROOT, (
            f"{root} is not inside the repo root {skill_policy.ROOT} -- "
            "roots must derive from __file__, never a literal drive path"
        )


# --------------------------------------------------------------- the checker itself ------------
# The instrument gets tested too. The first run of this policy reported 4 name mismatches that
# were ALL artifacts of `$` under re.M capturing the \r of CRLF -- 0 real problems. A guard with a
# high false-positive rate gets muted, so these pin the exact shapes.

def test_valid_skill_conforms():
    assert check_skill_bytes(VALID, expected_name="demo") == []


def test_crlf_skill_conforms():
    """The regression that made this checker cry wolf on real, correct skills."""
    assert check_skill_bytes(VALID.replace(b"\n", b"\r\n"), expected_name="demo") == []


def test_essay_without_frontmatter_is_rejected():
    essay = b"# Skill: Git-Verified Agent Orchestration\n\n**Use when:** ...\n"
    problems = check_skill_bytes(essay, expected_name="git-verified-agent-orchestration")
    assert problems and "no YAML frontmatter" in problems[0]


def test_bom_is_rejected():
    problems = check_skill_bytes(b"\xef\xbb\xbf" + VALID, expected_name="demo")
    assert any("BOM" in p for p in problems)


def test_missing_description_is_rejected():
    problems = check_skill_text("---\nname: demo\n---\n\n# demo\n", expected_name="demo")
    assert any("description" in p for p in problems)


def test_missing_name_is_rejected():
    problems = check_skill_text("---\ndescription: x.\n---\n\n# d\n", expected_name="demo")
    assert any("`name:`" in p for p in problems)


def test_name_directory_mismatch_is_rejected():
    problems = check_skill_bytes(VALID, expected_name="something-else")
    assert any("directory" in p for p in problems)


def test_frontmatter_must_be_the_first_thing_in_the_file():
    """Prose above the block means no harness ever sees the frontmatter."""
    problems = check_skill_text("# Title\n\n---\nname: demo\ndescription: x.\n---\n", "demo")
    assert problems and "no YAML frontmatter" in problems[0]


def test_not_utf8_is_rejected_without_crashing():
    problems = check_skill_bytes(b"---\nname: demo\ndescription: \xff\xfe.\n---\n", "demo")
    assert problems and "UTF-8" in problems[0]


# --------------------------------------------------------------- isolation + exceptions --------

def test_audit_detects_a_loose_md_in_a_temp_root(tmp_path, monkeypatch):
    """Drives audit_all() through the env override, so the test does not depend on this repo's
    actual skills and cannot be made vacuous by someone tidying them."""
    root = tmp_path / "skills"
    (root / "good").mkdir(parents=True)
    (root / "good" / "SKILL.md").write_bytes(b"---\nname: good\ndescription: x.\n---\n")
    (root / "stray-notes.md").write_text("# not a skill\n", encoding="utf-8")
    (root / "_index.md").write_text("# support file\n", encoding="utf-8")
    monkeypatch.setenv("HARNESS_SKILL_ROOTS", str(root))

    findings = audit_all()
    paths = {p.name for p, _ in findings}
    assert "stray-notes.md" in paths, "a loose .md must be reported"
    assert "_index.md" not in paths, "underscore support files must be exempt"
    assert "SKILL.md" not in paths, "the conforming skill must not be reported"


def test_directory_without_skill_md_is_reported(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    (root / "empty-skill").mkdir(parents=True)
    monkeypatch.setenv("HARNESS_SKILL_ROOTS", str(root))
    assert any("no SKILL.md" in why for _, why in audit_all())


def test_every_documented_exception_names_a_real_file():
    """A stale exemption silently widens the guard."""
    for name in DOCUMENTED_FLAT_FILES:
        assert any((root / name).is_file() for root in owned_skill_roots()), (
            f"DOCUMENTED_FLAT_FILES lists {name!r} but no governed root contains it -- "
            "remove the stale exemption"
        )


def test_underscore_files_are_support_not_skills():
    assert is_support_file("_index.md")
    assert not is_support_file("agentshield-watch.md")
