"""skill-refiner.py — Skill-Forge Phase 0 (read-only signal validator).

Scores every skill in skills/ from claude-brain transcript history and writes
forge/report-latest.md. MODIFIES NOTHING.

Usage:
  python skill-refiner.py                 # full run (uses claude -p judge)
  python skill-refiner.py --skip-claude   # offline: stub judge (pipeline test)
  python skill-refiner.py --lookback-days 30
  python skill-refiner.py --verbose
"""
from __future__ import annotations
import argparse
import datetime as dt
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # find skill_forge package

from harness_common import clean_env, classify_claude_result
from skill_forge import config
from skill_forge.skills_inventory import list_skills
from skill_forge.brain_query import find_invocations, get_after_window
from skill_forge.judge import classify_invocation
from skill_forge.scoring import contribution_score, classify_action
from skill_forge.report import render_report
from skill_forge.evolution import append_event
from skill_forge.usage_log import read_invocations


def log(level: str, message: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} [{level}] {message}\n"
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="", file=sys.stderr)


class SessionPoolExhausted(Exception):
    """The claude session is rate-limited or unauthenticated — every further judge
    call this run would fail the same way. Abort the run cleanly instead of grinding
    through every skill until the scheduler's time limit kills the process."""
    def __init__(self, status: str, detail: str | None):
        super().__init__(f"{status}: {detail or ''}")
        self.status, self.detail = status, detail


def make_claude_invoker(timeout: int = 180):
    """Return invoke_fn(prompt)->str|None using `claude -p` (no tools, no hooks).
    Pattern copied from weekly-planner.py: subscription auth, fallback model,
    CLAUDE_BRAIN_SKIP_HOOKS so the judge call isn't polluted/recaptured.

    Raises SessionPoolExhausted on rate-limit/auth failure signatures — NOTE
    `claude -p` writes those to STDOUT, not stderr (classify_claude_result reads both)."""
    claude_path = shutil.which("claude") or shutil.which("claude.exe") or shutil.which("claude.cmd")
    if not claude_path:
        log("ERROR", "claude CLI not found")
        return lambda prompt: None

    def invoke(prompt: str):
        env = clean_env(CLAUDE_BRAIN_SKIP_HOOKS="1")
        try:
            r = subprocess.run(
                [claude_path, "-p", "--no-session-persistence",
                 "--disallowed-tools", "Read Write Edit Bash Glob Grep WebFetch WebSearch",
                 "--fallback-model", "claude-sonnet-4-6"],
                input=prompt, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout, env=env)
        except Exception as e:  # noqa: BLE001 - log + degrade to inapplicable
            log("WARN", f"claude judge invocation failed: {type(e).__name__}: {e}")
            return None
        if r.returncode != 0:
            status, detail = classify_claude_result(r.returncode, r.stdout or "", r.stderr or "")
            if status in ("rate_limited", "auth_failed"):
                raise SessionPoolExhausted(status, detail)
            log("WARN", f"claude judge non-zero [{status}]: {(r.stdout or r.stderr or '')[:300]}")
            return None
        return r.stdout.strip()

    return invoke


def score_skill(conn, skill, since, invoke_fn, verbose=False) -> dict:
    invs = find_invocations(conn, skill["name"], since=since)
    # Merge the PostToolUse usage log (the reliable frequency source). Brain
    # LIKE-detection misses most Skill-tool invocations (~7% recall vs the hook
    # log); log entries carry session_id + ts, so the same after-window judge
    # applies. Dedupe on (session_id, minute bucket) so double-detected calls
    # score once.
    seen = {(i["session_id"], (i["timestamp"] or "")[:16]) for i in invs}
    for rec in read_invocations(config.USAGE_LOG, skill["name"], since):
        key = (rec["session_id"], (rec["timestamp"] or "")[:16])
        if key in seen:
            continue
        seen.add(key)
        invs.append({"id": None, "session_id": rec["session_id"],
                     "timestamp": rec["timestamp"]})
    invs.sort(key=lambda r: r["timestamp"] or "")
    verdicts: list[str] = []
    for inv in invs:
        window = get_after_window(conn, inv["session_id"], inv["timestamp"],
                                  limit=config.AFTER_WINDOW)
        if not window:
            verdicts.append("inapplicable")
            continue
        verdicts.append(classify_invocation(
            skill["name"], skill["description"], window, invoke_fn))
    score = contribution_score(verdicts)
    trials = sum(1 for v in verdicts if v in ("helped", "hurt", "neutral"))
    action = classify_action(trials, score, config.N_MIN, config.TAU)
    if verbose:
        log("INFO", f"  {skill['name']}: invocations={len(invs)} trials={trials} "
                    f"score={score:+.2f} -> {action}")
    return {"name": skill["name"], "origin": skill["origin"],
            "invocations": len(invs), "trials": trials, "score": score, "action": action}


