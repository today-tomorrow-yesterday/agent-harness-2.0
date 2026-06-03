"""
weekly-planner.py — Sunday-morning briefing for Tre.

Runs once a week (Sunday 09:00 local by default). Reads the current state
of the AI Production Engine project, the CLONE wiki, and recent agent-os
memory changes, then invokes `claude -p` headlessly to synthesize a
"here's what's next and why" report. Writes the result to
`Z:\\agent-os\\next-session.md` so when you open a session he finds the
briefing waiting.

What this does NOT do:
  - Make decisions for you (just surfaces options + reasoning)
  - Build production plumbing (that's still session-based work)
  - Modify memory or project files (read-only synthesis)

What it DOES do:
  - Surface the highest-leverage next move per week
  - Document what landed in CLONE since the last run (farmer routings,
    new methodology files, new experts)
  - Track which capability gaps in projects/ai_production_engine.md are
    closer to being unblock-worthy
  - Note any standing feedback rule changes you might want to remember

Cost model: uses Tre's OAuth Claude subscription via `claude -p`. Each
run consumes ~1-3 messages from the 5-hour rate-limit window. No dollar
cost. See feedback/subscription_first_design.md.

Authentication: inherits whatever profile is current via CLAUDE_CONFIG_DIR.
By default, scheduled tasks run under the user's environment and use
`~/.claude` (personal Pro subscription). Switch by setting
CLAUDE_CONFIG_DIR in the scheduled task's environment if you want it on
Team allotment instead.

Usage:
  python weekly-planner.py                # default — generate briefing
  python weekly-planner.py --dry-run      # show what would happen
  python weekly-planner.py --skip-claude  # generate the prompt + context bundle, but don't invoke claude (debugging)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

AGENT_OS = Path(r"Z:\agent-os")
CLONE = Path(r"Z:\Clone")
OUTPUT_PATH = AGENT_OS / "next-session.md"
ARCHIVE_PATH = AGENT_OS / "next-session.archive.md"
LOG_PATH = AGENT_OS / "weekly-planner.log"


def log(level: str, message: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} [{level}] {message}\n"
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="", file=sys.stderr)


def _read_file(p: Path, max_chars: int = 8000) -> str:
    """Read a file safely with size cap."""
    if not p.exists():
        return f"(file not found: {p})"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            return text[:max_chars] + "\n\n[truncated for prompt budget]"
        return text
    except OSError as e:
        return f"(read error on {p}: {e})"


def _tail_log(p: Path, n: int = 50) -> str:
    """Last N lines of a log file."""
    if not p.exists():
        return f"(no log at {p})"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return f"(read error on {p})"


def _list_methodology_files() -> str:
    """Count methodology files per expert."""
    methodology_root = CLONE / "experts"
    if not methodology_root.exists():
        return "(no experts dir)"
    out = []
    for domain_dir in sorted(methodology_root.iterdir()):
        if not domain_dir.is_dir() or domain_dir.name.startswith("_"):
            continue
        for expert_dir in sorted(domain_dir.iterdir()):
            if not expert_dir.is_dir():
                continue
            method_dir = expert_dir / "methodology"
            count = len(list(method_dir.glob("*.md"))) if method_dir.exists() else 0
            out.append(f"  - {domain_dir.name}/{expert_dir.name}: {count} methodology file(s)")
    return "\n".join(out) if out else "(no experts onboarded yet)"


def _recent_clone_log_entries(days: int = 7) -> str:
    """Pull _log.md entries from the last N days."""
    log_file = CLONE / "_log.md"
    if not log_file.exists():
        return "(no _log.md)"
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(read error)"
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    # Naive parse: split on "## [YYYY-MM-DD]" headers
    blocks = []
    current_block = []
    current_date = None
    for line in text.splitlines():
        if line.startswith("## [") and "]" in line:
            if current_block and current_date and current_date >= cutoff:
                blocks.append("\n".join(current_block))
            current_block = [line]
            # Extract date
            try:
                current_date = line[4:14]  # "## [YYYY-MM-DD"
            except IndexError:
                current_date = None
        else:
            current_block.append(line)
    if current_block and current_date and current_date >= cutoff:
        blocks.append("\n".join(current_block))
    return "\n\n".join(blocks) if blocks else f"(no entries in last {days} days)"


def _gather_context() -> dict:
    """Gather everything the briefing prompt needs."""
    return {
        "today": dt.date.today().isoformat(),
        "ai_production_engine_brief": _read_file(
            AGENT_OS / "memory" / "projects" / "ai_production_engine.md",
            max_chars=10000,
        ),
        "user_md": _read_file(AGENT_OS / "memory" / "user.md", max_chars=6000),
        "sol_md": _read_file(AGENT_OS / "memory" / "[NAME].md", max_chars=4000),
        "memory_index": _read_file(AGENT_OS / "memory" / "MEMORY.md", max_chars=4000),
        "recent_clone_log": _recent_clone_log_entries(days=7),
        "methodology_files_summary": _list_methodology_files(),
        "previous_next_session": _read_file(OUTPUT_PATH, max_chars=3000),
        "farmer_route_tail": _tail_log(AGENT_OS / "farmer-route.log", n=15),
        "farmer_youtube_tail": _tail_log(AGENT_OS / "farmer-youtube.log", n=15),
    }


def _build_prompt(ctx: dict) -> str:
    return f"""You are a Claude instance — the Claude instance that loads when agent-os is the context. Your job today is the weekly Sunday-morning briefing for Tre.

