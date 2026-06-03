"""Query the claude-brain transcript DB for skill invocations and their outcomes.

Detection (Phase 0): a transcript row whose content contains
`<command-name>SKILL</command-name>` (slash-invocation form) OR the literal
`"skill": "SKILL"` / `Skill(SKILL)` shapes the Skill tool can serialize to.
The command-name form is the reliable signal; the others are best-effort and
their recall is a calibration target measured in Task 11.
"""
from __future__ import annotations
import sqlite3


def find_invocations(conn: sqlite3.Connection, skill_name: str, since: str) -> list[dict]:
    """Return [{id, session_id, timestamp}] for each invocation of skill_name
    at or after the ISO timestamp `since`, ordered oldest-first."""
    patterns = [
        f"%<command-name>{skill_name}</command-name>%",
        f"%<command-name>/{skill_name}</command-name>%",
        f'%"skill": "{skill_name}"%',
        f'%"skill":"{skill_name}"%',
    ]
    where = " OR ".join("content LIKE ?" for _ in patterns)
    sql = (
        f"SELECT id, session_id, timestamp FROM transcripts "
        f"WHERE timestamp >= ? AND ({where}) ORDER BY timestamp ASC"
    )
    cur = conn.execute(sql, [since, *patterns])
    return [{"id": r[0], "session_id": r[1], "timestamp": r[2]} for r in cur.fetchall()]


def get_after_window(conn: sqlite3.Connection, session_id: str,
                     after_timestamp: str, limit: int) -> list[dict]:
    """Return up to `limit` messages in `session_id` strictly after the given
    timestamp, oldest-first: [{role, content, timestamp}]. This is the evidence
    window the judge reads to decide whether the skill helped or hurt."""
    sql = (
        "SELECT role, content, timestamp FROM transcripts "
        "WHERE session_id = ? AND timestamp > ? "
        "ORDER BY timestamp ASC LIMIT ?"
    )
    cur = conn.execute(sql, [session_id, after_timestamp, limit])
    return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in cur.fetchall()]