def main() -> int:
    ap = argparse.ArgumentParser(description="Skill-Forge Phase 0 signal validator (read-only).")
    ap.add_argument("--skip-claude", action="store_true",
                    help="Use a stub judge (offline pipeline test).")
    ap.add_argument("--lookback-days", type=int, default=config.LOOKBACK_DAYS)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    log("INFO", f"skill-refiner Phase 0 starting (skip_claude={args.skip_claude}, "
                f"lookback={args.lookback_days}d)")

    if not config.BRAIN_DB.exists():
        log("ERROR", f"brain DB not found: {config.BRAIN_DB}")
        return 1

    since = (dt.datetime.now(dt.timezone.utc)
             - dt.timedelta(days=args.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    skills = list_skills(config.SKILLS_DIR)
    log("INFO", f"scoring {len(skills)} skills since {since}")

    invoke_fn = (lambda prompt: "VERDICT: inapplicable") if args.skip_claude else make_claude_invoker()

    conn = sqlite3.connect(f"file:{config.BRAIN_DB}?mode=ro", uri=True)
    try:
        rows = [score_skill(conn, s, since, invoke_fn, args.verbose) for s in skills]
    except SessionPoolExhausted as e:
        # The session is closed (limit/auth) — skip THIS run cleanly and let the next
        # scheduled slot retry. The previous report stays in place: a partial one
        # would score every unjudged skill as if it had no evidence.
        if e.status == "auth_failed":
            # NOT a clean skip: waiting does not fix an expired login, so every
            # later run would fail the same way while the scheduler recorded
            # success and the report went quietly stale. Fail the run and say so.
            log("ERROR", "claude login failed — the judge needs a human to re-authenticate "
                         "(run `claude` and /login). Previous report left in place.")
            try:
                from notify_slack import post_slack
                post_slack("Skill-Forge could not run: the Claude login has expired or is "
                           "invalid. Re-authenticate (`claude`, then /login). The report "
                           "is stale until then.", title="Skill-Forge needs re-auth")
            except Exception as slack_err:  # noqa: BLE001
                log("WARN", f"Slack notify skipped: {type(slack_err).__name__}: {slack_err}")
            return 1
        # Rate limit: transient, the next scheduled slot retries on its own.
        log("WARN", f"claude session rate-limited — skipping this run; "
                    f"previous report left in place. {e.detail or ''}")
        return 0
    finally:
        conn.close()

    today = dt.date.today().isoformat()
    md = render_report(rows, today=today)
    config.REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.REPORT_PATH.write_text(md, encoding="utf-8")
    log("INFO", f"wrote report ({len(md)} chars) -> {config.REPORT_PATH}")
    append_event(
        strategy="calibrate",
        asset="forge/report-latest.md",
        what=f"Skill-Forge Phase 0 report: {len(rows)} skills scored",
        why=f"Weekly signal scan (lookback={args.lookback_days}d)",
        session="skill-refiner",
        log_path=config.EVOLUTION_LOG,
    )

    # Deliver to Slack (no-op if webhook unset) — reuse the existing helper.
    try:
        from notify_slack import post_slack
        post_slack(md, title=f"Skill-Forge report ({today})")
    except Exception as e:  # noqa: BLE001
        log("WARN", f"Slack notify skipped: {type(e).__name__}: {e}")

    log("INFO", "skill-refiner done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
