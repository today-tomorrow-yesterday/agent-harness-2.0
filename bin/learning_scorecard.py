#!/usr/bin/env python3
r"""
learning_scorecard.py — is your harness getting better? Five numbers, weekly.

WHAT:     Scores the last 7 days against the 4 weeks before them, on five numbers
          that measure improvement instead of size.
MAKES:    forge/learning-scorecard/YYYY-MM-DD.json (snapshot + manifests),
          forge/learning-scorecard/latest.md (the card).
RUN:      python bin/learning_scorecard.py             # build + write files + print
          python bin/learning_scorecard.py --print     # print only, write nothing
          python bin/learning_scorecard.py --asof 2026-09-06   # score an earlier week
READS:    claude-brain/claude-brain.db (transcripts, read-only),
          forge/skill-usage.jsonl, forge/runner.db (read-only),
          memory/goals.md, memory/feedback/*.md, skills/*/SKILL.md.
WRITES:   forge/learning-scorecard/ only.
NEEDS:    stdlib. No model calls, no network, no subscription cost.
USED BY:  weekly-planner.py prepends build_section() to the weekly briefing.
SIBLINGS: skill_forge/ (per-skill contribution scoring).

WHY IT EXISTS. A harness that keeps taking in rules, skills and notes feels like it
is improving. Counting those measures how much it has taken in, not whether it works
better. These five numbers are the difference:

  1. Repeat corrections — your messages that say a mistake happened AGAIN.
  2. Correction rate    — your messages that correct the agent at all.
  3. Goals moved        — goals in goals.md with commits in the last 7 days.
  4. Skill hit rate     — share of your skills invoked in the last 30 days.
  5. Job error rate     — background runs that ended in error.

THREE RULES:

  MANIFEST, NOT JUST COUNT. Every number carries the list it counted, in the JSON.
    A count that moves with no manifest cannot be explained after the fact.
  HONEST-EMPTY. A source that is missing or too thin renders "—" with the reason.
    It is never a fabricated 0, and a rate over fewer than MIN_MESSAGES messages is
    shown but never scored better or worse. A fresh install shows mostly "—".
  1 and 2 ARE KEYWORD MATCHES, NOT JUDGMENTS. They match phrases in your own
    messages. Good for a trend, wrong for any single message. The matched messages
    are in the snapshot so a number that looks off can be read, not argued with.
    The phrase lists are English; edit CORRECTION_RE / REPEAT_RE to match how you
    actually talk to your agent.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # bin/ on path for helpers

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "forge" / "learning-scorecard"
DB_PATH = REPO / "claude-brain" / "claude-brain.db"
SKILL_USAGE_PATH = REPO / "forge" / "skill-usage.jsonl"
RUNNER_DB = REPO / "forge" / "runner.db"
GOALS_PATH = REPO / "memory" / "goals.md"
FEEDBACK_DIR = REPO / "memory" / "feedback"
SKILLS_DIR = REPO / "skills"

WINDOW_DAYS = 7
PRIOR_WEEKS = 4
SKILL_WINDOW_DAYS = 30
RETIRE_AFTER_DAYS = 90
MIN_MESSAGES = 30          # below this a rate is shown but not scored
FLAT_BAND = 0.10           # under 10% relative change counts as flat
STALE_RUN_HOURS = 6         # a run still 'running' after this was killed, not slow
AUTOMATED_PROJECTS: tuple[str, ...] = ()   # brain project prefixes that are headless jobs, not you
# Programs that list every skill by name (sync/inventory tools). Being named in one
# of these is not a dependency, so they never keep a skill off the retire list.
INVENTORY_PROGRAMS = ("skill-sync-check.py",)
MAX_HUMAN_CHARS = 4000     # longer than this is a paste or a headless prompt

# A user-role row is mostly NOT the user: tool results, skill bodies, hook output
# and task notifications all arrive with role=user.
_NOT_HUMAN = re.compile(
    r"^\s*(<|\[\{|\{|\[Request interrupted|Caveat:|This session is being continued|"
    r"Base directory for this skill|\(Re-invocation of|\[tool_result|Tool result)",
    re.IGNORECASE,
)

# Broad: the user is correcting the agent.
CORRECTION_RE = re.compile(
    r"\b(i (already |just )?(told|said|asked)|that'?s (not|wrong)|"
    r"you (didn'?t|did not|forgot|missed|ignored|keep|still|were supposed)|"
    r"why (did|didn'?t|are|would) you|not what i (asked|said|meant|wanted)|"
    r"how many times|stop (doing|it)|wrong|wtf|what the (hell|fuck)|fuck|damn|"
    r"frustrat|ridiculous|terrible|ugly|you'?re not listening|"
    r"didn'?t work|doesn'?t work|still (broken|not|wrong|doesn))",
    re.IGNORECASE,
)
# Narrow: the correction says it has happened BEFORE. This is the learning test —
# a rule that worked does not get asked for twice.
# A bare "again?" is deliberately NOT here. On the first live run it was half of all
# hits and every one was the user asking where things stood ("what were we working on
# again?"), not reporting a repeated mistake.
REPEAT_RE = re.compile(
    r"\b(i already (told|said|asked)|i (just )?(told|asked) you|i said (that|not|no|don'?t|to)\b|"
    r"you (keep|still|forgot|ignored)|(once|yet) again|how many times|"
    r"you'?re not listening|still (broken|not|wrong|doesn)|"
    r"(same|this) (mistake|thing|problem|issue) again)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def is_human_message(content: str | None) -> bool:
    if not content:
        return False
    text = content.strip()
    if len(text) < 8 or len(text) > MAX_HUMAN_CHARS:
        return False
    if _NOT_HUMAN.match(text) or "tool_use_id" in text[:200]:
        return False
    return True


def classify_message(content: str) -> tuple[bool, bool]:
    """(is_correction, is_repeat). A repeat is always also a correction."""
    repeat = bool(REPEAT_RE.search(content))
    return (repeat or bool(CORRECTION_RE.search(content))), repeat


def parse_ts(raw) -> dt.datetime | None:
    """ISO timestamp -> aware UTC datetime. None when unparseable."""
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def window(asof: dt.datetime, days: int, weeks_back: int = 0) -> tuple[dt.datetime, dt.datetime]:
    """The `days`-long window ending `weeks_back` weeks before `asof`."""
    end = asof - dt.timedelta(days=7 * weeks_back)
    return end - dt.timedelta(days=days), end


def per_100(hits: int, total: int) -> float | None:
    return round(100.0 * hits / total, 1) if total else None


def pct(part: int, total: int) -> float | None:
    return round(100.0 * part / total, 1) if total else None


def trend(current, prior, lower_is_better: bool) -> str:
    """🟢 better / 🔴 worse / 🟡 flat / ⏳ nothing to compare against."""
    if current is None or prior is None:
        return "⏳"
    if prior == 0:
        if current == 0:
            return "🟡"
        went_down = False
    else:
        change = (current - prior) / prior
        if abs(change) < FLAT_BAND:
            return "🟡"
        went_down = change < 0
    return "🟢" if went_down == lower_is_better else "🔴"


def mean(values) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


# --------------------------------------------------------------------------- #
# Collectors — each returns counts plus the manifest it counted
# --------------------------------------------------------------------------- #
def load_human_messages(db_path: Path, start: dt.datetime, end: dt.datetime) -> dict:
    """Every message the user typed between start and end, classified once.

    Returns {"messages": [...], "data_through": iso|None, "error": str|None}.
    Read-only connection: this runs while the brain is being written to.
    """
    out = {"messages": [], "data_through": None, "error": None}
    if not Path(db_path).exists():
        out["error"] = f"transcript db not found: {db_path}"
        return out
    skip = ""
    if AUTOMATED_PROJECTS:
        marks = ",".join("?" for _ in AUTOMATED_PROJECTS)
        skip = f" and coalesce(project,'') not in ({marks})"
    try:
        con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True, timeout=30)
        try:
            out["data_through"] = con.execute("select max(timestamp) from transcripts").fetchone()[0]
            rows = con.execute(
                "select timestamp, session_id, content from transcripts "
                "where role='user' and type='user' and is_subagent=0 "
                f"and timestamp>=? and timestamp<?{skip}",
                (start.strftime("%Y-%m-%dT%H:%M:%S"), end.strftime("%Y-%m-%dT%H:%M:%S"),
                 *AUTOMATED_PROJECTS),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        out["error"] = f"transcript db unreadable: {type(e).__name__}: {e}"
        return out
    for raw_ts, session_id, content in rows:
        ts = parse_ts(raw_ts)
        if ts is None or not is_human_message(content):
            continue
        correction, repeat = classify_message(content)
        out["messages"].append({"ts": ts, "session": session_id, "correction": correction,
                                "repeat": repeat, "text": " ".join(content.split())[:200]})
    return out


def score_corrections(messages: list[dict], start: dt.datetime, end: dt.datetime) -> dict:
    inside = [m for m in messages if start <= m["ts"] < end]
    corrections = [m for m in inside if m["correction"]]
    repeats = [m for m in inside if m["repeat"]]
    return {
        "human_messages": len(inside),
        "sessions": len({m["session"] for m in inside}),
        "corrections": len(corrections),
        "repeats": len(repeats),
        "correction_rate": per_100(len(corrections), len(inside)),
        "repeat_rate": per_100(len(repeats), len(inside)),
        "repeat_manifest": [{"ts": m["ts"].isoformat(), "session": m["session"], "text": m["text"]}
                            for m in repeats],
    }


def _birth(stat) -> float | None:
    """Filesystem creation time, or None where the platform does not record one.

    NEVER falls back to st_ctime: on Linux that is the last inode change, so editing
    a file moves it, and every edited rule would be counted as a new one. Windows and
    macOS expose st_birthtime; most Linux filesystems do not through os.stat.
    """
    return getattr(stat, "st_birthtime", None)


def git_first_added(directory: Path) -> dict[str, float]:
    """{path relative to `directory`: time it was first committed}, from git.

    The creation signal for platforms with no birth time. Empty when the directory
    is not in a git repo or git is unavailable — callers then treat creation as
    unknown instead of guessing.
    """
    try:
        res = subprocess.run(
            ["git", "-C", str(directory), "log", "--diff-filter=A", "--format=%x00%at",
             "--name-only", "--relative", "--", "."],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return {}
    if res.returncode != 0:
        return {}
    first: dict[str, float] = {}
    stamp = None
    for line in res.stdout.splitlines():
        if line.startswith("\x00"):
            try:
                stamp = float(line[1:])
            except ValueError:
                stamp = None
        elif line.strip() and stamp is not None:
            name = line.strip()
            # git log runs newest-first; keep the EARLIEST add (a file can be re-added).
            if name not in first or stamp < first[name]:
                first[name] = stamp
    return first


class _Creation:
    """Resolves when files under one directory were created: filesystem birth time
    first, git's first-add time second, None (unknown) last. Asks git at most once,
    and only if some file actually lacks a birth time."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._git: dict[str, float] | None = None
        self.sources: set[str] = set()

    def of(self, path: Path, stat) -> float | None:
        born = _birth(stat)
        if born is not None:
            self.sources.add("filesystem")
            return born
        if self._git is None:
            self._git = git_first_added(self.directory)
        try:
            rel = Path(path).resolve().relative_to(self.directory.resolve()).as_posix()
        except ValueError:
            rel = Path(path).name
        born = self._git.get(rel)
        self.sources.add("git" if born is not None else "unknown")
        return born

    @property
    def source(self) -> str:
        return "+".join(sorted(self.sources)) or "none"


