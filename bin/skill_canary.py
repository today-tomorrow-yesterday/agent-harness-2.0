#!/usr/bin/env python3
"""skill_canary.py — a CANARY-BEFORE-PROMOTE gate for skills.

The problem it closes: a skill edited in this repo (`skills/<name>/`) gets copied into the
Claude profile's skills dir and goes live with no validation and no rollback. One broken
frontmatter block or a syntax-broken helper script silently degrades every session that
loads that profile — a malformed skill never errors, it just never loads.

Flow for one skill:
  (a) SNAPSHOT the profile's current copy to forge/skill-versions/<skill>/<utc-fingerprint>/
      BEFORE any overwrite, with a manifest recording which profiles had it.
  (b) SMOKE-TEST the repo copy: bin/skill_policy.py's definition of an invokable SKILL.md
      (frontmatter opens the file, name + description present, name matches the dir, no
      byte-order mark), plus every co-located or referenced helper .py compiles.
  (c) APPEND a CanaryStatus record to forge/evolution.jsonl:
      {..., "canary": "Passed"|"Failed", "checks": [...], "crash": {...}|null}.
  (d) Passed -> exit 0 (caller may promote). Failed -> exit 1, profiles untouched.

Profiles: the skills dir of the Claude config in use — $CLAUDE_CONFIG_DIR/skills, else
~/.claude/skills. Pass --profile DIR (repeatable) to gate several profiles at once.

    python bin/skill_canary.py <skill>              # snapshot + smoke-test + log (gate only)
    python bin/skill_canary.py --promote <skill>    # gate, and on Pass copy repo -> profiles
    python bin/skill_canary.py --rollback <skill>   # restore the latest snapshot
    python bin/skill_canary.py --list <skill>       # list snapshots
    python bin/skill_canary.py --check-all          # smoke-test every repo skill; no writes

Exit codes: 0 = Passed / rollback ok · 1 = smoke-test Failed · 2 = usage / not found.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import skill_policy  # noqa: E402

CANONICAL_SKILLS = ROOT / "skills"
SNAPSHOT_ROOT = ROOT / "forge" / "skill-versions"
EVOLUTION_LOG = ROOT / "forge" / "evolution.jsonl"
PY_REF_RE = re.compile(r"[\w./\\-]+\.py\b")


def default_profiles() -> dict[str, Path]:
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(cfg).expanduser() if cfg else Path.home() / ".claude"
    return {"claude": base / "skills"}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(canonical_dir: Path) -> str:
    """UTC stamp + short content hash: sortable and collision-resistant."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md = canonical_dir / "SKILL.md"
    h = hashlib.sha256(md.read_bytes()).hexdigest()[:8] if md.exists() else "nofile00"
    return f"{stamp}-{h}"


# ---------------------------------------------------------------------------- smoke test
def _helper_scripts(canonical_dir: Path, skill_text: str) -> list[Path]:
    """Every helper .py that ships with, or is referenced (relatively) by, the skill."""
    found: dict[str, Path] = {}
    for p in canonical_dir.rglob("*.py"):
        if "__pycache__" not in p.parts:
            found[str(p.resolve())] = p
    for token in PY_REF_RE.findall(skill_text):
        for c in (canonical_dir / token, ROOT / token):
            try:
                if c.is_file():
                    found[str(c.resolve())] = c
            except OSError:
                pass
    return list(found.values())


def _crash(checks: list[dict]) -> dict | None:
    first = next((c for c in checks if not c["ok"]), None)
    if first is None:
        return None
    return {"check": first["name"], "message": first["detail"],
            "failed_checks": [c["name"] for c in checks if not c["ok"]]}


def smoke_test(skill: str, canonical_root: Path | None = None) -> tuple[bool, list[dict], dict | None]:
    """(passed, checks, crash). checks = [{name, ok, detail}]."""
    canonical_dir = (canonical_root or CANONICAL_SKILLS) / skill
    md = canonical_dir / "SKILL.md"
    checks: list[dict] = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        return ok

    if not add("canonical_dir_exists", canonical_dir.is_dir(), canonical_dir.name):
        return False, checks, _crash(checks)
    if not add("skill_md_exists", md.is_file(), "SKILL.md"):
        return False, checks, _crash(checks)
    raw = md.read_bytes()
    problems = skill_policy.check_skill_bytes(raw, expected_name=skill)
    add("skill_policy", not problems, "; ".join(problems)[:300] if problems else "invokable")
    text = raw.decode("utf-8", errors="replace")
    scripts = _helper_scripts(canonical_dir, text)
    if not scripts:
        add("helper_scripts_compile", True, "no helper .py")
    for sp in scripts:
        try:   # builtin compile(): syntax check without writing bytecode
            compile(sp.read_bytes(), str(sp), "exec")
            add(f"compile:{sp.name}", True, sp.name)
        except (SyntaxError, ValueError, UnicodeDecodeError, OSError) as e:
            add(f"compile:{sp.name}", False, f"{type(e).__name__}: {e}"[:200])
    passed = all(c["ok"] for c in checks)
    return passed, checks, _crash(checks)


# ---------------------------------------------------------------------------- snapshots
def snapshot(skill: str, profiles: dict[str, Path]) -> Path:
    snap_dir = SNAPSHOT_ROOT / skill / _fingerprint(CANONICAL_SKILLS / skill)
    snap_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"skill": skill, "ts": _utcnow_iso(), "profiles": {}}
    for tag, base in profiles.items():
        src = base / skill
        if src.exists():
            shutil.copytree(src, snap_dir / tag, dirs_exist_ok=True)
        manifest["profiles"][tag] = {"existed": src.exists()}
    (snap_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                             encoding="utf-8")
    return snap_dir


