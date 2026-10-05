#!/usr/bin/env python3
"""weekly-planner.py — a weekly "what's next" briefing, generated from your memory.

Reads your `memory/` (who you are, your project briefs, standing rules, and last
week's briefing), asks Claude to synthesize the highest-leverage next moves, and
writes `next-session.md` at the repo root. Runs on your Claude subscription via
`claude -p` (no API key). Cross-platform. Register it weekly via bin/scheduler.

Three LLM-free sections are prepended to the briefing, shortest first:
  1. the learning scorecard (is the harness getting better?),
  2. the Goal Loop (memory/goals.md: movement per goal, questions, next actions —
     skipped entirely while goals.md is absent or still the unfilled template),
  3. the Seed Review (ideas in forge/seedbank.json that are due for a decision).
See docs/goal-loop.md.

Usage:
    python bin/weekly-planner.py            # generate the briefing
    python bin/weekly-planner.py --dry-run  # build the prompt, don't call Claude
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MEMORY = REPO / "memory"
OUTPUT_PATH = REPO / "next-session.md"
ARCHIVE_PATH = REPO / "next-session.archive.md"
LOG_PATH = REPO / "logs" / "weekly-planner.log"


def log(level: str, message: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} [{level}] {message}\n"
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="", file=sys.stderr)


def _read_file(p: Path, max_chars: int = 8000) -> str:
    if not p.exists():
        return f"(not found: {p.name})"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars] + ("\n\n[truncated]" if len(text) > max_chars else "")
    except OSError as e:
        return f"(read error on {p.name}: {e})"


def _read_projects(max_each: int = 4000) -> str:
    pdir = MEMORY / "projects"
    if not pdir.exists():
        return "(no projects/ yet)"
    blocks = [f"### {f.stem}\n{_read_file(f, max_each)}"
              for f in sorted(pdir.glob("*.md")) if not f.stem.startswith(("_", "BOOTSTRAP", "README"))]
    return "\n\n".join(blocks) if blocks else "(no project briefs yet)"


def _list_feedback_rules() -> str:
    fdir = MEMORY / "feedback"
    if not fdir.exists():
        return "(none)"
    names = [f.stem for f in sorted(fdir.glob("*.md"))
             if not f.stem.startswith(("_", "BOOTSTRAP", "README"))]
    return ", ".join(names) if names else "(none)"


def _gather_context() -> dict:
    return {
        "today": dt.date.today().isoformat(),
        "user_md": _read_file(MEMORY / "user.md", 6000),
        "memory_index": _read_file(MEMORY / "MEMORY.md", 4000),
        "projects": _read_projects(),
        "feedback_rules": _list_feedback_rules(),
        "previous": _read_file(OUTPUT_PATH, 3000),
    }


def _build_prompt(ctx: dict) -> str:
    return f"""You are the user's Claude instance. Write their weekly "what's next" briefing
for {ctx['today']}. When they next open a session, this file should tell them
(a) where their projects stand, (b) the single highest-leverage next move, (c) why,
and (d) what's deferred or waiting.

Be honest about what's actually moving vs. stalled. Recommend ONE primary next move,
not a menu. Respect their standing rules (do not contradict them).

=== WHO THEY ARE (memory/user.md) ===
{ctx['user_md']}

=== MEMORY INDEX (memory/MEMORY.md) ===
{ctx['memory_index']}

=== PROJECT BRIEFS (memory/projects/) ===
{ctx['projects']}

=== STANDING RULES ON FILE (memory/feedback/) ===
{ctx['feedback_rules']}

=== LAST WEEK'S BRIEFING (for continuity) ===
{ctx['previous']}

=== OUTPUT ===
Write the briefing as clean Markdown (no surrounding backticks). Use these sections:
## What's moving
## Highest-leverage next move   (ONE, with a one-line why)
## Deferred / waiting
## How to use this briefing

