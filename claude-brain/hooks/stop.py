#!/usr/bin/env python3
"""stop.py - Claude Code Stop hook for claude-brain.

Fires after every Claude response completes.
1. Determines current session ID and JSONL path (cross-profile, cross-platform)
2. Spawns write_exchange.py detached to capture new messages to DB
3. If backup is older than 12 hours, triggers brain_sync.py (detached)
4. Returns {} (no additional context needed)

RULE: stdout is SACRED. Only valid JSON goes to stdout.
"""

import json
import os
import subprocess
import sys
import time

# Brain-internal subprocess guard (Phase 3, 2026-05-27): distill_session.py
# sets CLAUDE_BRAIN_SKIP_HOOKS=1 when invoking `claude -p` so the distillation
# call does not recursively capture itself into the DB.
# Hooks contract: stdout is SACRED — emit valid JSON and exit cleanly.
if os.environ.get("CLAUDE_BRAIN_SKIP_HOOKS") == "1":
    print("{}")
    sys.exit(0)

# Make lib/ importable from a hook context
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.paths import find_current_jsonl  # noqa: E402

_BACKUP_MAX_AGE = 12 * 3600  # 12 hours in seconds


def _detached_popen(cmd: list[str]) -> None:
    """Fire-and-forget subprocess. Cross-platform detach semantics."""
    if os.name == "nt":
        flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        )
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=flags, close_fds=True)
    else:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, close_fds=True)


def main():
    # Read stdin (hook protocol requires it)
    sys.stdin.read()

    # Determine ROOT (parent of hooks/)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Find the current session's JSONL across all profile dirs
    jsonl_path, session_id = find_current_jsonl()
    if not jsonl_path:
        print("{}")
        return

    # Spawn write_exchange.py DETACHED so the embedding model load (5-15s on
    # cold start, see sentence-transformers init in write_exchange.py) doesn't
    # block Claude's response. The script handles its own DB writes + dedup.
    try:
        _detached_popen([
            sys.executable,
            os.path.join(root, "scripts", "write_exchange.py"),
            "--session-id", session_id,
            "--jsonl-path", jsonl_path,
        ])
    except Exception as e:
        # stdout is sacred but stderr is fine — surface the error to operator
        print(f"stop.py: write_exchange spawn failed: {e}", file=sys.stderr)

    # Auto-backup if last backup is older than 12 hours
    try:
        backup_path = os.path.join(root, "db-backup", "claude-brain.db.bak1")
        run_backup = False
        if not os.path.exists(backup_path):
            run_backup = True
        else:
            age = time.time() - os.path.getmtime(backup_path)
            if age > _BACKUP_MAX_AGE:
                run_backup = True

        if run_backup:
            _detached_popen([
                sys.executable,
                os.path.join(root, "scripts", "brain_sync.py"),
            ])
    except Exception as e:
        print(f"stop.py: backup spawn failed: {e}", file=sys.stderr)

    print("{}")


if __name__ == "__main__":
    main()
