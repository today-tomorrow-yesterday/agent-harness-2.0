"""Tests for skill_forge.evolution.append_event."""
from __future__ import annotations
import json
import pytest
from skill_forge.evolution import append_event, VALID_STRATEGIES


def test_append_creates_file(tmp_path):
    log = tmp_path / "evolution.jsonl"
    append_event(strategy="repair", asset="feedback/foo.md",
                 what="fixed x", why="x was broken", session="abc12345",
                 log_path=log)
    assert log.exists()


def test_append_valid_json(tmp_path):
    log = tmp_path / "evolution.jsonl"
    append_event(strategy="innovate", asset="skills/my-skill/SKILL.md",
                 what="new skill", why="repeatable workflow detected", session="def67890",
                 log_path=log)
    entry = json.loads(log.read_text(encoding="utf-8").strip())
    assert entry["strategy"] == "innovate"
    assert entry["asset"] == "skills/my-skill/SKILL.md"
    assert entry["what"] == "new skill"
    assert entry["why"] == "repeatable workflow detected"
    assert entry["session"] == "def67890"
    assert "ts" in entry


def test_append_multiple_lines(tmp_path):
    log = tmp_path / "evolution.jsonl"
    append_event(strategy="repair", asset="a.md", what="w1", why="r1",
                 session="s1", log_path=log)
    append_event(strategy="harden", asset="b.md", what="w2", why="r2",
                 session="s2", log_path=log)
    lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["strategy"] == "repair"
    assert json.loads(lines[1])["strategy"] == "harden"


def test_append_invalid_strategy_raises(tmp_path):
    log = tmp_path / "evolution.jsonl"
    with pytest.raises(ValueError, match="strategy must be one of"):
        append_event(strategy="unknown", asset="x.md", what="w", why="r",
                     session="s", log_path=log)


def test_append_creates_parent_dirs(tmp_path):
    log = tmp_path / "nested" / "deep" / "evolution.jsonl"
    append_event(strategy="document", asset="memory/user.md",
                 what="added fact", why="new identity context", session="aaa00000",
                 log_path=log)
    assert log.exists()


def test_all_valid_strategies_accepted(tmp_path):
    log = tmp_path / "evolution.jsonl"
    for s in VALID_STRATEGIES:
        append_event(strategy=s, asset="x.md", what="w", why="r",
                     session="s", log_path=log)
    lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == len(VALID_STRATEGIES)
