#!/usr/bin/env python3
"""harness_metrics.py — the ruler: measured counts for this install, each with the list
of things it counted.

THREE DESIGN RULES, each learned the hard way:

1.  MANIFEST, NOT JUST COUNT.
    Every metric carries the sorted list of things it counted. A count that moves from
    17 to 9 with no manifest is unexplainable after the fact. `--json --stable` output is
    diffable, so a delta names itself.

2.  ENUMERATE, THEN SUBTRACT. NEVER ALLOWLIST BY NAME.
    Anything that must stay complete as the system grows is enumerated, so a new item is
    visible the moment it exists. (An earlier name-fragment allowlist saw 15 of 31 jobs
    and could not see the healer itself.)

3.  UNREADABLE IS REPORTED, NOT SWALLOWED. UNMEASURED IS NOT ZERO.
    Every walk records what it could not read, and a store that could not be measured
    reports `available: false` with a reason — never a count of 0. "Not set up" and
    "empty" are different facts.

    python bin/harness_metrics.py                 # human summary
    python bin/harness_metrics.py --json          # full payload incl. manifests
    python bin/harness_metrics.py --json --stable # deterministic: no timestamps

Read-only. Never prints a credential value — key NAMES only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

unreadable: list[str] = []


def _rel(p: Path) -> str:
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(p).name


def claude_settings_path() -> Path:
    """Same resolution as bin/register_hook.py: CLAUDE_SETTINGS_PATH, else
    $CLAUDE_CONFIG_DIR/settings.json, else ~/.claude/settings.json."""
    override = os.environ.get("CLAUDE_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(cfg).expanduser() if cfg else Path.home() / ".claude") / "settings.json"


def read_settings() -> dict | None:
    p = claude_settings_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8-sig") or "{}")
    except (OSError, ValueError) as exc:
        unreadable.append(f"claude settings.json :: {type(exc).__name__}")
        return None


# ---------------------------------------------------------------- collectors
def scheduled_jobs(query=None) -> dict:
    """Declared REGISTRY vs what the OS scheduler has installed, and both differences."""
    from scheduler import introspect as _intro  # noqa: PLC0415
    from scheduler import jobs as _jobs  # noqa: PLC0415
    declared = sorted(j.id for j in _jobs.REGISTRY)
    installed, why = (query or _intro.query)()
    out = {"declared": {"count": len(declared), "items": declared}, "scheduler": why}
    if installed is None:
        unreadable.append(f"scheduler :: {why}")
        out["installed"] = {"available": False, "reason": why}
        return out
    inst = sorted(installed)
    out["installed"] = {"available": True, "count": len(inst), "items": inst}
    out["installed_not_declared"] = sorted(set(inst) - set(declared))
    out["declared_not_installed"] = sorted(set(declared) - set(inst))
    return out


def bin_scripts() -> dict:
    items = sorted(p.name for p in (ROOT / "bin").iterdir()
                   if p.is_file() and p.suffix in (".py", ".sh", ".ps1"))
    return {"count": len(items), "items": items}


def hooks(settings: dict | None) -> dict:
    scripts = []
    for sub in (ROOT / "bin" / "hooks", ROOT / "claude-brain" / "hooks"):
        if sub.is_dir():
            scripts += [f"{_rel(sub)}/{p.name}" for p in sub.iterdir()
                        if p.is_file() and p.suffix == ".py"]
    out = {"scripts": {"count": len(scripts), "items": sorted(scripts)}}
    if settings is None:
        out["wired_events"] = {"available": False,
                               "reason": f"no readable {claude_settings_path().name}"}
    else:
        ev = sorted((settings.get("hooks") or {}).keys())
        out["wired_events"] = {"available": True, "count": len(ev), "items": ev}
    return out


def brain_db_path() -> tuple[Path | None, str]:
    """Where claude-brain keeps its DB, read from claude-brain/config.yaml. (None, reason)
    when the brain is not set up."""
    cfg = ROOT / "claude-brain" / "config.yaml"
    if not cfg.exists():
        return None, "brain not set up (no claude-brain/config.yaml)"
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"config.yaml unreadable ({type(exc).__name__})"
    m = re.search(r"^\s*local_db_path:\s*[\"']?([^\"'\n#]+)", text, re.M)
    if m:
        return Path(os.path.expanduser(m.group(1).strip())), "config.yaml local_db_path"
    return ROOT / "claude-brain" / "claude-brain.db", "default location"


def claude_brain() -> dict:
    db, why = brain_db_path()
    if db is None:
        return {"available": False, "reason": why}
    if not db.exists():
        return {"available": False, "reason": f"brain DB not found ({why})"}
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=10)
        cur = con.cursor()

        def one(sql: str):
            try:
                return cur.execute(sql).fetchone()[0]
            except sqlite3.Error:
                return None     # None = schema moved; surfaced via schema_ok, never 0

        out = {
            "available": True,
            "sessions": one("SELECT COUNT(*) FROM sys_sessions"),
            "messages": one("SELECT COUNT(*) FROM transcripts"),
            "decisions": one("SELECT COUNT(*) FROM decisions"),
            "facts": one("SELECT COUNT(*) FROM facts"),
            "size_mb": round(db.stat().st_size / 1_048_576, 1),
        }
        out["schema_ok"] = all(out[k] is not None for k in ("sessions", "messages"))
        con.close()
        return out
    except sqlite3.Error as exc:
        unreadable.append(f"brain DB :: {exc}")
        return {"available": False, "reason": f"sqlite error: {exc}"}


def skills() -> dict:
    """Repo skills vs the ones installed in the Claude profile's skills dir."""
    repo_dir = ROOT / "skills"
    repo = sorted(d.name for d in repo_dir.iterdir()
                  if d.is_dir() and not d.name.startswith("_")) if repo_dir.is_dir() else []
    prof_dir = claude_settings_path().parent / "skills"
    out = {"repo": {"count": len(repo), "items": repo}}
    if prof_dir.is_dir():
        prof = sorted(d.name for d in prof_dir.iterdir() if d.is_dir())
        out["profile"] = {"available": True, "count": len(prof), "items": prof,
                          "repo_not_installed": sorted(set(repo) - set(prof))}
    else:
        out["profile"] = {"available": False, "reason": "no skills dir in the Claude profile"}
    return out


