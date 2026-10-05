"""Tests for learning_scorecard.py — the weekly "is the harness getting better" card.

Covers the parts a decision rides on: which rows count as the user talking, what counts
as a correction vs a repeat, window bucketing, the better/worse call, honest-empty
when a source is missing or thin, and the rendered card. Every clock is pinned —
nothing here reads the real date, so a fixture cannot age out of its window.
"""
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BIN))

import learning_scorecard as ls  # noqa: E402

UTC = dt.timezone.utc
ASOF = dt.datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def _at(days_ago: float) -> dt.datetime:
    return ASOF - dt.timedelta(days=days_ago)


# --------------------------------------------------------------------------- #
# Who is talking
# --------------------------------------------------------------------------- #
def test_tool_results_and_skill_bodies_are_not_human():
    assert not ls.is_human_message("")
    assert not ls.is_human_message(None)
    assert not ls.is_human_message("ok")  # too short to carry a correction
    assert not ls.is_human_message("<task-notification>\n<task-id>a1</task-id>")
    assert not ls.is_human_message("Base directory for this skill: C:\\Users\\x\\.claude\\skills")
    assert not ls.is_human_message('[{"tool_use_id": "toolu_1", "type": "tool_result"}]')
    assert not ls.is_human_message("(Re-invocation of /taste-skill — the skill instructions were")
    assert not ls.is_human_message("x" * (ls.MAX_HUMAN_CHARS + 1))


def test_a_typed_message_is_human():
    assert ls.is_human_message("now I want you to use the ui and automation test")


# --------------------------------------------------------------------------- #
# Correction vs repeat
# --------------------------------------------------------------------------- #
def test_plain_request_is_neither():
    assert ls.classify_message("add a loading state to the gallery page") == (False, False)


def test_asking_where_things_stand_is_not_a_correction():
    # Half of the first live run's "repeat" hits were this shape.
    for text in ("What were we working on again?", "Can you start the service again?",
                 "I just said ten to say it, the threshold should be three"):
        assert ls.classify_message(text)[1] is False, text
    assert ls.classify_message("What were we working on again?") == (False, False)


def test_correction_that_is_not_a_repeat():
    assert ls.classify_message("that's not what I asked for, the header is wrong") == (True, False)


def test_repeat_is_always_also_a_correction():
    for text in ("I told you not to commit", "how many times do I have to say this",
                 "you keep adding the border", "it's still broken", "same mistake again"):
        assert ls.classify_message(text) == (True, True), text


# --------------------------------------------------------------------------- #
# Windows and arithmetic
# --------------------------------------------------------------------------- #
def test_window_steps_back_whole_weeks():
    start, end = ls.window(ASOF, 7)
    assert (start, end) == (_at(7), ASOF)
    start, end = ls.window(ASOF, 7, weeks_back=2)
    assert (start, end) == (_at(21), _at(14))


def test_rates_are_none_not_zero_on_an_empty_denominator():
    assert ls.per_100(0, 0) is None
    assert ls.pct(0, 0) is None
    assert ls.per_100(3, 60) == 5.0
    assert ls.pct(1, 4) == 25.0


def test_trend_direction_depends_on_which_way_is_good():
    assert ls.trend(5.0, 10.0, lower_is_better=True) == "🟢"
    assert ls.trend(10.0, 5.0, lower_is_better=True) == "🔴"
    assert ls.trend(10.0, 5.0, lower_is_better=False) == "🟢"
    assert ls.trend(5.0, 10.0, lower_is_better=False) == "🔴"


def test_trend_small_moves_are_flat_and_missing_is_unscored():
    assert ls.trend(10.5, 10.0, True) == "🟡"
    assert ls.trend(None, 10.0, True) == "⏳"
    assert ls.trend(10.0, None, True) == "⏳"
    assert ls.trend(0, 0, True) == "🟡"
    assert ls.trend(2, 0, True) == "🔴"
    assert ls.trend(2, 0, False) == "🟢"


def test_parse_ts_handles_z_and_garbage():
    assert ls.parse_ts("2026-10-04T12:00:00Z") == ASOF
    assert ls.parse_ts("2026-10-04T12:00:00.000Z") == ASOF
    assert ls.parse_ts("not a date") is None
    assert ls.parse_ts(None) is None


