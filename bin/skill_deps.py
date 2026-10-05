#!/usr/bin/env python3
"""skill_deps.py — flag skills that encode knowledge which has since changed.

A skill is often a distilled copy of something written down elsewhere: a design doc, a runbook,
a research note, an architecture decision. When that source is revised, the skill keeps teaching
the old version and nothing connects the two — the knowledge moved on and the thing that does the
work did not. This module makes the edge explicit and checkable.

WHAT A DECLARATION LOOKS LIKE
A skill adds two frontmatter keys naming the documents it encodes, relative to a knowledge root
(default: this repo's root; any git repository works):

    knowledge:
      - docs/specs/retry-policy.md
      - docs/research/rate-limits.md
    knowledge_synced: 2026-08-01

`knowledge_synced` is the date the skill was last reconciled against those documents. When a
document's last git commit is AFTER that date, the skill is STALE (orange): it encodes a version
of the knowledge you no longer hold. A declared document that does not exist is RED.

WHY DECLARED RATHER THAN INFERRED
Inferring "which skill depends on which doc" from text similarity would be a guess that looks like
a fact, and it would be wrong quietly. A declaration is a claim someone made and can be checked:
every path is resolved, and an unresolvable one is an error, not a shrug.

Change dates come from `git log` in the knowledge root, so documents must be committed; an
uncommitted or untracked document has no date and is never reported stale.

Read-only. Raises work; never edits a skill.

Usage:
  python bin/skill_deps.py                       # report, worst first
  python bin/skill_deps.py --reverse             # doc -> skills that encode it (blast radius)
  python bin/skill_deps.py --knowledge-root ../handbook --skills-dir skills
  python bin/skill_deps.py --strict              # exit 1 if anything is RED or ORANGE (for CI)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
KNOWLEDGE_ROOT = REPO
FM_RE = re.compile(r"\A(?:﻿)?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
LIST_KEY = "knowledge"
DATE_KEY = "knowledge_synced"


@dataclass
class SkillDep:
    skill: str
    docs: list[str] = field(default_factory=list)
    synced: str | None = None
    missing: list[str] = field(default_factory=list)              # declared, not on disk
    stale: list[tuple[str, str]] = field(default_factory=list)    # (doc, changed_on)

    @property
    def severity(self) -> str:
        if self.missing:
            return "RED"
        if self.stale:
            return "ORANGE"
        return "GREEN"


def _clean(value: str) -> str:
    return value.strip().strip('"').strip("'")


def parse_declaration(text: str) -> tuple[list[str], str | None]:
    """Pull `knowledge:` (a YAML list, block or inline) and `knowledge_synced:` from frontmatter.

    A tiny hand parser rather than a YAML dependency: the shape is fixed, and skill frontmatter
    in the wild is not always strict YAML (unquoted colons in descriptions), which would make a
    real parser reject files this only needs two keys from.
    """
    m = FM_RE.match(text)
    if not m:
        return ([], None)
    docs: list[str] = []
    synced: str | None = None
    in_list = False
    for line in m.group(1).splitlines():
        stripped = line.strip()
        key, sep, rest = stripped.partition(":")
        if sep and key == DATE_KEY:
            synced = _clean(rest) or None
            in_list = False
            continue
        if sep and key == LIST_KEY:
            inline = rest.strip()
            if inline.startswith("["):
                docs += [_clean(p) for p in inline.strip("[]").split(",") if p.strip()]
                in_list = False
            else:
                in_list = True
            continue
        if in_list:
            if stripped.startswith("- "):
                docs.append(_clean(stripped[2:]))
            elif stripped and not line.startswith((" ", "\t")):
                in_list = False
    return ([d for d in docs if d], synced)


def git_dates(root: Path) -> dict[str, str]:
    """{path relative to root: YYYY-MM-DD of its most recent commit}. Empty if not a git repo."""
    out: dict[str, str] = {}
    try:
        r = subprocess.run(["git", "-C", str(root), "log", "--format=%cI", "--name-only",
                            "--no-renames", "--relative"], capture_output=True, text=True,
                           timeout=300, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return out
    if r.returncode != 0:
        return out
    cur = ""
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if _ISO_TS.match(line):
            cur = line[:10]
        elif cur:
            out.setdefault(line, cur)   # log is newest-first: the first date seen is the latest
    return out


def analyse(skills_dir: Path = SKILLS, knowledge_root: Path = KNOWLEDGE_ROOT) -> list[SkillDep]:
    dates = git_dates(knowledge_root)
    out: list[SkillDep] = []
    if not skills_dir.is_dir():
        return out
    for sk in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            text = sk.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        docs, synced = parse_declaration(text)
        if not docs:
            continue
        d = SkillDep(skill=sk.parent.name, docs=docs, synced=synced)
        for rel in docs:
            if not (knowledge_root / rel).exists():
                d.missing.append(rel)
                continue
            changed = dates.get(rel.replace("\\", "/"), "")
            if synced and changed and changed > synced:
                d.stale.append((rel, changed))
        out.append(d)
    return out


def reverse_map(deps: list[SkillDep]) -> dict[str, list[str]]:
    """doc -> skills that encode it: the answer to 'what does changing this doc affect?'"""
    rev: dict[str, list[str]] = {}
    for d in deps:
        for doc in d.docs:
            rev.setdefault(doc, []).append(d.skill)
    return rev


GLYPH = {"RED": "[RED]", "ORANGE": "[ORANGE]", "GREEN": "[GREEN]"}


def render(deps: list[SkillDep]) -> list[str]:
    lines = ["## Skill <- knowledge edge (does what we know reach what we do?)", ""]
    if not deps:
        lines += [f"- No skill declares a `{LIST_KEY}:` dependency, so a document can change "
                  "with no consequence for any skill. Add declarations to the skills that "
                  "distil a document.", ""]
        return lines
    order = {"RED": 0, "ORANGE": 1, "GREEN": 2}
    deps = sorted(deps, key=lambda d: (order[d.severity], d.skill))
    n_stale = sum(1 for d in deps if d.stale)
    lines += [f"- {len(deps)} skill(s) declare a dependency on {len(reverse_map(deps))} "
              f"document(s) · {n_stale} stale", ""]
    for d in deps:
        lines.append(f"- {GLYPH[d.severity]} `{d.skill}` — {len(d.docs)} doc(s), "
                     f"synced {d.synced or 'NEVER'}")
        for m in d.missing:
            lines.append(f"    - declared document does not exist: `{m}`")
        for doc, when in d.stale:
            lines.append(f"    - `{doc}` changed {when}, after this skill was last synced "
                         f"({d.synced}): the skill encodes knowledge that has since been revised")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the skill <- knowledge dependency edge.")
    ap.add_argument("--skills-dir", default=str(SKILLS))
    ap.add_argument("--knowledge-root", default=str(KNOWLEDGE_ROOT))
    ap.add_argument("--reverse", action="store_true", help="show doc -> skills instead")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any RED or ORANGE")
    args = ap.parse_args(argv)
    deps = analyse(Path(args.skills_dir).expanduser(), Path(args.knowledge_root).expanduser())
    if args.reverse:
        rev = reverse_map(deps)
        if not rev:
            print("no declarations")
        for doc, skills in sorted(rev.items()):
            print(f"{doc}\n    -> {', '.join(sorted(skills))}")
        return 0
    print("\n".join(render(deps)))
    if args.strict and any(d.severity != "GREEN" for d in deps):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
