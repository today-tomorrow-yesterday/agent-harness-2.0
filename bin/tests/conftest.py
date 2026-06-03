"""Shared pytest fixtures: an in-memory-on-disk brain DB and a sample skills dir."""
from __future__ import annotations
import sqlite3
import pytest


@pytest.fixture
def brain_conn():
    """A sqlite connection seeded with the transcripts table subset we query."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE transcripts ("
        " id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,"
        " content TEXT, timestamp TEXT)"
    )
    rows = [
        # session s1: clone-route invoked, then user thanks (helped)
        (1, "s1", "user", "<command-name>clone-route</command-name>", "2026-05-01T10:00:00Z"),
        (2, "s1", "assistant", "Routed 3 folders.", "2026-05-01T10:01:00Z"),
        (3, "s1", "user", "perfect, thanks", "2026-05-01T10:02:00Z"),
        # session s2: clone-route invoked, then user corrects (hurt)
        (4, "s2", "user", "<command-name>clone-route</command-name>", "2026-05-02T11:00:00Z"),
        (5, "s2", "assistant", "Routed to expert joey.", "2026-05-02T11:01:00Z"),
        (6, "s2", "user", "no that's wrong, it should go to kallaway", "2026-05-02T11:02:00Z"),
        # session s3: an unrelated skill, never our target
        (7, "s3", "user", "<command-name>watch</command-name>", "2026-05-03T12:00:00Z"),
        (8, "s3", "assistant", "Watched the video.", "2026-05-03T12:01:00Z"),
    ]
    conn.executemany(
        "INSERT INTO transcripts (id, session_id, role, content, timestamp)"
        " VALUES (?,?,?,?,?)", rows)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def sample_skills_dir(tmp_path):
    """A skills/ dir with two SKILL.md files (one Tre-authored, one Forge-minted)."""
    sd = tmp_path / "skills"
    (sd / "clone-route").mkdir(parents=True)
    (sd / "clone-route" / "SKILL.md").write_text(
        "---\nname: clone-route\ndescription: Route inbox content into wiki.\n---\n\nBody.",
        encoding="utf-8")
    (sd / "compose-shorts").mkdir(parents=True)
    (sd / "compose-shorts" / "SKILL.md").write_text(
        "---\nname: compose-shorts\ndescription: Compose short clips.\n"
        "origin: skill-forge\n---\n\nBody.",
        encoding="utf-8")
    return sd
