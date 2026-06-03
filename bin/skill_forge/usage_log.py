"""Read the skill-usage JSONL log written by the PostToolUse hook.

This is the reliable FREQUENCY source (the brain doesn't capture Skill-tool
invocations queryably — see spec 2026-05-29 §5). Forward-only: entries exist
from hook-install date onward.
"""
from __future__ import annotations
import json
from pathlib import Path


def read_invocations(log_path, skill_name: str, since: str) -> list[dict]:
    """Return [{session_id, timestamp}] for `skill_name` at/after ISO `since`,
    oldest-first. Tolerates malformed lines (skips them)."""
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    out: list[dict] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("skill") == skill_name and rec.get("ts", "") >= since:
            out.append({"session_id": rec.get("session_id", ""), "timestamp": rec.get("ts", "")})
    out.sort(key=lambda r: r["timestamp"])
    return out
