#!/usr/bin/env python3
"""security_watch.py - detect unexpected changes to your Claude Code setup.

Snapshots a SHA-256 manifest of your Claude profile dir(s) (skills, plugins,
agents, commands, settings.json, CLAUDE.md) and reports what was added / changed
/ removed since the last run - so a skill or hook installed by a subagent without
your notice doesn't slip by.

Cross-platform, dependency-free. Register it (e.g. daily) via bin/scheduler, or
run on demand. State + log live under the repo's logs/.

Usage:
    python bin/security_watch.py          # report changes since last run
    python bin/security_watch.py --json   # machine-readable diff
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATE = REPO / "logs" / "security-watch-state.json"

# Files/dirs inside each Claude profile that matter for supply-chain safety.
WATCH_NAMES = ("skills", "plugins", "agents", "commands", "settings.json", "CLAUDE.md")


def profile_dirs() -> list[Path]:
    """All ~/.claude* profile directories on this machine."""
    return sorted(d for d in Path.home().glob(".claude*") if d.is_dir())


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def scan(dirs) -> dict[str, str]:
    """Build {path: sha256} for every watched file under the given profile dirs."""
    manifest: dict[str, str] = {}
    for base in dirs:
        for name in WATCH_NAMES:
            target = base / name
            try:
                if target.is_file():
                    manifest[str(target)] = _sha256(target)
                elif target.is_dir():
                    for f in target.rglob("*"):
                        if f.is_file():
                            manifest[str(f)] = _sha256(f)
            except OSError:
                continue
    return manifest


def diff_manifests(old: dict, new: dict) -> dict:
    """Pure diff: which watched files were added / removed / changed."""
    old_k, new_k = set(old), set(new)
    return {
        "added": sorted(new_k - old_k),
        "removed": sorted(old_k - new_k),
        "changed": sorted(k for k in (old_k & new_k) if old[k] != new[k]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Detect changes to your Claude Code setup.")
    ap.add_argument("--json", action="store_true", help="Emit the diff as JSON.")
    ns = ap.parse_args(argv)

    STATE.parent.mkdir(parents=True, exist_ok=True)
    new = scan(profile_dirs())
    old = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    d = diff_manifests(old, new)
    STATE.write_text(json.dumps(new, indent=2), encoding="utf-8")

    if ns.json:
        print(json.dumps(d, indent=2))
        return 0

    if not old:
        print(f"Baseline recorded: watching {len(new)} files across "
              f"{len(profile_dirs())} profile(s).")
    elif any(d.values()):
        print("Changes to your Claude setup detected since last run:")
        for kind in ("added", "changed", "removed"):
            for f in d[kind]:
                print(f"  [{kind}] {f}")
        print("\nIf you didn't make these, review them (a subagent may have).")
    else:
        print("No changes to your Claude setup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