The briefing's purpose: when you open a session this week, he should find a file at Z:\\agent-os\\next-session.md that tells him (a) what landed since last week, (b) what the highest-leverage next move is, (c) why that's the move, and (d) what's deferred or waiting.

PRIMARY CONSTRAINTS (do not violate)
====================================

1. Be HONEST about what's actually new vs. unchanged from last week.
2. NEVER recommend committing code in projects with default-ask commit policies (SES, Mosaic). See feedback/never_commit_without_permission.md.
3. NEVER suggest setting ANTHROPIC_API_KEY or quoting dollar costs for Claude inference. See feedback/subscription_first_design.md.
4. NEVER suggest content production that would reveal Tre's identity. See feedback/faceless_production_only.md.
5. you does 5%, [NAME] does 95% — frame work as "I would do X; you'd approve Y" not "you need to do X."
6. Match Tre's tone (see soul.md and anti_patterns.md): no walls of prose, no decorative emojis, structured tables OK, severity glyphs OK.

YOUR INPUTS
===========

TODAY: {ctx['today']}

USER (who you are — abridged):
{ctx['user_md']}

[NAME] (who I am, my self-commitments — abridged):
{ctx['sol_md']}

MEMORY INDEX (what feedback rules / projects exist):
{ctx['memory_index']}

AI PRODUCTION ENGINE PROJECT BRIEF (current state):
{ctx['ai_production_engine_brief']}

RECENT CLONE WIKI ACTIVITY (last 7 days from _log.md):
{ctx['recent_clone_log']}

METHODOLOGY FILES PER EXPERT (current roster state):
{ctx['methodology_files_summary']}

PREVIOUS WEEK'S NEXT-SESSION.MD (if it existed — for continuity):
{ctx['previous_next_session']}

FARMER-ROUTE LAST 15 LOG LINES:
{ctx['farmer_route_tail']}

FARMER-YOUTUBE LAST 15 LOG LINES:
{ctx['farmer_youtube_tail']}

YOUR OUTPUT
===========

Write a complete markdown file. NOT JSON. NOT a tool call. Just write the markdown directly as your response. The first line should be the H1 header. The file will be written verbatim to Z:\\agent-os\\next-session.md.

Required structure:

```
# Next session briefing — generated {ctx['today']}

## What landed this week
(Bullets: new methodology files routed, new experts onboarded, capability gaps closed, etc. Be specific with file paths and counts. If nothing landed, say so plainly.)

## What's closer to ready
(Which capability roadmap items in projects/ai_production_engine.md are now closer to being actionable? Which triangulation thresholds (e.g., N=3 experts in a domain) are within reach? Be specific.)

## Highest-leverage next move
(ONE recommendation. Specific. Estimable. Justify with cross-creator evidence or capability-gap analysis. Don't propose multiple options — pick the one and defend it.)

## Deferred (intentionally not now)
(Items that COULD be next but aren't, and why. Keeps the option visible without diluting focus.)

## Standing rules to remember
(Any feedback rules added or amended this week that affect upcoming work. Quote the rule slug, e.g. [[faceless_production_only]].)

## How to use this briefing
One paragraph: "Open a session when you have energy. Tell me you've read this. I'll execute the highest-leverage next move with the 5/95 split."
```

