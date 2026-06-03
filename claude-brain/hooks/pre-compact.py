#!/usr/bin/env python3
"""pre-compact.py - Claude Code PreCompact hook for claude-brain.

Fires before context compaction (manual /compact or auto-compact).
Safety net: calls write_exchange.py one final time to ensure all
messages are captured to the DB before compaction wipes context.

stop.py (async) handles normal capture, but there is a small window
where compaction could trigger before the last async stop.py finishes.
This hook closes that gap.

RULE: stdout is SACRED. Only valid JSON goes to stdout.
"""

import os
import subprocess
import sys

# Brain-internal subprocess guard (Phase 3, 2026-05-27): no-op when a brain
# script (e.g. distill_session.py) invokes `claude -p`. Hooks contract: stdout sacred.
if os.environ.get("CLAUDE_BRAIN_SKIP_HOOKS") == "1":
    print("{}")
    sys.exit(0)

# Make lib/ importable from a hook context
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.paths import find_current_jsonl  # noqa: E402


def main():
    # Read stdin (hook protocol requires it)
    sys.stdin.read()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Find the current session's JSONL across all profile dirs
    jsonl_path, session_id = find_current_jsonl()
    if not jsonl_path:
        print("{}")
        return

    # Call write_exchange.py - dedup is built in, safe to call multiple times
    try:
        subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "write_exchange.py"),
             "--session-id", session_id,
             "--jsonl-path", jsonl_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    print("{}")


if __name__ == "__main__":
    main()
