#!/usr/bin/env python3
"""
notify_slack.py — post a message to Slack via an Incoming Webhook.

Reusable helper for agent-os background tasks (Weekly-Planner, Daily-Brief).
Headless-safe: a plain HTTPS POST, no interactive auth, works under Task
Scheduler / `claude -p` where the interactive Slack MCP is unavailable.

Webhook resolution (first hit wins):
  1. env var  SLACK_WEBHOOK_URL
  2. file     Z:\\agent-os\\bin\\secrets\\slack-webhook.txt  (gitignored)

If neither is set (or the file still holds the placeholder), this NO-OPS and
returns exit code 2 — callers treat that as "Slack not configured, skip" so
the briefs still write their files even before the webhook is wired.

The webhook URL is a secret: it is NEVER printed to stdout/stderr/logs.

Usage:
    python notify_slack.py --text "hello"
    python notify_slack.py --file path/to/brief.md --title "Sunday brief"
    from notify_slack import post_slack; post_slack("hi")   # returns True/False/None
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

WEBHOOK_FILE = Path(__file__).resolve().parent / "secrets" / "slack-webhook.txt"
_PLACEHOLDER_MARK = "PASTE_YOUR"  # the scaffolded placeholder contains this


def _resolve_webhook() -> str | None:
    url = (os.environ.get("SLACK_WEBHOOK_URL") or "").strip()
    if url:
        return url
    if WEBHOOK_FILE.exists():
        val = WEBHOOK_FILE.read_text(encoding="utf-8").strip()
        if val and _PLACEHOLDER_MARK not in val and val.startswith("http"):
            return val
    return None


def post_slack(text: str, title: str | None = None) -> bool | None:
    """Post to Slack. True=sent, False=error, None=not configured (no-op)."""
    url = _resolve_webhook()
    if not url:
        return None
    if title:
        text = f"*{title}*\n{text}"
    # Slack hard-truncates ~40k chars; keep payloads sane.
    if len(text) > 38000:
        text = text[:38000] + "\n…(truncated)"
    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        # Never include `url` in the message — it's the secret.
        print(f"[notify_slack] POST failed: {type(e).__name__}: {e}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Post a message to Slack via Incoming Webhook.")
    ap.add_argument("--text", help="Message text.")
    ap.add_argument("--file", help="Read message text from this file.")
    ap.add_argument("--title", help="Optional bold title line.")
    args = ap.parse_args()

    text = args.text or ""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    if not text.strip():
        print("[notify_slack] nothing to send (no --text/--file).", file=sys.stderr)
        return 1

    result = post_slack(text, args.title)
    if result is None:
        print("[notify_slack] Slack not configured (no webhook) — skipping.", file=sys.stderr)
        return 2
    if result:
        print("[notify_slack] sent.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