Style: tables for 3+ item comparisons; sentence-then-bullets for single facts; no
walls of prose; no decorative emoji (severity glyphs 🔴🟡🟢 OK, sparingly); direct,
peer-to-peer tone.
"""


def _invoke_claude(prompt: str, timeout: int = 300) -> str | None:
    claude_path = (shutil.which("claude") or shutil.which("claude.exe")
                   or shutil.which("claude.cmd"))
    if not claude_path:
        log("ERROR", "claude CLI not found on PATH")
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from harness_common import clean_env
    # clean_env: never forward a metered API key to the child, and mark it unattended.
    # CLAUDE_BRAIN_SKIP_HOOKS keeps the planner's child session out of the brain.
    env = clean_env(CLAUDE_BRAIN_SKIP_HOOKS="1")
    try:
        result = subprocess.run(
            [claude_path, "-p", "--no-session-persistence",
             "--disallowed-tools", "Read Write Edit Bash Glob Grep WebFetch WebSearch",
             "--fallback-model", "claude-sonnet-4-6"],
            input=prompt, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            cwd=str(REPO), timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        log("ERROR", f"claude timed out after {timeout}s")
        return None
    except Exception as e:  # noqa: BLE001
        log("ERROR", f"claude invocation crashed: {e}")
        return None
    if result.returncode != 0:
        log("ERROR", f"claude returned non-zero: {result.stderr[:500]}")
        return None
    return result.stdout.strip()


GOALS_PATH = MEMORY / "goals.md"
# `repos:` entries in goals.md are resolved against the folder that CONTAINS this
# checkout (sibling clones), unless they are absolute paths.
REPO_BASE = REPO.parent
RESEARCH_CAP = 2             # at most this many web-research fetches per week
SEED_CADENCE_DAYS = 3.5      # how often an undecided idea comes back (twice a week)


def run_goal_loop(dry_run: bool = False, *, goals_path: Path | None = None,
                  repo_base: Path | None = None, db_path=None) -> str:
    """Goal Loop: assess progress toward memory/goals.md, run bounded research, and
    build the goal-progress + questions + recommendations section. On a live run the
    generated open questions (and any research notes) are written back to goals.md.

    Returns the markdown section, or '' when goals.md does not exist, is still the
    unfilled template, has no goals, or the loop fails (the brief must still write).
    """
    path = Path(goals_path or GOALS_PATH)
    if not path.exists():
        return ""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from goal_loop import goals_io, signals as gl_signals, assess as gl_assess
        from goal_loop import questions as gl_questions, recommend as gl_recommend
        from goal_loop import research as gl_research, report as gl_report
    except Exception as e:  # noqa: BLE001
        log("WARN", f"goal-loop import failed: {type(e).__name__}: {e}")
        return ""
    try:
        original = path.read_text(encoding="utf-8")
        if goals_io.is_unfilled_template(original):
            log("INFO", "goal loop skipped: memory/goals.md is still the template "
                        "(fill it in and delete its BOOTSTRAP block to switch the loop on)")
            return ""
        doc = goals_io.parse_goals(original)
        if not doc["goals"]:
            return ""
        # Paused goals stay in `doc` (so save() writes them back untouched) but are not
        # assessed, questioned, researched or recommended — see goals_io.is_paused.
        goals = goals_io.active_goals(doc["goals"])
        paused = [g for g in doc["goals"] if goals_io.is_paused(g)]
        since = "7 days ago"  # relative -> avoids a local-midnight timezone off-by-one
        sig = gl_signals.gather_signals(goals, Path(repo_base or REPO_BASE), since)
        verdicts = gl_assess.assess_progress(goals, sig)
        if dry_run:
            findings = gl_research.research_dispatch(goals, cap=RESEARCH_CAP, dry_run=True)
        else:
            # Two safety layers: the runner bounds the batch (kill-switch + action
            # ceiling + wall clock); inside it, each fetch goes through the execution
            # gate as a read_external action (risk-scored, policy-gated, audit-logged;
            # a risky question parks for approval) — see goal_loop/research.py.
            from runner import run as runner_run
            picked = gl_research.select_for_research(goals, cap=RESEARCH_CAP)
            steps = [(lambda g=g: (g["id"], gl_research.run_research(
                         g.get("next_step") or g.get("title", ""), db_path=db_path)))
                     for g in picked]
            res = runner_run.run("goal-loop-research", steps, max_actions=len(steps) + 2,
                                 max_seconds=1800,  # wall-clock bound: a fetch can hang
                                 db_path=db_path)
            findings = {gid: txt for gid, txt in (r for r in res["results"] if r) if txt}
        for gid, text in findings.items():
            for g in goals:
                if g["id"] == gid:
                    # Findings arrive quarantined (UNTRUSTED fences) from run_research;
                    # clip fence-aware so truncation never drops the closing marker.
                    # The dry-run placeholder is fenced too: nothing reaches a goal's
                    # notes, or the briefing, without its taint marker.
                    if not text.startswith(gl_research.Q_OPEN):
                        text = gl_research.quarantine(text)
                    g["research_notes"] = gl_research.clip_quarantined(text, 4000)
        qs = gl_questions.generate_questions(verdicts, goals)
        recs = gl_recommend.recommend_actions(goals, verdicts)
        section = gl_report.build_goal_section(goals, verdicts, qs, recs, paused=paused)
        if not dry_run:
            for g in goals:
                # startswith on "<id> ", not substring: G1 must not capture G10's questions.
                generated = [q for q in qs if q.startswith(g["id"] + " ")]
                if generated:  # only overwrite when we generated questions — never
                    g["open_questions"] = generated  # wipe hand-written open_questions
            if goals_io.serialize_goals(doc) != original:
                goals_io.save(path, doc)
        return section
    except Exception as e:  # noqa: BLE001 — the brief must still write even if the goal loop fails
        log("WARN", f"goal loop failed, skipping goal section: {type(e).__name__}: {e}")
        return ""


def run_seed_review(dry_run: bool = False, *, now_ts: int | None = None,
                    seedbank_path: Path | None = None) -> str:
    """Idea Cultivation: surface seeds due for a decision into the briefing. Marks
    them surfaced (advancing their cadence) unless dry_run. '' when none are due or
    no seedbank exists yet."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import time as _t
        from goal_loop import seeds as gl_seeds
        now = int(now_ts if now_ts is not None else _t.time())
        due = gl_seeds.due_for_review(now, SEED_CADENCE_DAYS, path=seedbank_path)
        if not due:
            return ""
        today = dt.datetime.fromtimestamp(now).date().isoformat()
        section = gl_seeds.render_review(due, today=today)
        if not dry_run:
            gl_seeds.mark_surfaced([sd["id"] for sd in due], now, path=seedbank_path)
        return section
    except Exception as e:  # noqa: BLE001 — seed review must never break the briefing
        log("WARN", f"seed review failed, skipping: {type(e).__name__}: {e}")
        return ""