def latest_snapshot(skill: str) -> Path | None:
    d = SNAPSHOT_ROOT / skill
    if not d.is_dir():
        return None
    snaps = sorted((s for s in d.iterdir() if (s / "_manifest.json").exists()),
                   key=lambda s: s.name)
    return snaps[-1] if snaps else None


def log_evolution(skill: str, status: str, checks: list[dict], crash: dict | None,
                  snap_dir: Path | None, session: str, extra: str = "") -> None:
    n_ok = sum(1 for c in checks if c["ok"])
    rec = {
        "ts": _utcnow_iso(), "strategy": "canary", "asset": f"skills/{skill}/SKILL.md",
        "what": f"skill-canary {status} on '{skill}' ({n_ok}/{len(checks)} checks)"
                + (f" — {extra}" if extra else ""),
        "why": "validate a skill edit before it goes live in the Claude profile",
        "session": session, "canary": status, "checks": checks, "crash": crash,
        "snapshot": snap_dir.relative_to(ROOT).as_posix() if snap_dir else None,
    }
    EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EVOLUTION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def promote(skill: str, profiles: dict[str, Path]) -> None:
    """Copy the whole repo skill dir into each profile (replacing the old copy)."""
    src = CANONICAL_SKILLS / skill
    for tag, base in profiles.items():
        dest = base / skill
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
        print(f"  [{tag}] promoted -> {dest}")


def rollback(skill: str, profiles: dict[str, Path]) -> int:
    snap = latest_snapshot(skill)
    if snap is None:
        print(f"ERROR: no snapshot for '{skill}'", file=sys.stderr)
        return 2
    manifest = json.loads((snap / "_manifest.json").read_text(encoding="utf-8"))
    print(f"Rolling back '{skill}' from snapshot {snap.name} (taken {manifest['ts']})")
    for tag, base in profiles.items():
        info = manifest["profiles"].get(tag)
        target = base / skill
        if info is None:
            print(f"  [{tag}] not in this snapshot — left untouched")
            continue
        if target.exists():
            shutil.rmtree(target)
        if info.get("existed"):
            shutil.copytree(snap / tag, target)
            print(f"  [{tag}] restored")
        else:
            print(f"  [{tag}] removed (absent when the snapshot was taken)")
    log_evolution(skill, "Rollback", [], None, snap, "skill-canary",
                  extra=f"restored snapshot {snap.name}")
    return 0


def run_gate(skill: str, profiles: dict[str, Path], do_promote: bool, session: str) -> int:
    if not (CANONICAL_SKILLS / skill).is_dir():
        print(f"ERROR: no skill named '{skill}' under skills/", file=sys.stderr)
        return 2
    snap_dir = snapshot(skill, profiles)
    print(f"Snapshot: {snap_dir.relative_to(ROOT).as_posix()}")
    passed, checks, crash = smoke_test(skill)
    status = "Passed" if passed else "Failed"
    print(f"Canary: {status}")
    for c in checks:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
    log_evolution(skill, status, checks, crash, snap_dir, session,
                  extra="promoted" if (passed and do_promote) else
                  "gate-only" if passed else "profiles untouched")
    if not passed:
        print("Profiles left UNTOUCHED (smoke-test failed).", file=sys.stderr)
        return 1
    if do_promote:
        promote(skill, profiles)
    else:
        print(f"Gate passed. Promote with: python bin/skill_canary.py --promote {skill}")
    return 0


def check_all(canonical_root: Path | None = None) -> int:
    """Smoke-test every repo skill. Read-only (no snapshot, no log) — for release gates."""
    root = canonical_root or CANONICAL_SKILLS
    names = sorted(d.name for d in root.iterdir()
                   if d.is_dir() and not skill_policy.is_support_file(d.name)) \
        if root.is_dir() else []
    if not names:
        print("no skills found — nothing to check (not a pass)")
        return 2
    failed = []
    for n in names:
        ok, checks, crash = smoke_test(n, root)
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}" + ("" if ok else f" — {crash['check']}: "
                                                          f"{crash['message'][:120]}"))
        if not ok:
            failed.append(n)
    print(f"{len(names) - len(failed)}/{len(names)} skills pass the canary smoke-test")
    return 1 if failed else 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Canary-before-promote gate for repo skills.")
    ap.add_argument("skill", nargs="?", help="skill name under skills/")
    ap.add_argument("--promote", action="store_true", help="on Pass, copy repo -> profiles")
    ap.add_argument("--rollback", metavar="SKILL", help="restore the latest snapshot")
    ap.add_argument("--list", metavar="SKILL", dest="list_skill", help="list snapshots")
    ap.add_argument("--check-all", action="store_true",
                    help="smoke-test every repo skill; writes nothing")
    ap.add_argument("--profile", action="append", metavar="DIR",
                    help="a profile skills dir to gate (repeatable; default: the Claude "
                         "config's skills dir)")
    ap.add_argument("--session", default="skill-canary", help="session tag for the log")
    args = ap.parse_args(argv)
    profiles = ({f"profile{i}": Path(p).expanduser() for i, p in enumerate(args.profile)}
                if args.profile else default_profiles())

    if args.check_all:
        return check_all()
    if args.rollback:
        return rollback(args.rollback, profiles)
    if args.list_skill:
        d = SNAPSHOT_ROOT / args.list_skill
        for s in sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []:
            print(s)
        if not d.is_dir():
            print(f"(no snapshots for '{args.list_skill}')")
        return 0
    if not args.skill:
        ap.error("a skill name is required (or --check-all / --rollback / --list)")
    return run_gate(args.skill, profiles, args.promote, args.session)


if __name__ == "__main__":
    sys.exit(main())