def collect_rules(feedback_dir: Path, start: dt.datetime, end: dt.datetime) -> dict:
    """Rule files created in the window, and older ones edited in it.

    An edit to an existing rule is usually an addendum after the rule was broken,
    so `amended` backs up the repeat-corrections number from a different source.
    mtime only keeps the LAST edit, so this is exact for the current week only.

    `created_from` says where creation times came from. Where it includes "unknown"
    (no filesystem birth time AND the file is not committed yet), a file touched this
    week is listed as amended: calling it new would be a guess.
    """
    out = {"new": [], "amended": [], "created_from": "none", "error": None}
    feedback_dir = Path(feedback_dir)
    if not feedback_dir.is_dir():
        out["error"] = f"feedback dir not found: {feedback_dir}"
        return out
    lo, hi = start.timestamp(), end.timestamp()
    creation = _Creation(feedback_dir)
    for path in sorted(feedback_dir.glob("*.md")):
        try:
            stat = path.stat()
        except OSError:
            continue
        born = creation.of(path, stat)
        if born is not None and lo <= born < hi:
            out["new"].append(path.name)
        elif lo <= stat.st_mtime < hi:
            out["amended"].append(path.name)
    out["created_from"] = creation.source
    return out


def collect_goals(goals_path: Path, repo_base: Path, commit_counter=None,
                  since: str = f"{WINDOW_DAYS} days ago") -> dict:
    """Goals with at least one commit in their repos this week.

    Same signal the Goal Loop uses, so the two never disagree. A goal with no
    `repos` cannot move by this measure — it is listed under `untracked`, because
    "stalled" and "not being watched" are different problems.
    """
    out = {"total": 0, "moved": [], "stalled": [], "untracked": [], "paused": [], "error": None}
    goals_path = Path(goals_path)
    if not goals_path.exists():
        out["error"] = f"goals file not found: {goals_path}"
        return out
    try:
        from goal_loop import goals_io, signals
        goals = goals_io.load(goals_path)["goals"]
        counter = commit_counter or signals.count_git_commits_since
    except Exception as e:  # noqa: BLE001 — the card must still render
        out["error"] = f"goals unreadable: {type(e).__name__}: {e}"
        return out
    # `total` is ACTIVE goals. A goal paused on purpose is not a goal that
    # failed to move, and counting it would hide progress on the ones that matter.
    out["paused"] = [g["id"] for g in goals if goals_io.is_paused(g)]
    goals = goals_io.active_goals(goals)
    out["total"] = len(goals)
    for g in goals:
        entry = {"id": g["id"], "title": g["title"], "last_moved": g.get("last_moved", "")}
        repos = g.get("repos") or []
        if not repos:
            out["untracked"].append(entry)
            continue
        commits = sum(counter(Path(repo_base) / r, since) for r in repos)
        entry["commits"] = commits
        (out["moved"] if commits else out["stalled"]).append(entry)
    return out


