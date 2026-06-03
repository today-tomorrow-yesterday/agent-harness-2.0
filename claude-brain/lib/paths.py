"""Shared path / session-id discovery used by hooks and scripts.

Created 2026-05-24 to fix a critical bug: the original `cwd.replace("/", "-")`
only handled POSIX separators, so on Windows the encoded folder name never
matched what Claude Code actually creates. Result: every live hook silently
no-op'd, and 100% of sessions were captured by the fallback `jsonl_ingest`
path instead of the live hook path. See `docs/AUDIT_2026_05_24.md` for the
full story.

Claude Code's actual encoding convention (verified by inspecting both
`~/.claude/projects/` and `~/.claude-<profile>/projects/` on Windows + macOS):
- Each of `/`, `\\`, `:` is replaced with `-`.
- Consecutive separators are NOT collapsed: `C:\Users\<USERNAME>` → `C--Users-<USERNAME>`.
- Drive-colon expansion is the load-bearing piece for Windows.

Multi-profile awareness: You may run multiple profiles (e.g. ~/.claude-work/ and ~/.claude/) on
the same machine, plans for a third. Every helper that searches for JSONLs
walks all discovered profile dirs, not just the hardcoded default.
"""

from __future__ import annotations

import glob
import os
from typing import Iterable


def encode_cwd(cwd: str) -> str:
    """Encode a working directory to Claude Code's projects-dir folder name.

    Cross-platform safe. Verified against real folder names in
    ~/.claude*/projects/ on Windows. Does not collapse consecutive
    separators, by design — `C:\Users\<USERNAME>` must round-trip to
    `C--Users-<USERNAME>` to match what Claude Code creates.
    """
    return cwd.replace("/", "-").replace("\\", "-").replace(":", "-")


def discover_profile_dirs() -> list[str]:
    """Return all Claude Code profile directories on this machine.

    Order of precedence:
    1. `$CLAUDE_CONFIG_DIR` if set (single dir, respects explicit override)
    2. Otherwise: every `~/.claude*` directory that exists
       (`.claude`, `.claude-<profile>`, future `.claude-foo`)

    Returns absolute paths. Empty list is possible (no Claude Code installed).
    """
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return [os.path.abspath(os.path.expandvars(os.path.expanduser(override)))]

    home = os.path.expanduser("~")
    if not os.path.isdir(home):
        return []

    dirs: list[str] = []
    try:
        for name in os.listdir(home):
            if name.startswith(".claude"):
                full = os.path.join(home, name)
                if os.path.isdir(full):
                    dirs.append(full)
    except OSError:
        return []

    return sorted(dirs)


def find_current_jsonl(cwd: str | None = None,
                       profile_dirs: Iterable[str] | None = None) -> tuple[str | None, str | None]:
    """Find the JSONL transcript file + session_id for the current session.

    Walks every profile dir under `~/.claude*/projects/<encoded_cwd>/*.jsonl`
    and returns the most recently modified one — that's the active session.

    Returns `(jsonl_path, session_id)` or `(None, None)` if nothing found.
    Never raises; returns `(None, None)` on permission/IO errors.
    """
    if cwd is None:
        cwd = os.getcwd()
    if profile_dirs is None:
        profile_dirs = discover_profile_dirs()

    encoded = encode_cwd(cwd)
    candidates: list[str] = []

    for profile in profile_dirs:
        project_dir = os.path.join(profile, "projects", encoded)
        try:
            candidates.extend(glob.glob(os.path.join(project_dir, "*.jsonl")))
        except OSError:
            continue

    if not candidates:
        return None, None

    jsonl_path = max(candidates, key=os.path.getmtime)
    session_id = os.path.splitext(os.path.basename(jsonl_path))[0]
    return jsonl_path, session_id


def detect_session_id(cwd: str | None = None) -> str | None:
    """Convenience wrapper — returns just the session_id, or None."""
    _, session_id = find_current_jsonl(cwd=cwd)
    return session_id
