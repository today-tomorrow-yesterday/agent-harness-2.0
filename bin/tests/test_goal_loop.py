"""Unit tests for the Goal Loop pure modules + the git-signal helper."""
import importlib.util
import subprocess
import sys
from pathlib import Path


def _load(mod):
    p = Path(__file__).resolve().parents[1] / "goal_loop" / f"{mod}.py"
    s = importlib.util.spec_from_file_location(f"goal_loop_{mod}", p)
    m = importlib.util.module_from_spec(s)
    sys.modules[f"goal_loop_{mod}"] = m
    s.loader.exec_module(m)
    return m


gio = _load("goals_io")
assess = _load("assess")
questions = _load("questions")
recommend = _load("recommend")
report = _load("report")
signals_mod = _load("signals")
research = _load("research")


# --- goals_io ---
SAMPLE = """# North Star
Ship a useful, well-tested product.

# Active Goals

## G1 — Launch the public beta
- outcome: A live beta with real users
- success_signal: First 100 sign-ups + 1 paying user
- status: stalled
- last_moved: 2026-06-01
- next_step: Research beta launch checklist
- repos: [app-core]
- research_notes: (none yet)
- open_questions: []
"""


def test_parse_then_serialize_roundtrips():
    doc = gio.parse_goals(SAMPLE)
    assert doc["north_star"].startswith("Ship a useful")
    assert len(doc["goals"]) == 1
    g = doc["goals"][0]
    assert g["id"] == "G1" and g["title"] == "Launch the public beta"
    assert g["status"] == "stalled" and g["repos"] == ["app-core"]
    assert g["open_questions"] == []
    again = gio.parse_goals(gio.serialize_goals(doc))
    assert again["goals"][0]["next_step"] == g["next_step"]


# --- assess ---
def _goal(gid, last="2026-06-01", status="on-track"):
    return {"id": gid, "title": gid, "last_moved": last, "status": status}


def test_moved_when_signal_present():
    v = assess.assess_progress([_goal("G1")], {"G1": {"git_commits": 3, "artifacts": 0,
                               "log_activity": [], "brain_hits": 0, "blocker": None}})[0]
    assert v["verdict"] == "moved"
    assert any("3" in e for e in v["evidence"])


def test_stalled_when_no_signal():
    v = assess.assess_progress([_goal("G1")], {"G1": {"git_commits": 0, "artifacts": 0,
                               "log_activity": [], "brain_hits": 0, "blocker": None}})[0]
    assert v["verdict"] == "stalled"
    assert any("no movement detected" in e.lower() for e in v["evidence"])


def test_blocked_when_blocker():
    v = assess.assess_progress([_goal("G1")], {"G1": {"git_commits": 5, "artifacts": 0,
                               "log_activity": [], "brain_hits": 0, "blocker": "waiting on API key"}})[0]
    assert v["verdict"] == "blocked"
    assert any("API key" in e for e in v["evidence"])


# --- questions ---
def test_questions_for_stalled_capped_at_4():
    goals = [{"id": f"G{i}", "title": f"goal{i}", "last_moved": "2026-05-01"} for i in range(6)]
    verdicts = [{"id": f"G{i}", "verdict": "stalled", "evidence": ["x"]} for i in range(6)]
    qs = questions.generate_questions(verdicts, goals)
    assert 1 <= len(qs) <= 4
    assert any("goal0" in q for q in qs)


def test_blocked_question_mentions_unblock():
    goals = [{"id": "G1", "title": "beta", "last_moved": "2026-05-01"}]
    verdicts = [{"id": "G1", "verdict": "blocked", "evidence": ["blocked: needs phone"]}]
    qs = questions.generate_questions(verdicts, goals)
    assert any("unblock" in q.lower() or "needs phone" in q.lower() for q in qs)


# --- recommend ---
def test_rec_flags_real_world_action_for_approval():
    r = recommend.recommend_actions(
        [{"id": "G1", "title": "beta", "next_step": "Create a hosting account"}],
        [{"id": "G1", "verdict": "stalled", "evidence": []}])[0]
    assert r["needs_approval"] is True and "hosting account" in r["action"]


def test_rec_research_step_no_approval():
    r = recommend.recommend_actions(
        [{"id": "G1", "title": "beta", "next_step": "Research account requirements"}],
        [{"id": "G1", "verdict": "stalled", "evidence": []}])[0]
    assert r["needs_approval"] is False


# --- report ---
def test_goal_section_has_all_parts():
    goals = [{"id": "G1", "title": "beta", "last_moved": "2026-05-01"}]
    verdicts = [{"id": "G1", "verdict": "stalled", "evidence": ["no movement detected since 2026-05-01"]}]
    qs = ["G1 (beta) hasn't moved — kill it or next step?"]
    recs = [{"id": "G1", "action": "Create a hosting account", "needs_approval": True}]
    md = report.build_goal_section(goals, verdicts, qs, recs)
    assert "## Goal Progress" in md and "stalled" in md
    assert "## Questions" in md and "kill it" in md
    assert "## Recommended actions" in md and "[needs approval]" in md


# --- signals (git) ---
def test_count_git_commits_since(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=r, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=r, check=True)
    (r / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "commit", "-qm", "c1"], cwd=r, check=True)
    import datetime as _dt
    future = (_dt.date.today() + _dt.timedelta(days=2)).isoformat()
    assert signals_mod.count_git_commits_since(r, "2000-01-01") == 1
    assert signals_mod.count_git_commits_since(r, future) == 0  # no commits after a future date


# --- research (selection is pure) ---
def test_select_goals_needing_research_caps():
    goals = [{"id": f"G{i}", "next_step": "Research X", "research_notes": "(none yet)"} for i in range(5)]
    assert len(research.select_for_research(goals, cap=2)) == 2


def test_select_skips_non_research_steps():
    assert research.select_for_research(
        [{"id": "G1", "next_step": "Create account", "research_notes": ""}], cap=2) == []