def run_learning_scorecard(dry_run: bool = False) -> str:
    """Five numbers on whether the harness is getting better (see
    learning_scorecard.py). LLM-free. Writes its weekly snapshot unless dry_run."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import learning_scorecard
        return learning_scorecard.build_section(dry_run=dry_run)
    except Exception as e:  # noqa: BLE001 - the scorecard must never break the briefing
        log("WARN", f"learning scorecard failed, skipping: {type(e).__name__}: {e}")
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Weekly 'what's next' briefing from your memory.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build the prompt and report; don't call Claude or write output.")
    args = ap.parse_args()

    ctx = _gather_context()
    prompt = _build_prompt(ctx)
    log("INFO", f"weekly-planner: prompt ~{len(prompt):,} chars")

    if args.dry_run:
        card = run_learning_scorecard(dry_run=True)
        goal = run_goal_loop(dry_run=True)
        seed = run_seed_review(dry_run=True)
        log("INFO", f"dry-run - scorecard {len(card)} chars, goal loop {len(goal)} chars, "
                    f"seed review {len(seed)} chars; would write briefing to {OUTPUT_PATH}")
        return 0

    out = _invoke_claude(prompt)
    if not out:
        log("ERROR", "no output from claude; leaving previous briefing in place")
        return 1

    # Prepended, shortest first: the opening of a briefing is the part that gets
    # read. The scorecard says whether the harness is getting better; the goal loop
    # and seed review say what needs a decision. Each returns '' when it has nothing.
    card = run_learning_scorecard()
    goal = run_goal_loop()
    seed = run_seed_review()
    prefix = [sec for sec in (card, goal, seed) if sec]
    if prefix:
        out = "\n\n---\n\n".join(prefix + [out])
        log("INFO", f"prepended scorecard ({len(card)} chars) + goal loop ({len(goal)} chars) "
                    f"+ seed review ({len(seed)} chars)")

    if OUTPUT_PATH.exists():  # archive the prior briefing
        prev = OUTPUT_PATH.read_text(encoding="utf-8", errors="replace")
        with open(ARCHIVE_PATH, "a", encoding="utf-8") as a:
            a.write(f"\n\n---\n# Archived {ctx['today']}\n\n{prev}")

    # Atomic: write beside the target, then swap. A plain write_text() truncates
    # first, so a scheduler kill mid-write would leave an empty or half briefing.
    tmp = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".tmp")
    tmp.write_text(out + "\n", encoding="utf-8")
    os.replace(tmp, OUTPUT_PATH)
    log("INFO", f"wrote briefing to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
