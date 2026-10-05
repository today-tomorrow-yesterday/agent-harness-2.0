#!/usr/bin/env python3
"""weekly-planner.py — a weekly "what's next" briefing, generated from your memory.

Reads your `memory/` (who you are, your project briefs, standing rules, and last
week's briefing), asks Claude to synthesize the highest-leverage next moves, and
writes `next-session.md` at the repo root. Runs on your Claude subscription via
`claude -p` (no API key). Cross-platform. Register it weekly via bin/scheduler.

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
    env = os.environ.copy()
    env["CLAUDE_BRAIN_SKIP_HOOKS"] = "1"  # keep the planner's child session out of the brain
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Weekly 'what's next' briefing from your memory.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build the prompt and report; don't call Claude or write output.")
    args = ap.parse_args()

    ctx = _gather_context()
    prompt = _build_prompt(ctx)
    log("INFO", f"weekly-planner: prompt ~{len(prompt):,} chars")

    if args.dry_run:
        log("INFO", f"dry-run - would write briefing to {OUTPUT_PATH}")
        return 0

    out = _invoke_claude(prompt)
    if not out:
        log("ERROR", "no output from claude; leaving previous briefing in place")
        return 1

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
