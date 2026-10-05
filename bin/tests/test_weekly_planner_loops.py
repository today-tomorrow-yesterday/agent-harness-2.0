"""The weekly planner's Goal Loop and Seed Review wiring (run_goal_loop /
run_seed_review in bin/weekly-planner.py).

Nothing here calls Claude or the network: the research fetch is replaced at the
action's transport (so the runner AND the execution gate still run for real), the
runner DB is a tmp file, and every clock is pinned.
"""
import importlib.util
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]
REPO = BIN.parent
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from goal_loop import goals_io, research, seeds  # noqa: E402
from goal_loop import signals as gl_signals  # noqa: E402
from execution.actions import research_web  # noqa: E402

DAY = 86400
NOW = 1_800_000_000          # a fixed instant; no test depends on today's date


@pytest.fixture
def planner(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("weekly_planner_under_test",
                                                  BIN / "weekly-planner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "LOG_PATH", tmp_path / "planner.log")
    return mod


@pytest.fixture
def no_claude(monkeypatch):
    """Replace the research transport; record what would have been fetched."""
    asked = []

    def fake_fetch(question, timeout):
        asked.append(question)
        return f"findings for: {question}"
    monkeypatch.setattr(research_web, "_claude_fetch", fake_fetch)
    return asked


@pytest.fixture
def quiet_signals(monkeypatch):
    """No git access: G4 'moved', everything else has no movement."""
    def fake(goals, repo_base, since):
        return {g["id"]: {"git_commits": 3 if g["id"] == "G4" else 0, "artifacts": 0,
                          "log_activity": [], "brain_hits": 0, "blocker": None}
                for g in goals}
    monkeypatch.setattr(gl_signals, "gather_signals", fake)


GOALS = """---
name: goals
description: test goals
type: user
---

# North Star
Ship a small, useful tool.

# Active Goals
## G1 — Finish the importer
- outcome: imports work end to end
- status: stalled
- last_moved: 2026-01-02
- next_step: write the CSV edge-case tests
- repos: []
- open_questions: ["an old hand-written question"]

Free-form notes the loop must keep.

## G2 — Explore a hosted version
- status: paused (decided to wait)
- last_moved: 2026-01-01
- next_step: research hosting options
- open_questions: []

## G3 — Pick a charting library
- status: on-track
- last_moved: 2026-01-03
- next_step: research the three most used charting libraries
- open_questions: []

## G4 — Keep the docs current
- status: on-track
- last_moved: 2026-01-04
- next_step: review the README
- open_questions: ["keep this hand-written question"]
"""


def _goals_file(tmp_path, text=GOALS):
    p = tmp_path / "goals.md"
    p.write_text(text, encoding="utf-8")
    return p


# --------------------------------------------------------------- when the loop stays off
def test_absent_goals_file_is_a_noop(planner, tmp_path):
    assert planner.run_goal_loop(goals_path=tmp_path / "goals.md") == ""
    assert planner.run_goal_loop(dry_run=True, goals_path=tmp_path / "goals.md") == ""


def test_the_shipped_template_is_skipped_and_never_rewritten(planner, tmp_path, no_claude):
    shipped = REPO / "memory" / "goals.md"
    assert goals_io.is_unfilled_template(shipped.read_text(encoding="utf-8"))
    copy = tmp_path / "goals.md"
    shutil.copyfile(shipped, copy)
    before = copy.read_bytes()
    db = tmp_path / "runner.db"
    assert planner.run_goal_loop(goals_path=copy, db_path=db) == ""
    assert copy.read_bytes() == before
    assert not db.exists() and no_claude == []
    assert "still the template" in (tmp_path / "planner.log").read_text(encoding="utf-8")


def test_the_shipped_template_parses_to_no_goals():
    """Even with the marker deleted, the placeholders are not mistaken for goals."""
    text = (REPO / "memory" / "goals.md").read_text(encoding="utf-8")
    assert goals_io.parse_goals(text.replace(goals_io.TEMPLATE_MARKER, ""))["goals"] == []


def test_the_shipped_template_has_no_bom():
    raw = (REPO / "memory" / "goals.md").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_a_file_without_goals_is_a_noop(planner, tmp_path):
    p = _goals_file(tmp_path, "# North Star\nsomething\n\n# Active Goals\n")
    assert planner.run_goal_loop(goals_path=p, db_path=tmp_path / "r.db") == ""


# --------------------------------------------------------------- dry run
def test_dry_run_builds_the_section_and_writes_nothing(planner, tmp_path, no_claude,
                                                       quiet_signals):
    p = _goals_file(tmp_path)
    db = tmp_path / "runner.db"
    section = planner.run_goal_loop(dry_run=True, goals_path=p, db_path=db)
    assert "## Goal Progress" in section and "G1 Finish the importer" in section
    assert p.read_text(encoding="utf-8") == GOALS
    assert no_claude == [] and not db.exists()


# --------------------------------------------------------------- live run
def test_live_run_section_questions_research_and_write_back(planner, tmp_path, no_claude,
                                                            quiet_signals):
    p = _goals_file(tmp_path)
    db = tmp_path / "runner.db"
    section = planner.run_goal_loop(goals_path=p, db_path=db)

    # the section: active goals assessed, paused goal on one line only
    assert "**G1 Finish the importer** — stalled" in section
    assert "**G4 Keep the docs current** — moved" in section
    assert "Paused (not assessed): G2" in section
    assert "G2 Explore" not in section

    # research: only the ACTIVE goal asking for it, through the real gate + runner
    assert no_claude == ["research the three most used charting libraries"]
    with sqlite3.connect(db) as c:
        jobs = {r[0] for r in c.execute("SELECT job FROM runs")}
        invokes = c.execute("SELECT COUNT(*) FROM events WHERE event_type='action:invoke'"
                            ).fetchone()[0]
    assert {"goal-loop-research", "goal-research-fetch"} <= jobs and invokes == 1

    doc = goals_io.load(p)
    g = {x["id"]: x for x in doc["goals"]}
    # generated questions replace the old ones for the goals they were generated for
    assert len(g["G1"]["open_questions"]) == 1
    assert g["G1"]["open_questions"][0].startswith("G1 (Finish the importer)")
    # a goal with no generated question keeps its hand-written one
    assert g["G4"]["open_questions"] == ["keep this hand-written question"]
    # research notes are fenced as untrusted and the fence survives
    notes = g["G3"]["research_notes"]
    assert notes.startswith(research.Q_OPEN) and notes.rstrip().endswith(research.Q_CLOSE)
    assert "findings for:" in notes
    # the paused goal, the free-form body and the preamble are untouched
    assert g["G2"]["status"] == "paused (decided to wait)" and g["G2"]["research_notes"] == ""
    text = p.read_text(encoding="utf-8")
    assert "Free-form notes the loop must keep." in text
    assert text.startswith("---\nname: goals\n")
    assert not (tmp_path / "goals.md.tmp").exists()


def test_a_risky_research_question_parks_and_is_not_requeued(planner, tmp_path, no_claude,
                                                             quiet_signals):
    risky = GOALS.replace("research the three most used charting libraries",
                          "research how to sign up and pay for a hosted plan")
    p = _goals_file(tmp_path, risky)
    db = tmp_path / "runner.db"
    planner.run_goal_loop(goals_path=p, db_path=db)
    planner.run_goal_loop(goals_path=p, db_path=db)       # the following week
    assert no_claude == []                                 # never fetched without approval
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT status FROM approvals").fetchall()
    assert rows == [("pending",)]                          # asked once, not every week
    assert goals_io.load(p)["goals"][2]["research_notes"] == ""


def test_a_goal_loop_failure_never_breaks_the_briefing(planner, tmp_path, monkeypatch):
    p = _goals_file(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("signals exploded")
    monkeypatch.setattr(gl_signals, "gather_signals", boom)
    assert planner.run_goal_loop(goals_path=p, db_path=tmp_path / "r.db") == ""
    assert p.read_text(encoding="utf-8") == GOALS
    assert "signals exploded" in (tmp_path / "planner.log").read_text(encoding="utf-8")


# --------------------------------------------------------------- goals_io additions
def test_preamble_survives_a_round_trip():
    doc = goals_io.parse_goals(GOALS)
    assert doc["preamble"].startswith("---\nname: goals")
    again = goals_io.serialize_goals(doc)
    assert again.startswith("---\nname: goals")
    assert goals_io.parse_goals(again)["preamble"] == doc["preamble"]


def test_no_preamble_serializes_as_before():
    doc = {"north_star": "ns", "goals": []}
    assert goals_io.serialize_goals(doc).startswith("# North Star\nns")


# --------------------------------------------------------------- seed review
def test_seed_review_is_empty_without_a_seedbank(planner, tmp_path):
    assert planner.run_seed_review(now_ts=NOW, seedbank_path=tmp_path / "none.json") == ""


def test_seed_review_dry_run_does_not_advance_the_cadence(planner, tmp_path):
    db = tmp_path / "seedbank.json"
    seeds.capture("an idea", now_ts=NOW - DAY, path=db)
    section = planner.run_seed_review(dry_run=True, now_ts=NOW, seedbank_path=db)
    assert "an idea" in section
    assert seeds.list_seeds(path=db)[0]["surface_count"] == 0


def test_seed_review_live_marks_surfaced_and_respects_cadence(planner, tmp_path):
    db = tmp_path / "seedbank.json"
    seeds.capture("an idea", now_ts=NOW - DAY, path=db)
    assert "an idea" in planner.run_seed_review(now_ts=NOW, seedbank_path=db)
    assert seeds.list_seeds(path=db)[0]["last_surfaced_at"] == NOW
    # one day later it is not due again (cadence 3.5 days); five days later it is
    assert planner.run_seed_review(now_ts=NOW + DAY, seedbank_path=db) == ""
    assert "an idea" in planner.run_seed_review(now_ts=NOW + 5 * DAY, seedbank_path=db)


# --------------------------------------------------------------- fresh clone
def test_dry_run_main_on_a_fresh_clone(planner, tmp_path, monkeypatch, no_claude):
    """No goals, no seeds, no Slack webhook, no runner database: --dry-run succeeds."""
    monkeypatch.setattr(planner, "GOALS_PATH", tmp_path / "goals.md")
    monkeypatch.setattr(seeds, "SEEDBANK", tmp_path / "seedbank.json")
    monkeypatch.setattr(planner, "OUTPUT_PATH", tmp_path / "next-session.md")
    for var in ("SLACK_WEBHOOK_URL", "SLACK_WEBHOOK_DIGEST_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sys, "argv", ["weekly-planner.py", "--dry-run"])
    assert planner.main() == 0
    assert not (tmp_path / "next-session.md").exists()
    log = (tmp_path / "planner.log").read_text(encoding="utf-8")
    assert "goal loop 0 chars" in log and "seed review 0 chars" in log
