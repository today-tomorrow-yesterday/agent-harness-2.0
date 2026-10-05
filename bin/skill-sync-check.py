#!/usr/bin/env python3
"""skill-sync-check.py — read-only drift report for skills installed in several Claude profiles.

Installed skills are COPIES. Once you run more than one profile (two subscriptions, a work and a
personal config dir, a Codex or Gemini seat), a skill edited in one place is still the old version
in the others, and nothing tells you. This script tells you.

Read-only. Never copies, writes or deletes; fixing drift is a deliberate step
(`python bin/sync-agent-tools.py`), not something a checker should do behind your back.

Checks, across every profile:
  1. MISSING   a skill present in some profiles but not others.
  2. DIVERGED  a skill present in several profiles with a different file set or content.
  3. STALE     a profile copy that differs from the canonical source in this repo's skills/
               (the edit was made, the sync was not).
  4. UNREACHABLE  a skill that exists canonically but is installed in NO profile.

Check 4 is the one a profile-vs-profile comparison cannot see: a skill missing from EVERY
profile is absent from both sides of every diff, so it reads as "in sync" while being impossible
to invoke from any session. An earlier version of this checker had exactly that blind spot and
reported green while several authored skills were unreachable. Comparing against the canonical
source is what makes "in sync" mean something.

Profiles come from (first match wins):
  --profile NAME=PATH (repeatable)  a skills dir per profile
  the manifest (config/agent-tools.yaml): every enabled claude-code seat's <config_dir>/skills,
      plus codex/gemini seats' skills_dir; `not_installed_by_design` is read from it too
  otherwise ~/.claude/skills alone

Usage:  python bin/skill-sync-check.py [--json] [--canonical DIR] [--profile NAME=PATH ...]
Exit:   0 in sync · 1 drift found · 2 a profile directory does not exist
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANONICAL = REPO / "skills"
JUNK = {"__pycache__", ".git", "node_modules", "captures", ".DS_Store"}

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def _sync_module():
    """sync-agent-tools.py owns manifest loading; hyphenated, so load it by path."""
    spec = importlib.util.spec_from_file_location(
        "sync_agent_tools", str(Path(__file__).resolve().parent / "sync-agent-tools.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def skill_fingerprint(skill_dir: Path, ignore: frozenset = frozenset()) -> dict[str, str]:
    """{relative path: sha256} for every real file in a skill, skipping caches and local installs.
    `ignore` names relative paths a seat legitimately adds (e.g. a Codex sidecar)."""
    fp: dict[str, str] = {}
    if not skill_dir.is_dir():
        return fp
    for p in sorted(skill_dir.rglob("*")):
        rel_parts = p.relative_to(skill_dir).parts
        if not p.is_file() or any(part in JUNK for part in rel_parts):
            continue
        if p.suffix in (".pyc", ".pyo") or ".bak" in p.name:
            continue
        rel = "/".join(rel_parts)
        if rel not in ignore:
            fp[rel] = file_hash(p)
    return fp


def list_skills(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {p.name for p in root.iterdir()
            if (p.is_dir() or p.is_symlink()) and not p.name.startswith((".", "_"))}


def diff_fingerprints(a: dict, b: dict) -> dict:
    return {
        "only_in_first": sorted(set(a) - set(b)),
        "only_in_second": sorted(set(b) - set(a)),
        "changed": sorted(f for f in set(a) & set(b) if a[f] != b[f]),
    }


SIDECARS = frozenset({"agents/openai.yaml"})


def analyse(profiles: dict[str, Path], canonical: Path | None,
            not_installed_by_design: dict[str, str] | None = None) -> dict:
    nibd = dict(not_installed_by_design or {})
    installed = {name: list_skills(root) for name, root in profiles.items()}
    every = set().union(*installed.values()) if installed else set()
    canonical_skills = list_skills(canonical) if canonical and canonical.is_dir() else set()

    missing = []
    for skill in sorted(every):
        have = sorted(n for n, s in installed.items() if skill in s)
        lacking = sorted(n for n, s in installed.items() if skill not in s)
        if lacking:
            missing.append({"skill": skill, "in": have, "missing_from": lacking})

    diverged = []
    for skill in sorted(every):
        holders = [n for n, s in installed.items() if skill in s]
        if len(holders) < 2:
            continue
        first = holders[0]
        fp0 = skill_fingerprint(profiles[first] / skill, SIDECARS)
        for other in holders[1:]:
            fp = skill_fingerprint(profiles[other] / skill, SIDECARS)
            if fp != fp0:
                diverged.append({"skill": skill, "between": [first, other],
                                 **diff_fingerprints(fp0, fp)})

    stale = []
    for skill in sorted(every & canonical_skills):
        src = skill_fingerprint(canonical / skill)
        for name, skills in installed.items():
            if skill in skills:
                fp = skill_fingerprint(profiles[name] / skill, SIDECARS)
                if fp != src:
                    stale.append({"skill": skill, "profile": name, **diff_fingerprints(src, fp)})

    unreachable = sorted(canonical_skills - every - set(nibd))
    orphaned = sorted(every - canonical_skills) if canonical_skills else []

    return {
        "profiles": {n: str(p) for n, p in profiles.items()},
        "canonical": str(canonical) if canonical else None,
        "canonical_count": len(canonical_skills),
        "missing": missing,
        "diverged": diverged,
        "stale_vs_canonical": stale,
        "unreachable": unreachable,
        "not_canonical": orphaned,
        "not_installed_by_design": sorted(nibd),
        "in_sync": not (missing or diverged or stale or unreachable),
    }


def render(r: dict) -> str:
    if r["in_sync"]:
        return (f"In sync: {len(r['profiles'])} profile(s) agree, every installed copy matches "
                f"the canonical source, and all {r['canonical_count']} canonical skills are "
                "reachable.")
    out = ["Skill drift detected.", ""]
    if r["unreachable"]:
        out.append(f"[RED] Authored but installed in NO profile, unreachable "
                   f"({len(r['unreachable'])}):")
        out += [f"  - {s}" for s in r["unreachable"]]
        out += ["  Fix: add it to the manifest and run sync-agent-tools.py, or record it under",
                "  not_installed_by_design with a reason if that is intentional.", ""]
    if r["stale_vs_canonical"]:
        out.append(f"[ORANGE] Installed copy differs from the canonical source "
                   f"({len(r['stale_vs_canonical'])}):")
        for d in r["stale_vs_canonical"]:
            out.append(f"  - {d['skill']} in {d['profile']}")
            if d["changed"]:
                out.append(f"      changed: {', '.join(d['changed'])}")
            if d["only_in_first"]:
                out.append(f"      missing from the copy: {', '.join(d['only_in_first'])}")
            if d["only_in_second"]:
                out.append(f"      extra in the copy: {', '.join(d['only_in_second'])}")
        out.append("")
    if r["missing"]:
        out.append(f"[YELLOW] Present in some profiles only ({len(r['missing'])}):")
        out += [f"  - {m['skill']}: in {', '.join(m['in'])}; missing from "
                f"{', '.join(m['missing_from'])}" for m in r["missing"]]
        out.append("")
    if r["diverged"]:
        out.append(f"[YELLOW] Same skill, different content between profiles "
                   f"({len(r['diverged'])}):")
        for d in r["diverged"]:
            a, b = d["between"]
            out.append(f"  - {d['skill']} ({a} vs {b})")
            if d["changed"]:
                out.append(f"      changed: {', '.join(d['changed'])}")
            if d["only_in_first"]:
                out.append(f"      only in {a}: {', '.join(d['only_in_first'])}")
            if d["only_in_second"]:
                out.append(f"      only in {b}: {', '.join(d['only_in_second'])}")
        out.append("")
    if r["not_canonical"]:
        out.append(f"[INFO] Installed but not in this repo's skills/ ({len(r['not_canonical'])})"
                   " — third-party, or authored elsewhere:")
        out += [f"  - {s}" for s in r["not_canonical"]]
    return "\n".join(out).rstrip()


def profiles_from_manifest(manifest: dict, resolve) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for name, seat in (manifest.get("seats") or {}).items():
        if seat.get("enabled", True) is False:
            continue
        if seat.get("kind") == "claude-code" and seat.get("config_dir"):
            out[name] = resolve(seat["config_dir"]) / "skills"
        elif seat.get("skills_dir"):
            out[name] = resolve(seat["skills_dir"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only skill drift report across profiles.")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--canonical", default=str(CANONICAL), help="canonical skills root")
    ap.add_argument("--manifest", help="manifest path (default: config/agent-tools.yaml)")
    ap.add_argument("--profile", action="append", default=[], metavar="NAME=PATH",
                    help="a profile's skills dir; repeat for each profile")
    args = ap.parse_args(argv)

    nibd: dict[str, str] = {}
    profiles: dict[str, Path] = {}
    if args.profile:
        for item in args.profile:
            name, _, path = item.partition("=")
            if not path:
                ap.error(f"--profile expects NAME=PATH, got {item!r}")
            profiles[name] = Path(path).expanduser()
    else:
        sat = _sync_module()
        manifest_path = Path(args.manifest).expanduser() if args.manifest else sat.DEFAULT_MANIFEST
        if manifest_path.is_file():
            manifest = sat.load_manifest(manifest_path)
            profiles = profiles_from_manifest(manifest, sat.resolve_path)
            nibd = manifest.get("not_installed_by_design") or {}
        if not profiles:
            profiles = {"default": Path.home() / ".claude" / "skills"}

    absent = [f"{n}: {p}" for n, p in profiles.items() if not p.is_dir()]
    if absent:
        print("Cannot find one or more profile skill directories:", file=sys.stderr)
        for a in absent:
            print(f"  - {a}", file=sys.stderr)
        return 2

    canonical = Path(args.canonical).expanduser() if args.canonical else None
    result = analyse(profiles, canonical, nibd)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0 if result["in_sync"] else 1


if __name__ == "__main__":
    sys.exit(main())
