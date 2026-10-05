#!/usr/bin/env python3
"""placement-guard.py -- PreToolUse deny-guard for creating a FOLDER in the wrong place.

Register with:  python bin/register_hook.py placement-guard

Refuses a tool call that would create a new top-level directory inside a protected root (this
repository by default, plus any roots in your HARNESS_PLACEMENT_POLICY file) unless that name is
on the root's allowlist. Policy lives in bin/placement_policy.py.

THE GAP IT CLOSES. Guards that only watch the shell catch `mkdir newthing` but not the far more
common route: the Write tool, which creates parent directories implicitly. So this hook reads the
exact path out of Write/Edit/MultiEdit/NotebookEdit (no text matching, no false positives), and
for Bash/PowerShell it parses mkdir / md / New-Item / ni commands (quoted paths included, and
nested `bash -c "..."` commands too).

Contract:
  * Deny = exit 2 + reason on stderr. Allow = exit 0.
  * FAIL-OPEN: any internal error -> exit 0. A guard bug must never brick a session.
  * Off switch: HARNESS_HOOKS_DISABLED=1.
  * Threat model is ACCIDENTS, not adversaries. Only the first word of a command segment counts
    as a command, so a command that merely MENTIONS a path (`grep "mkdir x"`) does not trip it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))              # bin/ for placement_policy
from _hook_common import (  # noqa: E402
    deny, hooks_disabled, read_payload, segments, tool_input, verb,
)

WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
MKDIR_VERBS = {"mkdir", "md", "new-item", "ni"}
# flags whose NEXT token is a value, not a path to create
_VALUE_FLAGS = {"-itemtype", "-type", "-value", "-m", "--mode", "-path", "-literalpath",
                "-name", "-pspath"}


def shell_targets(command: str) -> list[tuple[str, bool]]:
    """[(path, is_dir)] a shell command would create. Relative paths resolve against the cwd.

    Parsed, not pattern-matched on blanked text: `mkdir "/root/new folder"` has a real quoted
    target, while a quoted MENTION (`grep "mkdir x" docs`) is an argument of grep, not a mkdir.
    """
    out: list[tuple[str, bool]] = []
    for seg in segments(command):
        v = verb(seg)
        if v not in MKDIR_VERBS:
            continue
        paths: list[str] = []
        name = None
        item_type = None
        args = seg[1:]
        i = 0
        while i < len(args):
            tok, low = args[i], args[i].lower()
            if low in _VALUE_FLAGS:
                val = args[i + 1] if i + 1 < len(args) else ""
                if low in ("-path", "-literalpath", "-pspath"):
                    paths.extend(p for p in val.split(",") if p)
                elif low == "-name":
                    name = val
                elif low in ("-itemtype", "-type"):
                    item_type = val.lower()
                i += 2
                continue
            if not tok.startswith("-"):
                paths.append(tok)
            i += 1
        if v in ("new-item", "ni"):
            is_dir = bool(item_type and item_type.startswith("dir"))
        else:
            is_dir = True
        if name:
            paths = [os.path.join(p, name) for p in (paths or [os.getcwd()])]
        for p in paths:
            out.append((os.path.join(os.getcwd(), os.path.expanduser(p)), is_dir))
    return out


def main() -> int:
    if hooks_disabled():
        return 0
    data = read_payload()
    if data is None:
        return 0
    try:
        from placement_policy import check_path
    except Exception:
        return 0                                  # fail open

    tool = str(data.get("tool_name", ""))
    ti = tool_input(data)
    targets: list[tuple[str, bool]] = []
    if tool in WRITE_TOOLS:
        for key in ("file_path", "notebook_path"):
            v = ti.get(key)
            if isinstance(v, str) and v.strip():
                targets.append((v, False))
        for e in (ti.get("edits") if isinstance(ti.get("edits"), list) else []):
            if isinstance(e, dict) and isinstance(e.get("file_path"), str):
                targets.append((e["file_path"], False))
    elif tool in SHELL_TOOLS:
        cmd = ti.get("command", "")
        if isinstance(cmd, str):
            targets.extend(shell_targets(cmd))

    for t, is_dir in targets:
        try:
            reason = check_path(t, is_dir=is_dir)
        except Exception:
            continue                              # fail open per target
        if reason:
            return deny(reason)
    return 0


if __name__ == "__main__":
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)                               # fail-open
