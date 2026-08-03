#!/usr/bin/env python3
"""PreToolUse guard: refuse to write a "skill" that could never be invoked.

WHY. Asked to "convert this into a skill", an agent produced a 51-line markdown essay -- no
frontmatter, a filename nothing looks for, written into a scratch directory. It read like a skill
and was inert. A second instance was already shipped in this repo (skills/session-reflect/SKILL.md
carried a UTF-8 BOM ahead of its `---`). Neither failure has a runtime symptom: nothing errors,
the skill just never loads. Documentation did not prevent either. This checks when it is written.

Register with:  python bin/register_hook.py skill-shape-guard

Contract:
  * Deny  = exit 2 + reason on stderr.   Allow = exit 0.
  * FAIL-OPEN: any internal error -> exit 0. A guard bug must never brick a session.
  * Honors HARNESS_HOOKS_DISABLED=1.
  * Threat model is ACCIDENTS, not adversaries. It reads the resolved path from tool_input.

Two rules:
  1. LOCATION -- anything written into a governed skills root must be a conforming
     <root>/<name>/SKILL.md.
  2. INTENT -- a file that ANNOUNCES itself as a skill (named *-skill.md / skill-*.md, or whose
     content opens with "# Skill:") must be a conforming skill in a skills root, wherever it is
     being written. Rule 2 is the one that catches the original failure, because that essay was
     written to scratch: nowhere near a skills root, so a location-only rule misses it entirely.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parents[1]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# Announces-itself-as-a-skill filename shapes. Deliberately narrow: a bare `*skill*.md` match
# would flag every legitimate document ABOUT skills (a design note, a plan, a "skills.md" index).
# In the repo this came from, that naive pattern hit 35 innocent files and 1 real offender.
#
# A `skill-*.md` prefix rule was here too and was REMOVED: it was added on speculation, and the
# test caught it flagging `SKILL-MODE-PATTERN.md`, an ordinary document. The `-skill.md` suffix
# plus the "# Skill:" content check below cover every failure actually observed, so the prefix
# rule bought nothing and cost a false positive.
_ANNOUNCES = (
    re.compile(r"-skill\.md$", re.I),
)
_ANNOUNCES_CONTENT = re.compile(r"^\s*#\s*Skill\s*:", re.I)


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except Exception:
        return False


def evaluate(path_str: str, content: str | None) -> str | None:
    """Return a denial message, or None to allow. Pure function so tests can drive it directly."""
    import skill_policy as policy

    if not path_str:
        return None
    try:
        p = Path(path_str)
        if not p.is_absolute():
            return None
        p = Path(os.path.normpath(str(p)))
    except Exception:
        return None

    roots = policy.owned_skill_roots()
    if not roots:
        return None

    convention = (
        "\n  An invokable skill is a DIRECTORY, not a file:\n"
        "      <skills-root>/<skill-name>/SKILL.md\n\n"
        "  and SKILL.md must open with these EXACT first bytes (no BOM before them):\n"
        "      ---\n"
        "      name: <skill-name>        # must equal the directory name\n"
        "      description: <when to use this, one sentence>\n"
        "      ---\n\n"
        "  Roots: " + " | ".join(str(r) for r in roots) + "\n"
    )

    # ---- Rule 1: inside a governed skills root ----------------------------------------------
    for root in roots:
        if not _under(p, root):
            continue
        rel = p.relative_to(root)
        if policy.is_support_file(rel.parts[0]):
            return None                      # _index.md, _tests/, etc.
        if len(rel.parts) == 1:
            if rel.name in policy.DOCUMENTED_FLAT_FILES or rel.suffix.lower() != ".md":
                return None
            return (
                f"BLOCKED: loose file in a skills root -> {p}\n\n"
                "  A bare .md here is never loaded by anything. Write it as\n"
                f"      {root / p.stem / 'SKILL.md'}\n"
                f"{convention}\n"
                "  If it is intentionally NOT an invokable skill, either prefix the name with\n"
                "  `_` or add it to bin/skill_policy.py DOCUMENTED_FLAT_FILES with a reason.\n"
            )
        if rel.name == "SKILL.md" and content is not None:
            problems = policy.check_skill_text(content, expected_name=rel.parts[-2])
            if problems:
                joined = "\n".join(f"    - {x}" for x in problems)
                return (
                    f"BLOCKED: this SKILL.md could not be invoked -> {p}\n\n{joined}\n{convention}"
                )
        return None

    # ---- Rule 2: announces itself as a skill, but is not one ---------------------------------
    announces = any(rx.search(str(p)) for rx in _ANNOUNCES)
    if not announces and content is not None and _ANNOUNCES_CONTENT.match(content):
        announces = True
    if announces:
        stem = re.sub(r"-skill$", "", p.stem, flags=re.I)
        stem = re.sub(r"^skill-", "", stem, flags=re.I)
        return (
            "BLOCKED: this looks like an attempt to author a skill outside a skills root ->\n"
            f"  {p}\n\n"
            "  Nothing discovers skills from arbitrary locations, so this file would be inert -\n"
            "  and no error would ever tell you so. If it IS a skill, write it to a skills root,\n"
            f"  e.g.\n      {roots[0] / stem / 'SKILL.md'}\n"
            f"{convention}\n"
            "  If it is a DOCUMENT ABOUT a skill (a design note, a plan, a runbook), that is\n"
            "  fine - just do not name it like a skill. Drop the `-skill` suffix, do not open the\n"
            "  file with '# Skill:', and put it in docs/ instead.\n"
        )

    return None


def main() -> int:
    if os.environ.get("HARNESS_HOOKS_DISABLED") == "1":
        return 0
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if str(data.get("tool_name", "")) not in WRITE_TOOLS:
        return 0
    ti = data.get("tool_input") or {}
    if not isinstance(ti, dict):
        return 0

    path_str = str(ti.get("file_path") or ti.get("notebook_path") or "")
    content = ti.get("content")
    if not isinstance(content, str):
        content = None   # Edit/MultiEdit: path rules still apply, content rules cannot

    msg = evaluate(path_str, content)
    if msg:
        sys.stderr.write(msg)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-open
