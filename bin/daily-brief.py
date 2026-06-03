#!/usr/bin/env python3
"""
daily-brief.py — assemble a cheap daily digest of agent-os activity and post it
to Slack. LLM-FREE (zero subscription/API cost): it just reads the farmer logs,
the CLONE inbox/news lane, and the roster, then formats a short brief.

Runs after the morning farmers (06:00-06:30), e.g. 07:00 daily. The deep
synthesis brief stays weekly (Weekly-Planner, Sunday). This is the daily pulse.

Posts via notify_slack.py (no-op if the webhook isn't configured yet) and also
writes Z:\\agent-os\\daily-brief.md for the record.

Usage:
    python daily-brief.py            # assemble + post + write file
    python daily-brief.py --print    # assemble + print to stdout only (no Slack)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

AGENT_OS = Path(r"Z:\agent-os")
CLONE = Path(r"Z:\Clone")
INBOX = CLONE / "00_inbox"
NEWS_LOG = CLONE / "news" / "_log.md"
OUT_FILE = AGENT_OS / "daily-brief.md"

FARMER_LOGS = {
    "YouTube": AGENT_OS / "farmer-youtube.log",
    "Web": AGENT_OS / "farmer-web.log",
    "Route": AGENT_OS / "farmer-route.log",
}


def _last_done_line(log_path: Path) -> str:
    """Last summary line from a farmer log (the 'done.' line), else last line."""
    if not log_path.exists():
        return "(no log)"
    try:
        lines = [ln.strip() for ln in log_path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    except OSError:
        return "(unreadable)"
    if not lines:
        return "(empty)"
    for ln in reversed(lines):
        if "done." in ln:
            return ln.split("] ", 1)[-1] if "] " in ln else ln
    return lines[-1][:160]


def _inbox_pending() -> int:
    if not INBOX.exists():
        return 0
    return sum(1 for p in INBOX.iterdir() if p.is_dir() and not p.name.startswith("_"))


def _news_recent(n: int = 5) -> list[str]:
    if not NEWS_LOG.exists():
        return []
    lines = [ln.strip() for ln in NEWS_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
             if ln.strip().startswith("- [")]
    return lines[-n:]


def _roster_count() -> int:
    try:
        return len(list((CLONE / "experts").glob("*/*/_index.md")))
    except OSError:
        return 0


def _methodology_count() -> int:
    try:
        return len(list((CLONE / "experts").glob("*/*/methodology/*.md")))
    except OSError:
        return 0


def build_brief() -> str:
    today = dt.datetime.now().strftime("%Y-%m-%d")
    lines = [f"[NAME] — daily brief ({today})", ""]

    lines.append("*Farmers (last run):*")
    for name, path in FARMER_LOGS.items():
        lines.append(f"• {name}: {_last_done_line(path)}")
    lines.append("")

    pending = _inbox_pending()
    lines.append(f"*Inbox:* {pending} folder(s) pending routing.")
    lines.append(f"*Roster:* {_roster_count()} experts · {_methodology_count()} methodology pages.")

    news = _news_recent()
    if news:
        lines.append("")
        lines.append("*News lane (auto-skipped from methodology):*")
        lines.extend(f"  {n}" for n in news)

    lines.append("")
    lines.append("_Deep synthesis brief: Sundays (next-session.md). Full inbox: /clone-route._")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble + post the daily agent-os brief to Slack.")
    ap.add_argument("--print", dest="print_only", action="store_true",
                    help="Print the brief to stdout only; don't post or write the file.")
    args = ap.parse_args()

    brief = build_brief()

    if args.print_only:
        print(brief)
        return 0

    try:
        OUT_FILE.write_text(brief, encoding="utf-8")
    except OSError as e:
        print(f"[daily-brief] could not write {OUT_FILE}: {e}", file=sys.stderr)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from notify_slack import post_slack
    sent = post_slack(brief)
    if sent is None:
        # Not a failure: the brief was assembled + written; Slack is optional until
        # the webhook is configured. Return 0 so the scheduled task shows success.
        print("[daily-brief] Slack not configured (no webhook) — wrote file only.", file=sys.stderr)
        return 0
    print("[daily-brief] sent." if sent else "[daily-brief] Slack post failed.", file=sys.stderr)
    return 0 if sent else 1


if __name__ == "__main__":
    sys.exit(main())