def _skill_key(name: str) -> str:
    """'frontend-design:frontend-design' and 'frontend-design' are one skill."""
    return str(name).rsplit(":", 1)[-1].strip().lower()


def find_references(skills_dir: Path, names: list[str], program_dirs=()) -> dict[str, list[str]]:
    """For each named skill, the OTHER skills and programs that mention it.

    A skill nobody invokes directly can still be a step in a pipeline: an early
    run of this card listed five such skills as retire candidates, and every one
    was called by a parent skill or read by a scheduled program. Retiring them
    would have broken the pipeline, so a mentioned skill is reported as idle,
    never as retirable. A mention is a whole-word match — a guess, but one that errs toward
    keeping a skill.
    """
    sources: list[tuple[str, str, str]] = []  # (owner skill or "", label, text)
    for skill_md in sorted(Path(skills_dir).glob("*/SKILL.md")):
        try:
            sources.append((skill_md.parent.name, skill_md.parent.name,
                            skill_md.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    for directory in program_dirs:
        for prog in sorted(Path(directory).glob("*.py")):
            if prog.name in INVENTORY_PROGRAMS:
                continue  # carries a flat list of every skill name; a mention there means nothing
            try:
                sources.append(("", prog.name, prog.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    refs: dict[str, list[str]] = {}
    for name in names:
        word = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
        hits = [label for owner, label, text in sources if owner != name and word.search(text)]
        if hits:
            refs[name] = hits
    return refs


def collect_skills(skills_dir: Path, usage_path: Path, asof: dt.datetime, program_dirs=()) -> dict:
    out = {"total": 0, "used": [], "unused": [], "retire_candidates": [],
           "idle_but_referenced": {}, "error": None}
    skills_dir, usage_path = Path(skills_dir), Path(usage_path)
    if not skills_dir.is_dir():
        out["error"] = f"skills dir not found: {skills_dir}"
        return out
    if not usage_path.exists():
        out["error"] = f"skill usage log not found: {usage_path}"
        return out
    last_used: dict[str, dt.datetime] = {}
    for line in usage_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        ts = parse_ts(row.get("ts"))
        if ts is None or ts >= asof or not row.get("skill"):
            continue
        key = _skill_key(row["skill"])
        if key not in last_used or ts > last_used[key]:
            last_used[key] = ts
    recent = asof - dt.timedelta(days=SKILL_WINDOW_DAYS)
    old = asof - dt.timedelta(days=RETIRE_AFTER_DAYS)
    creation = _Creation(skills_dir)
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            created = creation.of(skill_md, skill_md.stat())
        except OSError:
            continue
        # Unknown creation time counts as "has always existed": the skill stays in the
        # denominator and can become a retire candidate. The alternative (treating it
        # as brand new) would hide every skill on a platform with no birth time.
        born = dt.datetime.fromtimestamp(created or 0, dt.timezone.utc)
        if born >= asof:
            continue  # did not exist yet at `asof`
        name = skill_md.parent.name
        used_at = last_used.get(name.lower())
        out["total"] += 1
        if used_at and used_at >= recent:
            out["used"].append(name)
            continue
        out["unused"].append(name)
        # A skill younger than the retire window has not had its chance yet.
        if born < old and (used_at is None or used_at < old):
            out["retire_candidates"].append(name)
    out["idle_but_referenced"] = find_references(skills_dir, out["retire_candidates"], program_dirs)
    out["retire_candidates"] = [n for n in out["retire_candidates"]
                                if n not in out["idle_but_referenced"]]
    out["hit_rate"] = pct(len(out["used"]), out["total"])
    return out


def load_runs(runner_db: Path) -> dict:
    """Every background run in forge/runner.db, with whether it failed.

    A run failed if it ended `error` or `halted`, or if any action inside it logged
    an error — an action error is recorded on the event and the run still ends
    `done`, so the run status alone would hide it. Read-only connection.
    """
    out = {"rows": [], "error": None}
    runner_db = Path(runner_db)
    if not runner_db.exists():
        out["error"] = "no background runs recorded yet (forge/runner.db not found)"
        return out
    try:
        con = sqlite3.connect(f"file:{runner_db.as_posix()}?mode=ro", uri=True, timeout=30)
        try:
            rows = con.execute(
                "select r.started_at, r.job, r.status, r.ended_at, "
                "exists(select 1 from events e where e.run_id=r.run_id and e.status='error') "
                "from runs r where r.started_at is not null").fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        out["error"] = f"runner db unreadable: {type(e).__name__}: {e}"
        return out
    for started_at, job, status, ended_at, had_error in rows:
        failed = status in ("error", "halted") or bool(had_error)
        out["rows"].append({"ts": dt.datetime.fromtimestamp(started_at, dt.timezone.utc),
                            "job": job or "?", "status": "error" if failed else (status or "?"),
                            # no outcome yet: still executing, or killed before end_run()
                            "unfinished": not failed and ended_at is None and status == "running"})
    return out


def score_jobs(rows: list[dict], start: dt.datetime, end: dt.datetime) -> dict:
    """Error rate over runs that have an outcome.

    A run still marked `running` has none yet, so it is left out — counting it would
    add a "success" to the denominator and push the rate down. The exception is a run
    that has been `running` for more than STALE_RUN_HOURS as of the window's end: it
    was killed before it could record an outcome, and that is a failure.
    """
    stale_before = end - dt.timedelta(hours=STALE_RUN_HOURS)
    inside = []
    for r in rows:
        if not (start <= r["ts"] < end):
            continue
        if r.get("unfinished"):
            if r["ts"] >= stale_before:
                continue                      # may simply still be running
            r = {**r, "status": "error"}      # orphaned: never reached end_run()
        inside.append(r)
    errors = [r for r in inside if r["status"] == "error"]
    by_job: dict[str, int] = {}
    for r in errors:
        by_job[r["job"]] = by_job.get(r["job"], 0) + 1
    return {"runs": len(inside), "errors": len(errors), "error_rate": pct(len(errors), len(inside)),
            "errors_by_job": dict(sorted(by_job.items(), key=lambda kv: (-kv[1], kv[0])))}


# --------------------------------------------------------------------------- #
# Assemble
# --------------------------------------------------------------------------- #
def load_snapshots(out_dir: Path, before: dt.datetime) -> list[dict]:
    """Earlier weekly snapshots, newest first — the only history for the numbers
    that cannot be recomputed after the fact (goals moved)."""
    snaps = []
    for path in sorted(Path(out_dir).glob("20??-??-??.json"), reverse=True):
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        asof = parse_ts(snap.get("asof"))
        if asof is not None and asof <= before - dt.timedelta(days=5):
            snaps.append(snap)
    return snaps[:PRIOR_WEEKS]


def compute(asof: dt.datetime, *, db_path=DB_PATH, usage_path=SKILL_USAGE_PATH,
            runner_db=RUNNER_DB, goals_path=GOALS_PATH, feedback_dir=FEEDBACK_DIR,
            skills_dir=SKILLS_DIR, out_dir=OUT_DIR, repo_base=None, commit_counter=None,
            program_dirs=(REPO / "bin",), live: bool = True) -> dict:
    """Build the full snapshot. `live=False` (an --asof backfill) skips the goal
    signal, which reads git relative to the real clock and cannot be replayed."""
    start, end = window(asof, WINDOW_DAYS)
    span_start = window(asof, WINDOW_DAYS, PRIOR_WEEKS)[0]

    loaded = load_human_messages(db_path, span_start, end)
    outcomes = load_runs(runner_db)

    corrections = score_corrections(loaded["messages"], start, end)
    jobs = score_jobs(outcomes["rows"], start, end)
    skills = collect_skills(skills_dir, usage_path, asof, program_dirs=program_dirs)

    prior_corr, prior_jobs, prior_skills = [], [], []
    for k in range(1, PRIOR_WEEKS + 1):
        p_start, p_end = window(asof, WINDOW_DAYS, k)
        prior_corr.append(score_corrections(loaded["messages"], p_start, p_end))
        prior_jobs.append(score_jobs(outcomes["rows"], p_start, p_end))
        prior_skills.append(collect_skills(skills_dir, usage_path, p_end))

    # Pooled, not a mean of weekly rates: a quiet week with 12 messages must not
    # weigh the same as a week with 600.
    p_msgs = sum(c["human_messages"] for c in prior_corr)
    p_runs = sum(j["runs"] for j in prior_jobs)
    snapshots = load_snapshots(out_dir, asof)
    prior = {
        "human_messages": p_msgs,
        "repeat_rate": per_100(sum(c["repeats"] for c in prior_corr), p_msgs),
        "correction_rate": per_100(sum(c["corrections"] for c in prior_corr), p_msgs),
        "error_rate": pct(sum(j["errors"] for j in prior_jobs), p_runs),
        "hit_rate": mean(s.get("hit_rate") for s in prior_skills),
        "goals_moved": mean(len(s["goals"]["moved"]) for s in snapshots
                            if s.get("goals") and not s["goals"].get("error")),
        "snapshots_used": len(snapshots),
    }

    if live:
        goals = collect_goals(goals_path, repo_base or REPO.parent, commit_counter)
    else:
        goals = {"total": 0, "moved": [], "stalled": [], "untracked": [], "paused": [],
                 "error": "not replayable for an earlier week (git signal uses the real clock)"}

    return {
        "asof": asof.isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": WINDOW_DAYS},
        "data_through": loaded["data_through"],
        "corrections": {**corrections, "error": loaded["error"]},
        "rules": collect_rules(feedback_dir, start, end),
        "goals": goals,
        "skills": skills,
        "jobs": {**jobs, "error": outcomes["error"]},
        "prior": prior,
    }


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def _num(value, suffix: str = "") -> str:
    return "—" if value is None else f"{value:g}{suffix}"


def _rows(snap: dict) -> list[dict]:
    c, g, s, j, p = snap["corrections"], snap["goals"], snap["skills"], snap["jobs"], snap["prior"]
    thin = c["human_messages"] < MIN_MESSAGES or p["human_messages"] < MIN_MESSAGES
    thin_note = (f"too few messages to score ({c['human_messages']} this week, "
                 f"{p['human_messages']} prior)") if thin else ""
    rows = []

    if c["error"]:
        for name in ("Repeat corrections", "Correction rate"):
            rows.append({"mark": "⏳", "name": name, "now": "—", "prior": "—", "note": c["error"]})
    else:
        rows.append({
            "mark": "⏳" if thin else trend(c["repeat_rate"], p["repeat_rate"], True),
            "name": "Repeat corrections",
            "now": f"{c['repeats']} ({_num(c['repeat_rate'])} per 100 messages)",
            "prior": f"{_num(p['repeat_rate'])} per 100", "note": thin_note or "want it falling"})
        rows.append({
            "mark": "⏳" if thin else trend(c["correction_rate"], p["correction_rate"], True),
            "name": "Correction rate",
            "now": f"{c['corrections']} of {c['human_messages']} messages "
                   f"({_num(c['correction_rate'])} per 100)",
            "prior": f"{_num(p['correction_rate'])} per 100", "note": thin_note or "want it falling"})

    if g["error"]:
        rows.append({"mark": "⏳", "name": "Goals moved", "now": "—", "prior": "—", "note": g["error"]})
    else:
        note = "want it rising"
        if g["untracked"]:
            note += f"; {len(g['untracked'])} goal(s) have no repo, so nothing can see them move"
        if g.get("paused"):
            note += f"; {len(g['paused'])} paused"
        rows.append({
            "mark": trend(len(g["moved"]), p["goals_moved"], False),
            "name": "Goals moved",
            "now": f"{len(g['moved'])} of {g['total']} active"
                   + (f" ({', '.join(x['id'] for x in g['moved'])})" if g["moved"] else ""),
            "prior": _num(p["goals_moved"]), "note": note})

    if s["error"]:
        rows.append({"mark": "⏳", "name": "Skill hit rate", "now": "—", "prior": "—", "note": s["error"]})
    else:
        rows.append({
            "mark": trend(s["hit_rate"], p["hit_rate"], False),
            "name": "Skill hit rate",
            "now": f"{len(s['used'])} of {s['total']} own skills used in {SKILL_WINDOW_DAYS} days "
                   f"({_num(s['hit_rate'], '%')})",
            "prior": _num(p["hit_rate"], "%"),
            "note": f"want it rising; unused for {RETIRE_AFTER_DAYS}+ days: "
                    f"{len(s['retire_candidates'])} standalone, "
                    f"{len(s['idle_but_referenced'])} still called by another skill or program"})

    if j["error"]:
        rows.append({"mark": "⏳", "name": "Job error rate", "now": "—", "prior": "—", "note": j["error"]})
    else:
        worst = next(iter(j["errors_by_job"]), None)
        rows.append({
            "mark": trend(j["error_rate"], p["error_rate"], True),
            "name": "Job error rate",
            "now": f"{j['errors']} of {j['runs']} runs ({_num(j['error_rate'], '%')})",
            "prior": _num(p["error_rate"], "%"),
            "note": "want it falling" + (f"; most errors: {worst}" if worst else "")})
    return rows


def render(snap: dict) -> str:
    rows = _rows(snap)
    tally = {m: sum(1 for r in rows if r["mark"] == m) for m in ("🟢", "🔴", "🟡", "⏳")}
    verdict = (f"{tally['🟢']} better, {tally['🔴']} worse, {tally['🟡']} flat"
               + (f", {tally['⏳']} not scored yet" if tally["⏳"] else ""))
    # An --asof window ends at midnight; name the last day inside it, not the day after.
    end = parse_ts(snap["window"]["end"]) - dt.timedelta(microseconds=1)
    lines = [
        f"## Learning Scorecard — {WINDOW_DAYS} days to {end:%Y-%m-%d}",
        "",
        f"**{verdict}** against the {PRIOR_WEEKS} weeks before.",
        "",
        "| | Number | This week | Prior 4 weeks | Note |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {r['mark']} | {r['name']} | {r['now']} | {r['prior']} | {r['note']} |" for r in rows]
    rules = snap["rules"]
    if not rules["error"]:
        lines += ["", f"Rules: {len(rules['new'])} new, {len(rules['amended'])} existing rule(s) "
                      "edited (an edit usually means the rule was broken again)."]
    through = parse_ts(snap.get("data_through"))
    lines += ["", "_Rows 1 and 2 are keyword matches on your messages: read the trend, not the "
                  "single week. Transcripts through "
                  f"{through:%Y-%m-%d %H:%M} UTC. " if through else
                  "_Rows 1 and 2 are keyword matches on your messages: read the trend, not the "
                  "single week. "]
    lines[-1] += r"Manifests: `forge\learning-scorecard\`._"
    return "\n".join(lines)


def _jsonable(snap: dict) -> dict:
    return json.loads(json.dumps(snap, default=str))


def build_section(dry_run: bool = False, now: dt.datetime | None = None) -> str:
    """The card for the Sunday brief. Writes the snapshot unless dry_run."""
    asof = now or dt.datetime.now(dt.timezone.utc)
    snap = compute(asof)
    card = render(snap)
    if not dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        snap_path = OUT_DIR / f"{asof:%Y-%m-%d}.json"
        tmp = snap_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_jsonable(snap), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, snap_path)   # atomic: next week's comparison reads this file
        (OUT_DIR / "latest.md").write_text(card + "\n", encoding="utf-8")
    return card


def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly learning scorecard for the harness.")
    parser.add_argument("--print", action="store_true", dest="print_only",
                        help="Print the card, write nothing.")
    parser.add_argument("--asof", help="Score the 7 days ending on this date (YYYY-MM-DD, UTC). "
                                       "Prints only; goals are not replayable.")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # the card has emoji; cp1252 does not

    if args.asof:
        asof = dt.datetime.strptime(args.asof, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        print(render(compute(asof + dt.timedelta(days=1), live=False)))
        return 0
    print(build_section(dry_run=args.print_only))
    return 0


if __name__ == "__main__":
    sys.exit(main())