# --------------------------------------------------------------------------- #
# Corrections
# --------------------------------------------------------------------------- #
def _msg(days_ago, text, session="s1"):
    correction, repeat = ls.classify_message(text)
    return {"ts": _at(days_ago), "session": session, "correction": correction,
            "repeat": repeat, "text": text}


def test_score_corrections_counts_only_the_window():
    messages = [
        _msg(1, "add the picker"),
        _msg(2, "that's wrong"),
        _msg(3, "I told you already", session="s2"),
        _msg(9, "you keep doing this"),  # last week, must not count
    ]
    start, end = ls.window(ASOF, 7)
    out = ls.score_corrections(messages, start, end)
    assert out["human_messages"] == 3
    assert out["sessions"] == 2
    assert out["corrections"] == 2
    assert out["repeats"] == 1
    assert out["repeat_manifest"][0]["text"] == "I told you already"


def _make_db(path, rows):
    con = sqlite3.connect(path)
    con.execute("create table transcripts (session_id text, project text, type text, role text, "
                "content text, timestamp text, is_subagent integer default 0)")
    con.executemany("insert into transcripts values (?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def test_load_human_messages_drops_automated_subagent_and_tool_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "AUTOMATED_PROJECTS", ("gen",))   # opt-in: none by default
    db = tmp_path / "brain.db"
    ts = _at(1).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    _make_db(db, [
        ("s1", "aos", "user", "user", "you keep adding the border", ts, 0),
        ("s1", "aos", "user", "user", "<system-reminder>hook</system-reminder>", ts, 0),
        ("s1", "aos", "user", "user", "you keep adding the border", ts, 1),      # subagent
        ("s2", "gen", "user", "user", "you keep adding the border", ts, 0),      # headless
        ("s1", "aos", "assistant", "assistant", "you keep adding the border", ts, 0),
        ("s1", "aos", "user", "user", "you keep adding the border",
         _at(60).strftime("%Y-%m-%dT%H:%M:%S.000Z"), 0),                         # out of span
    ])
    out = ls.load_human_messages(db, _at(35), ASOF)
    assert out["error"] is None
    assert len(out["messages"]) == 1
    assert out["messages"][0]["repeat"] is True
    assert out["data_through"] == ts


def test_no_project_is_treated_as_automated_by_default(tmp_path):
    db = tmp_path / "brain.db"
    ts = _at(1).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    _make_db(db, [("s1", "gen", "user", "user", "add the picker to the page", ts, 0),
                  ("s2", "webapp", "user", "user", "add the picker to the page", ts, 0)])
    assert ls.AUTOMATED_PROJECTS == ()
    assert len(ls.load_human_messages(db, _at(35), ASOF)["messages"]) == 2


def test_missing_db_is_an_error_not_a_zero(tmp_path):
    out = ls.load_human_messages(tmp_path / "nope.db", _at(35), ASOF)
    assert out["messages"] == []
    assert "not found" in out["error"]


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #
def test_collect_rules_separates_edited_from_untouched(tmp_path):
    edited, untouched = tmp_path / "edited.md", tmp_path / "untouched.md"
    edited.write_text("rule", encoding="utf-8")
    untouched.write_text("rule", encoding="utf-8")
    # Both files are born at the real "now"; ask about a window in the future of
    # their birth so the edit, not the creation, is what lands inside it.
    born = max(ls._birth(edited.stat()), ls._birth(untouched.stat()))
    start = dt.datetime.fromtimestamp(born + 100, UTC)
    end = start + dt.timedelta(days=7)
    os.utime(edited, (born + 200, born + 200))
    os.utime(untouched, (born - 500, born - 500))
    out = ls.collect_rules(tmp_path, start, end)
    assert out == {"new": [], "amended": ["edited.md"], "created_from": "filesystem", "error": None}


def test_collect_rules_counts_a_file_born_in_the_window_as_new(tmp_path):
    rule = tmp_path / "fresh.md"
    rule.write_text("rule", encoding="utf-8")
    born = ls._birth(rule.stat())
    start = dt.datetime.fromtimestamp(born - 100, UTC)
    out = ls.collect_rules(tmp_path, start, start + dt.timedelta(days=7))
    assert out["new"] == ["fresh.md"] and out["amended"] == []


def test_collect_rules_missing_dir(tmp_path):
    assert "not found" in ls.collect_rules(tmp_path / "nope", _at(7), ASOF)["error"]


# --------------------------------------------------------------------------- #
# Goals
# --------------------------------------------------------------------------- #
GOALS_MD = """# North Star
Earn independently.

# Active Goals

## G1 — Ships
- status: in-progress
- last_moved: 2026-10-01
- repos: ["products/a"]

## G2 — Sits
- status: stalled
- last_moved: 2026-06-12
- repos: ["products/b"]

## G10 — Nobody is watching
- status: in-progress
- last_moved: 2026-06-27
- repos: []
"""


def test_collect_goals_splits_moved_stalled_and_untracked(tmp_path):
    goals = tmp_path / "goals.md"
    goals.write_text(GOALS_MD, encoding="utf-8")
    commits = {"a": 4, "b": 0}
    out = ls.collect_goals(goals, tmp_path, commit_counter=lambda repo, since: commits[Path(repo).name])
    assert out["total"] == 3
    assert [g["id"] for g in out["moved"]] == ["G1"]
    assert [g["id"] for g in out["stalled"]] == ["G2"]
    assert [g["id"] for g in out["untracked"]] == ["G10"]


def test_a_paused_goal_is_not_counted_as_failing_to_move(tmp_path):
    goals = tmp_path / "goals.md"
    goals.write_text(GOALS_MD.replace("- status: stalled", "- status: paused (2026-10-04, owner's call)"),
                     encoding="utf-8")
    out = ls.collect_goals(goals, tmp_path, commit_counter=lambda repo, since: 1)
    assert out["paused"] == ["G2"]
    assert out["total"] == 2
    assert "G2" not in [g["id"] for g in out["moved"] + out["stalled"] + out["untracked"]]


def test_collect_goals_missing_file(tmp_path):
    assert "not found" in ls.collect_goals(tmp_path / "nope.md", tmp_path)["error"]


# --------------------------------------------------------------------------- #
# Skills
# --------------------------------------------------------------------------- #
def _skill(root, name):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")


def test_collect_skills_hit_rate_and_plugin_prefix(tmp_path):
    skills = tmp_path / "skills"
    for name in ("watch", "frontend-design", "never-used", "long-ago"):
        _skill(skills, name)
    (skills / "not-a-skill").mkdir()  # no SKILL.md -> not counted
    # The fixture files are born at the real "now", so score from a point safely after.
    asof = dt.datetime.now(UTC) + dt.timedelta(days=200)
    usage = tmp_path / "skill-usage.jsonl"

    def row(days_before, skill):
        return json.dumps({"ts": (asof - dt.timedelta(days=days_before)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "skill": skill})
    usage.write_text("\n".join([
        row(3, "watch"),
        row(10, "frontend-design:frontend-design"),
        row(120, "long-ago"),
        "garbage line",
        json.dumps({"ts": (asof + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "skill": "never-used"}),  # after asof, must not count
    ]), encoding="utf-8")

    out = ls.collect_skills(skills, usage, asof)
    assert out["total"] == 4
    assert out["used"] == ["frontend-design", "watch"]
    assert out["unused"] == ["long-ago", "never-used"]
    assert out["retire_candidates"] == ["long-ago", "never-used"]
    assert out["hit_rate"] == 50.0


def test_an_idle_skill_another_skill_calls_is_not_retirable(tmp_path):
    # A pipeline step that only its parent skill calls looks unused. A mentioned
    # skill is idle, not dead.
    skills = tmp_path / "skills"
    for name in ("image-prompts", "standalone", "image"):
        _skill(skills, name)
    _skill(skills, "pipeline")
    (skills / "pipeline" / "SKILL.md").write_text(
        "---\nname: pipeline\n---\nStep 3: run image-prompts.\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "skill-sync-check.py").write_text("ALL = ['standalone', 'image']", encoding="utf-8")
    usage = tmp_path / "skill-usage.jsonl"
    usage.write_text("", encoding="utf-8")
    asof = dt.datetime.now(UTC) + dt.timedelta(days=200)
    out = ls.collect_skills(skills, usage, asof, program_dirs=(bin_dir,))
    assert out["idle_but_referenced"] == {"image-prompts": ["pipeline"]}
    # 'image' is a prefix of a mentioned name, not a mention; the sync list never counts.
    assert out["retire_candidates"] == ["image", "pipeline", "standalone"]


def test_a_program_that_reads_a_skill_keeps_it(tmp_path):
    skills = tmp_path / "skills"
    _skill(skills, "tidy-pass")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "nightly.py").write_text("SKILL = 'tidy-pass'", encoding="utf-8")
    (tmp_path / "u.jsonl").write_text("", encoding="utf-8")
    out = ls.collect_skills(skills, tmp_path / "u.jsonl",
                            dt.datetime.now(UTC) + dt.timedelta(days=200), program_dirs=(bin_dir,))
    assert out["idle_but_referenced"] == {"tidy-pass": ["nightly.py"]}
    assert out["retire_candidates"] == []


def test_a_new_skill_is_not_a_retire_candidate(tmp_path):
    skills = tmp_path / "skills"
    _skill(skills, "brand-new")
    usage = tmp_path / "skill-usage.jsonl"
    usage.write_text("", encoding="utf-8")
    out = ls.collect_skills(skills, usage, dt.datetime.now(UTC) + dt.timedelta(days=5))
    assert out["unused"] == ["brand-new"]
    assert out["retire_candidates"] == []


def test_collect_skills_missing_usage_log(tmp_path):
    (tmp_path / "skills").mkdir()
    out = ls.collect_skills(tmp_path / "skills", tmp_path / "nope.jsonl", ASOF)
    assert "not found" in out["error"]


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
def test_score_jobs_error_rate_and_worst_job_first():
    rows = [
        {"ts": _at(1), "job": "ingest", "status": "ok"},
        {"ts": _at(2), "job": "ingest", "status": "error"},
        {"ts": _at(2), "job": "Self-Test", "status": "error"},
        {"ts": _at(3), "job": "Self-Test", "status": "error"},
        {"ts": _at(3), "job": "Self-Loop", "status": "empty"},  # empty is not an error
        {"ts": _at(20), "job": "Self-Test", "status": "error"},  # outside the window
    ]
    start, end = ls.window(ASOF, 7)
    out = ls.score_jobs(rows, start, end)
    assert (out["runs"], out["errors"], out["error_rate"]) == (5, 3, 60.0)
    assert list(out["errors_by_job"]) == ["Self-Test", "ingest"]


def _make_runner_db(path, runs, error_events=()):
    con = sqlite3.connect(path)
    con.execute("create table runs (run_id text primary key, job text, status text, "
                "started_at integer, ended_at integer)")
    con.execute("create table events (id integer primary key autoincrement, run_id text, "
                "status text)")
    con.executemany("insert into runs values (?,?,?,?,?)", runs)
    con.executemany("insert into events(run_id, status) values (?,?)", error_events)
    con.commit()
    con.close()


def test_load_runs_counts_a_run_with_a_failed_action_as_failed(tmp_path):
    db = tmp_path / "runner.db"
    ts = int(_at(1).timestamp())
    _make_runner_db(db, [
        ("r1", "weekly-planner", "done", ts, ts),
        ("r2", "goal-research-fetch", "done", ts, ts),     # ended done, but an action errored
        ("r3", "self-loop", "halted", ts, ts),
        ("r4", "self-loop", "paused", ts, ts),             # parked for approval: not a failure
    ], error_events=[("r2", "error"), ("r1", "ok")])
    out = ls.load_runs(db)
    assert out["error"] is None
    assert {r["job"]: r["status"] for r in out["rows"] if r["job"] != "self-loop"} == {
        "weekly-planner": "done", "goal-research-fetch": "error"}
    assert sorted(r["status"] for r in out["rows"] if r["job"] == "self-loop") == ["error", "paused"]


def test_a_run_still_in_progress_is_not_counted_as_a_success(tmp_path):
    db = tmp_path / "runner.db"
    done = int(_at(2).timestamp())
    _make_runner_db(db, [
        ("r1", "ingest", "done", done, done),
        ("r2", "ingest", "error", done, done),
        ("r3", "ingest", "running", int(_at(1 / 24).timestamp()), None),   # started an hour ago
    ])
    start, end = ls.window(ASOF, 7)
    out = ls.score_jobs(ls.load_runs(db)["rows"], start, end)
    assert (out["runs"], out["errors"], out["error_rate"]) == (2, 1, 50.0)


def test_a_run_that_never_finished_is_a_failure(tmp_path):
    db = tmp_path / "runner.db"
    done = int(_at(2).timestamp())
    _make_runner_db(db, [
        ("r1", "ingest", "done", done, done),
        ("r2", "nightly", "running", int(_at(3).timestamp()), None),   # 3 days "running": killed
    ])
    start, end = ls.window(ASOF, 7)
    out = ls.score_jobs(ls.load_runs(db)["rows"], start, end)
    assert (out["runs"], out["errors"]) == (2, 1)
    assert out["errors_by_job"] == {"nightly": 1}


# --------------------------------------------------------------------------- #
# Creation time without a filesystem birth time (most Linux filesystems)
# --------------------------------------------------------------------------- #
class _NoBirthStat:
    """os.stat_result as Linux reports it: ctime moves on every edit, no birth time."""
    def __init__(self, mtime):
        self.st_mtime = mtime
        self.st_ctime = mtime


def test_birth_never_falls_back_to_ctime():
    assert ls._birth(_NoBirthStat(1_700_000_000)) is None


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})


def _commit(repo, name, when: dt.datetime, text):
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text, encoding="utf-8")
    stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    subprocess.run(["git", "-C", str(repo), "add", name], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", f"add {name}"], check=True,
                   capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp,
                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})


