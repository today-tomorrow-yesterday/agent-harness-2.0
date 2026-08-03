"""skill_policy.py — the single owner of "what makes a file an invokable skill".

Three consumers, one source of truth:
  * bin/tests/test_skill_conformance.py -> DETECT drift in what already exists
  * bin/hooks/skill-shape-guard.py      -> PREVENT a bad one being written
  * this module's __main__              -> DESCRIBE the convention to a human or an agent

WHY THIS EXISTS. Asked to "convert this into a skill", an agent produced a well-written 51-line
markdown essay: no frontmatter, a filename nothing looks for, in a directory nothing scans. It
read like a skill and was inert. Reviewing for that turned up a second instance already shipped
in this repo -- skills/session-reflect/SKILL.md carried a UTF-8 BOM ahead of its `---`, which
breaks frontmatter parsing while looking perfectly correct in an editor.

Both failures are SILENT. Nothing errors, no warning appears; the skill simply never loads and
you discover it weeks later when invoking it does nothing. Documentation telling agents the
convention prevented neither. A check at the moment of writing does.

Paths are resolved from this file, never hardcoded, so the repo works on any machine and any
drive. Override the roots with HARNESS_SKILL_ROOTS (os.pathsep-separated) if you keep skills
somewhere else.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BOM = b"\xef\xbb\xbf"
_FRONTMATTER = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.S)
_NAME = re.compile(r"^name:[ \t]*(\S.*?)[ \t]*$", re.M)
_DESCRIPTION = re.compile(r"^description:[ \t]*(\S.*?)[ \t]*$", re.M)


def owned_skill_roots() -> tuple[Path, ...]:
    """Skills roots this policy governs. Env override wins, else <repo>/skills."""
    override = os.environ.get("HARNESS_SKILL_ROOTS")
    if override:
        return tuple(Path(p).expanduser() for p in override.split(os.pathsep) if p.strip())
    return (ROOT / "skills",)


# Files allowed to sit loose in a skills root WITHOUT being an invokable skill. Anything starting
# with "_" is treated as a support file automatically; this dict is for the ones that do not carry
# that marker, and each costs an entry WITH A REASON.
#
# This exception mechanism is not politeness. The first draft of this policy would have flagged a
# deliberate, documented operator runbook that lived in a skills root on purpose -- "fixing" an
# intentional decision. A guard that flags legitimate files is one people learn to switch off, and
# a switched-off guard protects nothing.
DOCUMENTED_FLAT_FILES: dict[str, str] = {}


def is_support_file(name: str) -> bool:
    """Underscore-prefixed files/dirs are catalogs and helpers, never skills."""
    return name.startswith("_")


def check_skill_text(text: str, expected_name: str | None = None) -> list[str]:
    """Reasons this text is not an invokable SKILL.md. Empty list == conforming."""
    problems: list[str] = []
    # Normalize CRLF once. Without this, `$` under re.M leaves the \r inside the captured value,
    # so `name: watch\r\n` reads as 'watch\r' and EVERY CRLF skill on Windows reports a bogus name
    # mismatch. The first run of this module did exactly that: 4 false positives, 0 real. A guard
    # that cries wolf gets muted, so this line is load-bearing.
    text = text.replace("\r\n", "\n")

    m = _FRONTMATTER.match(text)
    if not m:
        first = (text.lstrip().splitlines() or [""])[0][:60]
        problems.append(
            "no YAML frontmatter: a SKILL.md must OPEN with a --- / name: / description: / --- "
            f"block. First line is {first!r}. Without it nothing can discover or invoke this "
            "file -- it is a document about a skill, not a skill."
        )
        return problems  # everything below depends on having parsed the block

    body = m.group(1)
    name_m = _NAME.search(body)
    if not name_m:
        problems.append("frontmatter has no `name:` field")
    if not _DESCRIPTION.search(body):
        problems.append(
            "frontmatter has no `description:` field -- this is the text a harness matches on to "
            "decide whether to load the skill, so an absent one makes it effectively invisible"
        )
    if name_m and expected_name and name_m.group(1) != expected_name:
        problems.append(
            f"frontmatter name is {name_m.group(1)!r} but its directory is {expected_name!r}; "
            "they must match or the skill cannot be addressed by name"
        )
    return problems


def check_skill_bytes(raw: bytes, expected_name: str | None = None) -> list[str]:
    """Byte-level check first: a BOM breaks frontmatter while looking fine in an editor."""
    problems: list[str] = []
    if raw.startswith(BOM):
        problems.append(
            "file begins with a UTF-8 BOM, which breaks YAML frontmatter parsing even though the "
            "text looks correct in an editor. On Windows this is the PowerShell 5.1 "
            "`Set-Content -Encoding utf8` signature -- write with Python `encoding='utf-8'` "
            "instead. This shipped undetected in this repo's own session-reflect skill."
        )
        raw = raw[len(BOM):]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return problems + [f"not valid UTF-8: {e}"]
    return problems + check_skill_text(text, expected_name)


def audit_root(root: Path) -> list[tuple[Path, str]]:
    """Every conformance failure under one skills root, as (path, reason)."""
    findings: list[tuple[Path, str]] = []
    if not root.is_dir():
        return findings

    for entry in sorted(root.iterdir()):
        if is_support_file(entry.name):
            continue

        if entry.is_file():
            if entry.suffix.lower() != ".md" or entry.name in DOCUMENTED_FLAT_FILES:
                continue
            findings.append((
                entry,
                "loose .md in a skills root. An invokable skill must be "
                f"{entry.stem}/SKILL.md, not a bare file. If it is intentionally NOT a skill, "
                "prefix it with `_` or add it to skill_policy.DOCUMENTED_FLAT_FILES with a reason.",
            ))
            continue

        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            findings.append((entry, "skill directory has no SKILL.md"))
            continue
        for problem in check_skill_bytes(skill_md.read_bytes(), expected_name=entry.name):
            findings.append((skill_md, problem))

    return findings


def audit_all() -> list[tuple[Path, str]]:
    return [f for root in owned_skill_roots() for f in audit_root(root)]


def describe() -> str:
    roots = "\n".join(f"  {r}" for r in owned_skill_roots())
    return (
        "An invokable skill is a DIRECTORY, not a file:\n"
        "\n"
        "    <skills-root>/<skill-name>/SKILL.md\n"
        "\n"
        "and that SKILL.md must open with these as its very first bytes (no BOM, nothing above):\n"
        "\n"
        "    ---\n"
        "    name: <skill-name>          # must equal the directory name\n"
        "    description: <when to use this, in one sentence>\n"
        "    ---\n"
        "\n"
        f"Roots governed (override with HARNESS_SKILL_ROOTS):\n{roots}\n"
        "\n"
        "A markdown file with none of the above is a document ABOUT a skill. It will be silently\n"
        "unusable: nothing will ever load it, and nothing errors to tell you so."
    )


if __name__ == "__main__":
    print(describe())
    print()
    findings = audit_all()
    if not findings:
        print("audit: all skills conform")
    else:
        print(f"audit: {len(findings)} problem(s)")
        for path, reason in findings:
            print(f"  {path}\n      {reason}")
