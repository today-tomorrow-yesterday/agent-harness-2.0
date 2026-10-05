#!/usr/bin/env python3
"""Register hooks from bin/hooks/ into the Claude Code settings file. Idempotent, cross-platform.

Follows this repo's existing config convention (see bin/configure_claude.py): an env override
wins, otherwise the default under the user's home directory. Nothing here is hardcoded to a
machine, a drive, or a username. Works the same on Windows, macOS and Linux.

Each hook knows which events and tool matchers it needs (CATALOG below), so one command wires it
completely -- design-gate, for instance, needs PreToolUse AND Stop.

Usage:
    python bin/register_hook.py --list                      # what exists, what is registered
    python bin/register_hook.py pre-tool-guard               # register one hook
    python bin/register_hook.py pre-tool-guard safety-queue  # several
    python bin/register_hook.py --all                        # every hook in the catalog
    python bin/register_hook.py pre-tool-guard --verify      # report only, change nothing
    python bin/register_hook.py pre-tool-guard --remove      # unregister
    python bin/register_hook.py design-gate --hook-arg=--build-skills=frontend-design
                                    # pass arguments through to the hook's command line
    python bin/register_hook.py skill-shape-guard --event PreToolUse --matcher "Write|Edit"
                                    # override the catalog: one event, one matcher

Env:
    CLAUDE_SETTINGS_PATH   full path to settings.json (wins over everything)
    CLAUDE_CONFIG_DIR      profile directory; settings.json is resolved inside it
                           (default: ~/.claude)

Safety properties, learned from doing this by hand:
  * writes to a .tmp, PARSES the temp file, and only then replaces the live config -- a
    half-written settings.json silently disables every hook at once
  * preserves the file's existing BOM state and never introduces one
  * idempotent: re-running leaves a correct entry alone, and repairs one whose matcher, timeout
    or command differs from what was asked (catalog matcher, --timeout, --hook-arg). A re-run
    WITHOUT --hook-arg keeps the arguments given earlier; without --timeout keeps the timeout
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

# hook -> [(event, matcher or None)]. None = the event takes no matcher (Stop, UserPromptSubmit).
CATALOG: dict[str, list[tuple[str, str | None]]] = {
    "skill-shape-guard": [("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit")],
    "pre-tool-guard":    [("PreToolUse", "Bash|PowerShell")],
    "safety-queue":      [("PreToolUse", "Bash|PowerShell")],
    "placement-guard":   [("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell")],
    "design-gate":       [("PreToolUse", "Skill|Write|Edit|MultiEdit"), ("Stop", None)],
    "capability-gate":   [("PreToolUse", "Read|Grep|Glob|Bash|PowerShell|Write|Edit|MultiEdit"),
                          ("UserPromptSubmit", None)],
}


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


def marker(name: str) -> str:
    """What identifies this hook inside a registered command line."""
    return f"hooks/{name}.py"


def _quote(arg: str) -> str:
    return '"' + arg.replace('"', '\\"') + '"'


def hook_command(name: str, hook_args: list[str] | None = None) -> str:
    """A portable command line. Uses the running interpreter and a POSIX-style repo path so the
    same settings.json works from Git Bash, WSL, PowerShell and cmd."""
    script = (HOOK_DIR / f"{name}.py").as_posix()
    parts = [_quote(sys.executable), _quote(script)] + [_quote(a) for a in (hook_args or [])]
    return " ".join(parts)


def available_hooks() -> list[str]:
    """Hook scripts on disk. Hooks are hyphenated; underscore modules are helpers/data."""
    return sorted(p.stem for p in HOOK_DIR.glob("*-*.py"))


DEFAULT_TIMEOUT = 10


def register(data: dict, name: str, event: str, matcher: str | None, command: str | None,
             timeout: int | None) -> str:
    """Make `event` hold exactly one registration of `name`, with this matcher, command and
    timeout. Mutates `data`; returns 'added' | 'updated' | 'unchanged'.

    `command=None` keeps the existing command line (so a plain re-run does not wipe arguments
    given earlier with --hook-arg); `timeout=None` keeps the existing timeout. The MATCHER is
    always enforced: re-running is how a narrowed or edited matcher is restored to the catalog's.
    An entry is only 'unchanged' if matcher, command and timeout all already agree.
    """
    mk = marker(name)
    entries = data.get("hooks", {}).get(event, [])
    found = [(e, h) for e in entries for h in e.get("hooks", []) if mk in h.get("command", "")]
    want_cmd = command or (found[0][1].get("command") if found else hook_command(name))
    want_timeout = timeout if timeout is not None else (
        found[0][1].get("timeout", DEFAULT_TIMEOUT) if found else DEFAULT_TIMEOUT)

    if len(found) == 1:
        entry, h = found[0]
        if entry.get("matcher") == matcher and h.get("command") == want_cmd \
                and h.get("timeout") == want_timeout:
            return "unchanged"

    # Drop every existing registration of this hook in this event (an entry may be shared with
    # other hooks, so only our hook leaves it), then add one correct entry.
    if found:
        unregister(data, name, event)
    new: dict = {"hooks": [{"type": "command", "command": want_cmd, "timeout": want_timeout}]}
    if matcher is not None:
        new = {"matcher": matcher, **new}
    data.setdefault("hooks", {}).setdefault(event, []).append(new)
    return "updated" if found else "added"


def unregister(data: dict, name: str, event: str) -> int:
    """Remove this hook from `event`. Returns how many commands were removed."""
    events = data.get("hooks", {})
    if event not in events:
        return 0
    mk = marker(name)
    before = len(commands(data, event))
    for entry in events[event]:
        entry["hooks"] = [h for h in entry.get("hooks", []) if mk not in h.get("command", "")]
    events[event] = [e for e in events[event] if e.get("hooks")]
    if not events[event]:
        del events[event]
    return before - len(commands(data, event))


def count(data: dict, name: str, event: str) -> int:
    return sum(1 for c in commands(data, event) if marker(name) in c)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Register bin/hooks/ hooks into Claude Code settings.")
    ap.add_argument("hooks", nargs="*", help="hook filename stem(s) under bin/hooks")
    ap.add_argument("--all", action="store_true", help="every hook in the catalog")
    ap.add_argument("--list", action="store_true", help="show hooks and their registration state")
    ap.add_argument("--event", help="override the catalog: register on this one event")
    ap.add_argument("--matcher", help="override the catalog's tool matcher")
    ap.add_argument("--timeout", type=int, default=None,
                    help=f"seconds (default {DEFAULT_TIMEOUT} for a new entry; an existing "
                         "entry keeps its timeout unless this is given)")
    ap.add_argument("--hook-arg", action="append", default=[],
                    help="argument appended to the hook's command line (repeatable; use the "
                         "--hook-arg=VALUE form when VALUE starts with -)")
    ap.add_argument("--verify", action="store_true", help="report only, change nothing")
    ap.add_argument("--remove", action="store_true", help="unregister instead")
    args = ap.parse_args(argv)

    path = settings_path()
    data, had_bom = read_settings(path)

    if args.list:
        print(f"settings: {path}")
        for name in available_hooks():
            plan = CATALOG.get(name, [])
            state = ", ".join(f"{ev}={'yes' if count(data, name, ev) else 'no'}" for ev, _ in plan)
            print(f"  {name:<20} {state or '(not in catalog)'}")
        return 0

    names = list(CATALOG) if args.all else args.hooks
    if not names:
        ap.error("name at least one hook, or use --all / --list")

    rc = 0
    changed = False
    for name in names:
        script = HOOK_DIR / f"{name}.py"
        if not script.is_file():
            print(f"ERROR: no such hook: {script}", file=sys.stderr)
            return 1
        if args.event:
            plan = [(args.event, args.matcher if args.matcher is not None else DEFAULT_MATCHER)]
        else:
            plan = CATALOG.get(name) or [("PreToolUse", args.matcher or DEFAULT_MATCHER)]
            if args.matcher is not None:
                plan = [(ev, args.matcher if m is not None else None) for ev, m in plan]
        # None = keep the arguments an earlier --hook-arg registration gave this hook
        command = hook_command(name, args.hook_arg) if args.hook_arg else None

        for event, matcher in plan:
            if args.remove:
                n = unregister(data, name, event)
                changed = changed or n > 0
                print(f"  {name}: removed {n} from {event}")
            elif not args.verify:
                result = register(data, name, event, matcher, command, args.timeout)
                changed = changed or result != "unchanged"
                print(f"  {name}: {event} {result}")

        if name == "design-gate" and not args.remove and not args.verify and \
                not any("--build-skills=" in c for ev, _m in plan
                        for c in commands(data, ev) if marker(name) in c) and \
                not os.environ.get("DESIGN_GATE_BUILD_SKILLS"):
            print("  NOTE: design-gate has no --build-skills configured, so it will not enforce "
                  "anything until you set them (see docs/hooks.md).")

    if changed:
        write_settings(path, data, had_bom)
        print(f"  wrote {path} (bom_preserved={had_bom})")

    data, _ = read_settings(path)
    for name in names:
        plan = [(args.event, None)] if args.event else (CATALOG.get(name) or [("PreToolUse", None)])
        for event, _m in plan:
            n = count(data, name, event)
            ok = (n == 0) if args.remove else (n == 1)
            rc = rc if ok else 1
            print(f"  verify: {name} {event}={n}{'' if ok else '  <-- MISMATCH'}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