def test_git_first_added_keeps_the_first_commit_not_the_last_edit(tmp_path):
    _git(tmp_path, "init", "-q")
    _commit(tmp_path, "feedback/old.md", _at(60), "v1")
    _commit(tmp_path, "feedback/old.md", _at(2), "v2 edited this week")
    _commit(tmp_path, "feedback/fresh.md", _at(1), "v1")
    added = ls.git_first_added(tmp_path / "feedback")
    assert added["old.md"] == _at(60).timestamp()
    assert added["fresh.md"] == _at(1).timestamp()


def test_git_first_added_outside_a_repo_is_empty(tmp_path):
    assert ls.git_first_added(tmp_path) == {}


def test_an_edited_rule_is_amended_not_new_when_there_is_no_birth_time(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    rules = tmp_path / "feedback"
    _commit(tmp_path, "feedback/old.md", _at(60), "v1")
    _commit(tmp_path, "feedback/fresh.md", _at(1), "v1")
    (rules / "uncommitted.md").write_text("draft", encoding="utf-8")
    edited_at = _at(2).timestamp()
    for name in ("old.md", "fresh.md", "uncommitted.md"):
        os.utime(rules / name, (edited_at, edited_at))
    monkeypatch.setattr(ls, "_birth", lambda stat: None)   # behave like a no-birthtime filesystem
    start, end = ls.window(ASOF, 7)
    out = ls.collect_rules(rules, start, end)
    assert out["new"] == ["fresh.md"]
    # old.md was edited this week; uncommitted.md has no creation signal at all, and
    # calling it new would be a guess.
    assert out["amended"] == ["old.md", "uncommitted.md"]
    assert out["created_from"] == "git+unknown"


def test_skills_stay_in_the_count_when_creation_time_is_unknown(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    _skill(skills, "never-used")
    (tmp_path / "u.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(ls, "_birth", lambda stat: None)
    out = ls.collect_skills(skills, tmp_path / "u.jsonl", ASOF)
    assert out["total"] == 1
    assert out["retire_candidates"] == ["never-used"]


def test_load_runs_missing_db_is_honest_empty(tmp_path):
    out = ls.load_runs(tmp_path / "nope.db")
    assert out["rows"] == [] and "no background runs recorded yet" in out["error"]


# --------------------------------------------------------------------------- #
# Whole card
# --------------------------------------------------------------------------- #
def _fixture_world(tmp_path, this_week, prior_weeks):
    """A world where the user sent 40 messages a week; `this_week`/`prior_weeks` are
    how many of each week's 40 were repeat corrections."""
    rows = []
    for week, repeats in enumerate([this_week] + [prior_weeks] * 4):
        for i in range(40):
            ts = _at(week * 7 + 1 + i / 100).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            text = "you keep adding the border" if i < repeats else "add the picker to the page"
            rows.append((f"s{week}", "aos", "user", "user", text, ts, 0))
    db = tmp_path / "brain.db"
    _make_db(db, rows)
    hist = tmp_path / "runner.db"
    _make_runner_db(hist, [(f"r{d}", "ingest", "error" if d > 7 and d % 2 else "done",
                            int(_at(d).timestamp()), int(_at(d).timestamp()))
                           for d in range(1, 35)])
    goals = tmp_path / "goals.md"
    goals.write_text(GOALS_MD, encoding="utf-8")
    (tmp_path / "skills").mkdir()
    (tmp_path / "feedback").mkdir()
    (tmp_path / "usage.jsonl").write_text("", encoding="utf-8")
    return dict(db_path=db, usage_path=tmp_path / "usage.jsonl", runner_db=hist,
                goals_path=goals, feedback_dir=tmp_path / "feedback",
                skills_dir=tmp_path / "skills", out_dir=tmp_path / "out", repo_base=tmp_path,
                program_dirs=(), commit_counter=lambda repo, since: 1 if Path(repo).name == "a" else 0)


def test_compute_scores_fewer_repeats_as_better(tmp_path):
    snap = ls.compute(ASOF, **_fixture_world(tmp_path, this_week=2, prior_weeks=8))
    assert snap["corrections"]["repeats"] == 2
    assert snap["corrections"]["repeat_rate"] == 5.0
    assert snap["prior"]["repeat_rate"] == 20.0
    assert snap["jobs"]["errors"] == 0 and snap["prior"]["error_rate"] > 0
    card = ls.render(snap)
    rows = {line.split("|")[2].strip(): line.split("|")[1].strip()
            for line in card.splitlines() if line.startswith("| ") and "Number" not in line}
    assert rows["Repeat corrections"] == "🟢"
    assert rows["Correction rate"] == "🟢"
    assert rows["Job error rate"] == "🟢"
    assert rows["Goals moved"] == "⏳"  # no earlier snapshot to compare against
    assert "1 of 3 active (G1)" in card
    assert "1 goal(s) have no repo" in card


def test_compute_scores_more_repeats_as_worse(tmp_path):
    card = ls.render(ls.compute(ASOF, **_fixture_world(tmp_path, this_week=12, prior_weeks=4)))
    assert "| 🔴 | Repeat corrections |" in card


def test_thin_week_is_shown_but_not_scored(tmp_path):
    world = _fixture_world(tmp_path, this_week=2, prior_weeks=8)
    con = sqlite3.connect(world["db_path"])
    con.execute("delete from transcripts where session_id='s0' and rowid not in "
                "(select rowid from transcripts where session_id='s0' limit 5)")
    con.commit()
    con.close()
    card = ls.render(ls.compute(ASOF, **world))
    assert "| ⏳ | Repeat corrections |" in card
    assert "too few messages to score (5 this week" in card


def test_missing_sources_render_a_dash_and_the_reason(tmp_path):
    snap = ls.compute(ASOF, db_path=tmp_path / "no.db", usage_path=tmp_path / "no.jsonl",
                      runner_db=tmp_path / "no-runner.db", goals_path=tmp_path / "no.md",
                      feedback_dir=tmp_path / "no-feedback", skills_dir=tmp_path / "no-skills",
                      out_dir=tmp_path / "out", repo_base=tmp_path, program_dirs=())
    card = ls.render(snap)
    assert card.count("| ⏳ |") == 5
    assert "transcript db not found" in card
    assert "0 better, 0 worse, 0 flat, 5 not scored yet" in card


def test_backfill_does_not_claim_a_goal_number(tmp_path):
    snap = ls.compute(ASOF, live=False, **_fixture_world(tmp_path, 2, 8))
    assert "not replayable" in snap["goals"]["error"]


def test_prior_goal_number_comes_from_saved_snapshots(tmp_path):
    world = _fixture_world(tmp_path, 2, 8)
    world["out_dir"].mkdir()
    for weeks_ago, moved in ((1, 3), (2, 3)):
        asof = ASOF - dt.timedelta(days=7 * weeks_ago)
        (world["out_dir"] / f"{asof:%Y-%m-%d}.json").write_text(json.dumps({
            "asof": asof.isoformat(),
            "goals": {"moved": [{"id": f"G{i}"} for i in range(moved)], "error": None},
        }), encoding="utf-8")
    snap = ls.compute(ASOF, **world)
    assert snap["prior"]["goals_moved"] == 3.0
    assert "| 🔴 | Goals moved |" in ls.render(snap)  # 1 this week vs 3 before
