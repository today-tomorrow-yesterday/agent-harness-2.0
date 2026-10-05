#!/usr/bin/env python3
"""placement-guard.py -- PreToolUse deny-guard for creating a FOLDER in the wrong place.

Register with:  python bin/register_hook.py placement-guard

Refuses a tool call that would create a new top-level directory inside a protected root (this
repository by default, plus any roots in your HARNESS_PLACEMENT_POLICY file) unless that name is
on the root's allowlist. Policy lives in bin/placement_policy.py.

THE GAP IT CLOSES. Guards that only watch the shell catch `mkdir newthing` but not the far more
common route: the Write tool, which creates parent directories implicitly. So this hook reads the
exact path out of Write/Edit/MultiEdit/NotebookEdit (no text matching, no false positives), and
for Bash/PowerShell it text-matches mkdir / md / New-Item / ni, which is fuzzier by nature and
deliberately conservative.

Contract:
  * Deny = exit 2 + reason on stderr. Allow = exit 0.
  * FAIL-OPEN: any internal error -> exit 0. A guard bug must never brick a session.
  * Off switch: HARNESS_HOOKS_DISABLED=1.
  * Threat model is ACCIDENTS, not adversaries. Quoted text in a shell command is blanked first,
    so a command that merely MENTIONS a path does not trip it.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))              # bin/ for placement_policy
from _hook_common import deny, hooks_disabled, read_payload, tool_input  # noqa: E402

WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
MKDIR_RX = re.compile(r"(?i)(?:^|[\s;&|(])(?:mkdir|md|new-item|ni)\b([^|;&\n]*)")
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
_VALUE_FLAGS = {"-itemtype", "-type", "-name", "-value", "-m", "--mode"}


def shell_targets(command: str) -> list[str]:
    """Directory paths a shell command would create. Relative paths resolve against the cwd."""
    out: list[str] = []
    for m in MKDIR_RX.finditer(_QUOTED.sub(" ", command)):
        skip_next = False
        for tok in m.group(1).split():
            low = tok.lower()
            if skip_next:
                skip_next = False
                continue
            if low in _VALUE_FLAGS:
                skip_next = True
                continue
            if tok.startswith("-"):
                continue
            out.append(os.path.join(os.getcwd(), os.path.expanduser(tok)))
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
            targets.extend((t, True) for t in shell_targets(cmd))

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