def memory_rules() -> dict:
    fb = ROOT / "memory" / "feedback"
    rules = sorted(p.stem for p in fb.glob("*.md")) if fb.is_dir() else []
    idx = ROOT / "memory" / "MEMORY.md"
    return {"rules": {"count": len(rules), "items": rules},
            "index_chars": len(idx.read_text(encoding="utf-8")) if idx.exists() else None}


def credentials() -> dict:
    """Key NAMES in bin/secrets/keyring.env. Never a value, never a value fragment."""
    kr = ROOT / "bin" / "secrets" / "keyring.env"
    if not kr.exists():
        return {"available": False, "reason": "no bin/secrets/keyring.env (not configured)"}
    keys = []
    try:
        for line in kr.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                keys.append(line.split("=", 1)[0].strip())
    except OSError as exc:
        unreadable.append(f"keyring.env :: {type(exc).__name__}")
        return {"available": False, "reason": "keyring.env unreadable"}
    return {"available": True, "count": len(keys), "items": sorted(keys)}


def outcomes() -> dict:
    """Which jobs have reported an outcome, and their last status."""
    import harness_common as hc  # noqa: PLC0415
    d = hc.OUTCOMES_DIR
    if not d.is_dir():
        return {"count": 0, "items": {}, "note": "no job has recorded an outcome yet"}
    items = {}
    for p in sorted(d.glob("*.json")):
        rec = hc.read_outcome(p.stem) or {}
        items[p.stem] = rec.get("status", "unreadable")
    return {"count": len(items), "items": items}


# ---------------------------------------------------------------- assembly
def collect(stable: bool = False, query=None) -> dict:
    unreadable.clear()
    settings = read_settings()
    payload = {
        "scheduled_jobs": scheduled_jobs(query),
        "bin_scripts": bin_scripts(),
        "hooks": hooks(settings),
        "claude_brain": claude_brain(),
        "skills": skills(),
        "memory": memory_rules(),
        "credentials": credentials(),
        "outcomes": outcomes(),
    }
    payload["unreadable"] = sorted(set(unreadable))
    if not stable:
        payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return payload


def _fmt(d: dict, key: str = "count") -> str:
    return str(d.get(key)) if d.get("available", True) else f"n/a ({d.get('reason')})"


def render(m: dict) -> str:
    j = m["scheduled_jobs"]
    inst = j["installed"]
    L = [f"declared jobs          : {j['declared']['count']}",
         f"installed jobs         : {_fmt(inst)}"]
    if inst.get("available"):
        L.append(f"  installed not declared: {j['installed_not_declared'] or 'none'}")
        L.append(f"  declared not installed: {j['declared_not_installed'] or 'none'}")
    L += [f"bin scripts            : {m['bin_scripts']['count']}",
          f"hook scripts / events  : {m['hooks']['scripts']['count']} / "
          f"{_fmt(m['hooks']['wired_events'])}"]
    cb = m["claude_brain"]
    L.append("claude-brain           : " + (
        f"{cb.get('messages')} msgs / {cb.get('sessions')} sessions / {cb.get('size_mb')} MB"
        if cb.get("available") else f"n/a ({cb.get('reason')})"))
    sk = m["skills"]
    L.append(f"skills repo / profile  : {sk['repo']['count']} / {_fmt(sk['profile'])}")
    L.append(f"feedback rules         : {m['memory']['rules']['count']}")
    L.append(f"keyring keys           : {_fmt(m['credentials'])}")
    L.append(f"jobs with outcomes     : {m['outcomes']['count']}")
    if m["unreadable"]:
        L.append(f"UNREADABLE             : {len(m['unreadable'])} -> {m['unreadable']}")
    return "\n".join(L)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Measured counts for this install.")
    ap.add_argument("--json", action="store_true", help="emit the full payload")
    ap.add_argument("--stable", action="store_true", help="omit timestamps (diffable)")
    args = ap.parse_args(argv)
    m = collect(stable=args.stable)
    print(json.dumps(m, indent=2, sort_keys=True) if args.json else render(m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
