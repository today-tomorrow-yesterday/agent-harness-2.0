"""Parse a PostToolUse hook payload into a usage record (testable core).

Field-name robustness: this harness's Skill tool uses `skill`/`args`, while the
Claude Code docs example shows `skill_name`/`arguments`. Accept both so the
logger works regardless of which the runtime actually emits.
"""
from __future__ import annotations
import json


def parse_payload(raw: str) -> dict:
    """Parse the hook's stdin into a dict. Tolerates a leading UTF-8 BOM
    (some pipes prepend one) and empty/garbled input (returns {})."""
    if not raw:
        return {}
    # Strip a leading UTF-8 BOM in either form: properly decoded (U+FEFF) or
    # mis-decoded as latin-1 bytes (EF BB BF -> U+00EF U+00BB U+00BF), which is
    # how some pipes deliver it.
    raw = raw.lstrip("﻿")
    if raw.startswith("\xef\xbb\xbf"):
        raw = raw[3:]
    raw = raw.strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def build_usage_record(payload: dict, now_iso: str) -> dict | None:
    """Return a usage record if `payload` is a Skill-tool invocation, else None."""
    if not isinstance(payload, dict):
        return None
    if payload.get("tool_name") != "Skill":
        return None
    ti = payload.get("tool_input") or {}
    skill = ti.get("skill") or ti.get("skill_name")
    if not skill:
        return None
    return {
        "ts": now_iso,
        "skill": skill,
        "args": ti.get("args") or ti.get("arguments") or "",
        "session_id": payload.get("session_id", ""),
        "cwd": payload.get("cwd", ""),
    }
