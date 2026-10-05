"""_hook_common.py -- small helpers shared by the hooks in bin/hooks/.

Not a hook itself (the leading underscore keeps it out of the hook catalog and the stdin smoke
test). stdlib only and no I/O at import time: a PreToolUse hook runs on EVERY matching tool call,
so importing this must stay cheap.

Every path is resolved from this file or from the user's home directory. Nothing here knows about
a particular machine, drive or user.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

# bin/hooks/_hook_common.py -> bin/hooks -> bin -> repo root
HOOKS_DIR = Path(__file__).resolve().parent
BIN = HOOKS_DIR.parent
ROOT = BIN.parent

_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")


def hooks_disabled() -> bool:
    """The repo-wide kill switch, plus the brain's recursion flag.

    HARNESS_HOOKS_DISABLED=1 turns every hook in bin/hooks off. CLAUDE_BRAIN_SKIP_HOOKS=1 is set on
    child `claude -p` processes spawned by the harness itself, so a hook never re-fires inside a
    subprocess another hook started.
    """
    return (os.environ.get("HARNESS_HOOKS_DISABLED") == "1"
            or os.environ.get("CLAUDE_BRAIN_SKIP_HOOKS") == "1")


def unattended() -> bool:
    """True in a headless/scheduled run where no human is present to approve anything.

    Set HARNESS_UNATTENDED=1 in the environment of any unattended `claude -p` run.
    """
    return os.environ.get("HARNESS_UNATTENDED") == "1"


def read_payload() -> dict | None:
    """Parse the hook's stdin. Anything that is not a JSON object -> None (caller allows)."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return None
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def tool_input(data: dict) -> dict:
    ti = data.get("tool_input")
    return ti if isinstance(ti, dict) else {}


def strip_quoted(command: str) -> str:
    """Blank out quoted substrings so data (grep patterns, echo text, commit messages) cannot trip
    command-shaped patterns. Deliberate quoting evasion is out of scope: these hooks guard against
    accidents, not adversaries."""
    return _QUOTED.sub('""', command)


def state_dir(name: str) -> Path:
    """Per-hook runtime state directory.

    Default: <repo>/logs/hook-state/<name>/ (logs/ is gitignored). HARNESS_HOOK_STATE_DIR overrides
    the parent, which is how the tests isolate themselves. Falls back to the system temp dir if the
    repo location is not writable.
    """
    base = os.environ.get("HARNESS_HOOK_STATE_DIR")
    parent = Path(base).expanduser() if base else ROOT / "logs" / "hook-state"
    d = parent / name
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except OSError:
        d = Path(tempfile.gettempdir()) / "harness-hook-state" / name
        d.mkdir(parents=True, exist_ok=True)
        return d


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s or "no-session")[:120]


def settings_path() -> Path:
    """The Claude Code settings.json, resolved the same way bin/register_hook.py resolves it."""
    override = os.environ.get("CLAUDE_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    cfg_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(cfg_dir).expanduser() if cfg_dir else Path.home() / ".claude"
    return base / "settings.json"


def same_or_under(path: str | Path, root: str | Path) -> bool:
    """Is `path` equal to or inside `root`? Case-insensitive only where the OS is (Windows)."""
    try:
        p = os.path.normcase(os.path.abspath(str(path)))
        r = os.path.normcase(os.path.abspath(str(root)))
        return os.path.commonpath([p, r]) == r
    except ValueError:            # different drives on Windows
        return False


def emit_context(event: str, text: str) -> None:
    """Advisory output: inject `text` into the model's context without blocking anything."""
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": text},
        "suppressOutput": True,
    }))


def deny(msg: str) -> int:
    """Deny = exit 2 with the reason on stderr (Claude Code hands it to the model)."""
    try:
        sys.stderr.write(msg.rstrip() + "\n")
    except Exception:
        pass
    return 2
