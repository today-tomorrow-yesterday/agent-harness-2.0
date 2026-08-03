#!/usr/bin/env python3
"""Register a hook from bin/hooks/ into the Claude Code settings file. Idempotent, cross-platform.

Follows this repo's existing config convention (see bin/configure_claude.py): an env override
wins, otherwise the default under the user's home directory. Nothing here is hardcoded to a
machine, a drive, or a username.

Usage:
    python bin/register_hook.py skill-shape-guard
    python bin/register_hook.py skill-shape-guard --event PreToolUse --matcher "Write|Edit"
    python bin/register_hook.py skill-shape-guard --verify        # report only, change nothing
    python bin/register_hook.py skill-shape-guard --remove

Env:
    CLAUDE_SETTINGS_PATH   full path to settings.json (wins over everything)
    CLAUDE_CONFIG_DIR      profile directory; settings.json is resolved inside it
                           (default: ~/.claude)

Safety properties, learned from doing this by hand:
  * writes to a .tmp, PARSES the temp file, and only then replaces the live config -- a
    half-written settings.json silently disables every hook at once
  * preserves the file's existing BOM state and never introduces one
  * idempotent: an already-registered command is left alone
  * refuses to register a hook script that does not exist, which would fail open forever
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK_DIR = ROOT / "bin" / "hooks"
DEFAULT_MATCHER = "Write|Edit|MultiEdit|NotebookEdit"


def settings_path() -> Path:
    override = os.environ.get("CLAUDE_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    cfg_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(cfg_dir).expanduser() if cfg_dir else Path.home() / ".claude"
    return base / "settings.json"


def read_settings(path: Path) -> tuple[dict, bool]:
    """Return (data, had_bom). Missing or empty file -> ({}, False)."""
    if not path.exists():
        return {}, False
    raw = path.read_bytes()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    return (json.loads(text) if text.strip() else {}), had_bom


def write_settings(path: Path, data: dict, had_bom: bool) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    payload = (b"\xef\xbb\xbf" if had_bom else b"") + text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    json.loads(tmp.read_bytes().decode("utf-8-sig"))   # validate BEFORE replacing the live file
    shutil.move(str(tmp), str(path))


def commands(data: dict, event: str) -> list[str]:
    return [
        h.get("command", "")
        for entry in data.get("hooks", {}).get(event, [])
        for h in entry.get("hooks", [])
    ]


def hook_command(name: str) -> str:
    """A portable command line. Uses the running interpreter and a POSIX-style repo path so the
    same settings.json works from Git Bash, WSL, PowerShell and cmd."""
    script = (HOOK_DIR / f"{name}.py").as_posix()
    return f'"{sys.executable}" "{script}"'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("hook", help="hook filename stem under bin/hooks (e.g. skill-shape-guard)")
    ap.add_argument("--event", default="PreToolUse")
    ap.add_argument("--matcher", default=DEFAULT_MATCHER)
    ap.add_argument("--timeout", type=int, default=10)
    ap.add_argument("--verify", action="store_true", help="report only, change nothing")
    ap.add_argument("--remove", action="store_true", help="unregister instead")
    args = ap.parse_args()

    script = HOOK_DIR / f"{args.hook}.py"
    if not script.is_file():
        print(f"ERROR: no such hook: {script}", file=sys.stderr)
        return 1

    path = settings_path()
    data, had_bom = read_settings(path)
    command = hook_command(args.hook)

    if args.remove:
        events = data.get("hooks", {})
        before = len(commands(data, args.event))
        for entry in list(events.get(args.event, [])):
            entry["hooks"] = [h for h in entry.get("hooks", []) if args.hook not in h.get("command", "")]
        events[args.event] = [e for e in events.get(args.event, []) if e.get("hooks")]
        write_settings(path, data, had_bom)
        print(f"  removed ({before} -> {len(commands(data, args.event))} {args.event} hooks)")
        return 0

    if not args.verify:
        if any(args.hook in c for c in commands(data, args.event)):
            print(f"  already registered in {path} - no change")
        else:
            entry = {
                "matcher": args.matcher,
                "hooks": [{"type": "command", "command": command, "timeout": args.timeout}],
            }
            data.setdefault("hooks", {}).setdefault(args.event, []).append(entry)
            write_settings(path, data, had_bom)
            print(f"  registered in {path} (bom_preserved={had_bom})")

    data, _ = read_settings(path)
    hits = [c for c in commands(data, args.event) if args.hook in c]
    total = len(commands(data, args.event))
    print(f"  verify: {path}  {args.event} hooks={total}  {args.hook}={len(hits)}")
    return 0 if len(hits) == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
