#!/usr/bin/env python3
"""
notify_slack.py — post a message to Slack via an Incoming Webhook.

Reusable helper for harness background tasks (Weekly-Planner, digest, alerts).
Headless-safe: a plain HTTPS POST, no interactive auth, works under the scheduler
/ `claude -p` where the interactive Slack MCP is unavailable.

Webhook resolution (first hit wins):
  1. env var  SLACK_WEBHOOK_URL
  2. file     $SLACK_WEBHOOK_FILE, else bin/secrets/slack-webhook.txt (gitignored)

If neither is set (or the file still holds the placeholder, or the value is not a
real https://hooks.slack.com/ URL), this NO-OPS and returns exit code 2 — callers
treat that as "Slack not configured, skip" so the briefs still write their files
even before the webhook is wired.

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
import re
import sys
import urllib.request
from pathlib import Path

WEBHOOK_FILE = Path(os.environ.get("SLACK_WEBHOOK_FILE")
                    or (Path(__file__).resolve().parent / "secrets" / "slack-webhook.txt"))
_PLACEHOLDER_MARK = "PASTE_YOUR"  # the scaffolded placeholder contains this
# Real Slack Incoming Webhooks live under this host; anything else (typo,
# corrupted file, leftover placeholder) is rejected rather than POSTed to.
_WEBHOOK_PREFIX = "https://hooks.slack.com/"


def _looks_valid(url: str) -> bool:
    return bool(url) and _PLACEHOLDER_MARK not in url and url.startswith(_WEBHOOK_PREFIX)


def to_slack_mrkdwn(text: str) -> str:
    """Convert the GitHub-flavored markdown our builders emit into Slack 'mrkdwn'
    so it actually renders in Slack:
      '# Header' / '## Header'  -> '*Header*' (Slack has no header syntax)
      '**bold**'                -> '*bold*'   (Slack bold is single-asterisk)
      '- bullet'                -> '• bullet'
    Emoji, code blocks, and already-single-asterisk *bold* pass through untouched.
    The .md files keep GitHub markdown; only the Slack payload is normalized.
    """
    out = []
    for line in text.splitlines():
        h = re.match(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$", line)
        if h:
            out.append(f"*{h.group(1)}*")
            continue
        line = re.sub(r"^(\s*)[-]\s+", r"\1• ", line)     # dash bullets -> dots
        line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)     # **bold** -> *bold*
        out.append(line)
    return "\n".join(out)


def _egress_scrub(text: str) -> str:
    """Last-chance secret redaction before anything leaves the box. This is the true
    egress chokepoint — EVERY Slack post passes through here regardless of caller
    (digest/weekly-planner/alert), so a raw runner.db payload or a token in a traceback
    can't ship off-box. Uses the canonical execution.redaction.scrub; falls back to a
    minimal token-shape mask if that import is unavailable."""
    try:
        import sys as _sys
        from pathlib import Path as _P
        _sys.path.insert(0, str(_P(__file__).resolve().parent))
        from execution.redaction import scrub
        return scrub(text)
    except Exception:
        import re as _re
        return _re.sub(
            r"(Bearer\s+\S+|sk-[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9-]+"
            r"|eyJ[\w-]+\.[\w-]+\.[\w-]+|\b[A-Fa-f0-9]{32,}\b)", "[redacted]", text or "")


def _resolve_webhook() -> str | None:
    url = (os.environ.get("SLACK_WEBHOOK_URL") or "").strip()
    if _looks_valid(url):
        return url
    if WEBHOOK_FILE.exists():
        val = WEBHOOK_FILE.read_text(encoding="utf-8").strip()
        if _looks_valid(val):
            return val
    return None


def post_slack(text: str, title: str | None = None) -> bool | None:
    """Post to Slack. True=sent, False=error, None=not configured (no-op)."""
    url = _resolve_webhook()
    if not url:
        return None
    text = to_slack_mrkdwn(text)          # normalize GH-markdown -> Slack mrkdwn so it renders
    if title:
        text = f"*{title}*\n{text}"
    text = _egress_scrub(text)            # redact secrets at the egress chokepoint (last line before off-box)
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