Constraints on style:
- Tables for comparisons (3+ items)
- Sentence-then-bullets for single facts
- No prose walls
- No decorative emoji
- Severity glyphs OK (🔴🟡🟢) — use sparingly
- Match Tre's voice — direct, peer-to-peer, no salesman energy

Do not include backticks around the output. Just write the markdown directly.
"""


def _invoke_claude(prompt: str, timeout: int = 300) -> str | None:
    claude_path = shutil.which("claude") or shutil.which("claude.exe") or shutil.which("claude.cmd")
    if not claude_path:
        log("ERROR", "claude CLI not found")
        return None

    # No tools needed — this is pure synthesis. Disallow all tools so claude
    # doesn't try to "do" things; it just writes the markdown response.
    #
    # L2 fix (2026-05-27): set CLAUDE_BRAIN_SKIP_HOOKS=1 on subprocess env so the
    # brain hooks no-op for this child process. Otherwise session-start would
    # inject brain context (polluting the planner's neutral perspective) and
    # stop/session-end would capture the planner conversation back into the brain.
    env = os.environ.copy()
    env["CLAUDE_BRAIN_SKIP_HOOKS"] = "1"
    try:
        result = subprocess.run(
            [claude_path, "-p",
             "--no-session-persistence",
             "--disallowed-tools", "Read Write Edit Bash Glob Grep WebFetch WebSearch",
             "--fallback-model", "claude-sonnet-4-6"],
            input=prompt,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(AGENT_OS), timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        log("ERROR", f"claude timed out after {timeout}s")
        return None
    except Exception as e:
        log("ERROR", f"claude invocation crashed: {e}")
        return None

    if result.returncode != 0:
        log("ERROR", f"claude returned non-zero: {result.stderr[:500]}")
        return None

    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly Sunday-morning briefing for Tre.")
    parser.add_argument("--dry-run", action="store_true", help="Build prompt + show what would happen, don't invoke claude or write output.")
    parser.add_argument("--skip-claude", action="store_true", help="Bundle context, write to disk for inspection, but don't actually invoke claude.")
    parser.add_argument("--quiet", action="store_true", help="Suppress stderr logging.")
    args = parser.parse_args()

    log("INFO", f"weekly-planner starting (DryRun={args.dry_run}, SkipClaude={args.skip_claude})")

    ctx = _gather_context()
    prompt = _build_prompt(ctx)
    log("INFO", f"context bundle: prompt ~{len(prompt):,} chars")

    if args.dry_run:
        log("INFO", f"dry-run — prompt would be sent to claude, output to {OUTPUT_PATH}")
        return 0

    if args.skip_claude:
        debug_path = AGENT_OS / "weekly-planner-prompt.txt"
        debug_path.write_text(prompt, encoding="utf-8")
        log("INFO", f"skip-claude — wrote prompt to {debug_path} for inspection")
        return 0

    log("INFO", "invoking claude -p for briefing synthesis...")
    output = _invoke_claude(prompt)

    if not output:
        log("ERROR", "claude returned empty or failed; previous next-session.md preserved")
        return 1

    # Archive the previous briefing before overwriting
    if OUTPUT_PATH.exists():
        prev = OUTPUT_PATH.read_text(encoding="utf-8", errors="replace")
        try:
            archive_existing = ARCHIVE_PATH.read_text(encoding="utf-8", errors="replace") if ARCHIVE_PATH.exists() else ""
        except OSError:
            archive_existing = ""
        ARCHIVE_PATH.write_text(
            f"---\n# Archived {ctx['today']}\n---\n\n{prev}\n\n{archive_existing}",
            encoding="utf-8",
        )
        log("INFO", f"archived previous briefing to {ARCHIVE_PATH}")

    OUTPUT_PATH.write_text(output, encoding="utf-8")
    log("INFO", f"wrote {len(output):,} chars to {OUTPUT_PATH}")

    # Deliver the brief to Slack (no-op if webhook not configured yet).
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from notify_slack import post_slack
        sent = post_slack(output, title=f"[NAME] — weekly brief ({ctx['today']})")
        if sent is True:
            log("INFO", "posted weekly brief to Slack")
        elif sent is None:
            log("INFO", "Slack not configured (no webhook) — brief written to file only")
        else:
            log("WARN", "Slack post failed — brief written to file only")
    except Exception as e:
        log("WARN", f"Slack notify skipped: {type(e).__name__}: {e}")

    log("INFO", "weekly-planner done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
