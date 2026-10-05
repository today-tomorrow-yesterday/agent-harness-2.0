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

TWO ROUTES (optional). post_slack(..., route="alerts") — the default, so every
existing caller is unchanged — is for real signal: something broke, something
recovered, something needs a human. route="digest" is for routine, low-urgency
traffic (daily digests, weekly briefs, idea nudges) that belongs in a quiet channel
you can mute. The digest webhook resolves from:
  1. env var  SLACK_WEBHOOK_DIGEST_URL
  2. file     $SLACK_WEBHOOK_DIGEST_FILE, else bin/secrets/slack-webhook-digest.txt
With only ONE webhook configured, digest traffic FALLS BACK to the alerts webhook
with an ASCII "[digest]" title marker — a message is never lost to a missing second
channel — and moves to the quiet channel automatically once its webhook exists.

DRY-RUN: set HARNESS_SLACK_DRY_RUN=1 (or pass --dry-run on the CLI) and nothing is
POSTed — the would-be send is described on stderr instead (route, title, size; never
the webhook). For tests and for rehearsing a job without paging anyone.

The webhook URLs are secrets: they are NEVER printed to stdout/stderr/logs.

Usage:
    python notify_slack.py --text "hello"
    python notify_slack.py --file path/to/brief.md --title "Sunday brief"
    python notify_slack.py --text "digest..." --route digest
    python notify_slack.py --text "hello" --dry-run
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

_SECRETS_DIR = Path(__file__).resolve().parent / "secrets"
WEBHOOK_FILE = Path(os.environ.get("SLACK_WEBHOOK_FILE")
                    or (_SECRETS_DIR / "slack-webhook.txt"))
# Optional second channel for routine traffic. Absent by default; until it exists,
# digest-route messages fall back to the main webhook.
DIGEST_WEBHOOK_FILE = Path(os.environ.get("SLACK_WEBHOOK_DIGEST_FILE")
                           or (_SECRETS_DIR / "slack-webhook-digest.txt"))
ROUTES = ("alerts", "digest")
DRY_RUN_ENV = "HARNESS_SLACK_DRY_RUN"
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


_WITHHELD = "[message withheld: the secret scrubber could not be loaded]"


def _egress_scrub(text: str) -> str:
    """Last-chance secret redaction before anything leaves the box. This is the true
    egress chokepoint — EVERY Slack post passes through here regardless of caller
    (digest/weekly-planner/alert), so a raw runner.db payload or a token in a traceback
    can't ship off-box.

    Uses the canonical execution.redaction.scrub (exact registered values + the shared
    shape list). If that import fails, it falls back to the SAME canonical shape list
    (execution/secret_patterns.py, loaded by file path) — never to a hand-copied
    subset, because a weaker fallback on the one path that leaves the machine is
    exactly how the scrubbers drifted before. If even that cannot load, the body is
    withheld rather than sent unscrubbed (fail closed)."""
    try:
        bin_dir = str(Path(__file__).resolve().parent)
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
        from execution.redaction import scrub
        return scrub(text)
    except Exception:  # noqa: BLE001
        pass
    try:
        import importlib.util
        path = Path(__file__).resolve().parent / "execution" / "secret_patterns.py"
        spec = importlib.util.spec_from_file_location("_harness_secret_patterns", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.scrub_shapes(text)
    except Exception:  # noqa: BLE001
        return _WITHHELD


def _read_hook(env_var: str, path: Path) -> str | None:
    url = (os.environ.get(env_var) or "").strip()
    if _looks_valid(url):
        return url
    if path.exists():
        val = path.read_text(encoding="utf-8").strip()
        if _looks_valid(val):
            return val
    return None


def _resolve_webhook(route: str = "alerts") -> tuple[str | None, str]:
    """Resolve the webhook for a route. Returns (url, resolved_route): resolved_route
    names the channel the message will actually hit. An unconfigured digest webhook
    falls back to the alerts webhook (never lose a message to a missing config), then
    to no-op. The alerts route never uses the digest webhook."""
    if route == "digest":
        url = _read_hook("SLACK_WEBHOOK_DIGEST_URL", DIGEST_WEBHOOK_FILE)
        if url:
            return url, "digest"
    url = _read_hook("SLACK_WEBHOOK_URL", WEBHOOK_FILE)
    if url:
        return url, "alerts"
    return None, "alerts"


def _dry_run() -> bool:
    return (os.environ.get(DRY_RUN_ENV) or "").strip().lower() in ("1", "true", "yes")


def post_slack(text: str, title: str | None = None, route: str = "alerts") -> bool | None:
    """Post to Slack. True=sent (or dry-run), False=error, None=not configured (no-op).

    route: "alerts" (default — real signal) or "digest" (routine, mutable channel).
    Backward-compatible: existing post_slack(text, title) callers land on the alerts
    webhook exactly as before.
    """
    if route not in ROUTES:
        route = "alerts"                  # a typo'd route goes to the safe channel
    url, resolved = _resolve_webhook(route)
    if not url:
        return None
    if route == "digest" and resolved == "alerts":
        # Digest webhook not wired: mark the fallback with a low-noise ASCII sentinel
        # so routine traffic is filterable on the alerts channel (ASCII, not an emoji:
        # a cp1252 console or log drops emoji silently).
        title = f"[digest] {title}" if title else "[digest]"
    text = to_slack_mrkdwn(text)          # normalize GH-markdown -> Slack mrkdwn so it renders
    if title:
        text = f"*{title}*\n{text}"
    text = _egress_scrub(text)            # redact secrets at the egress chokepoint (last line before off-box)
    # Slack hard-truncates ~40k chars; keep payloads sane.
    if len(text) > 38000:
        text = text[:38000] + "\n…(truncated)"
    if _dry_run():
        print(f"[notify_slack] DRY-RUN route={route} resolved={resolved} "
              f"title={title!r} chars={len(text)} — not sent", file=sys.stderr)
        return True
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Post a message to Slack via Incoming Webhook.")
    ap.add_argument("--text", help="Message text.")
    ap.add_argument("--file", help="Read message text from this file.")
    ap.add_argument("--title", help="Optional bold title line.")
    ap.add_argument("--route", choices=ROUTES, default="alerts",
                    help="alerts (default) or digest (falls back to alerts until its webhook exists).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Describe the would-be send on stderr instead of POSTing.")
    args = ap.parse_args(argv)

    if args.dry_run:
        os.environ[DRY_RUN_ENV] = "1"
    text = args.text or ""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    if not text.strip():
        print("[notify_slack] nothing to send (no --text/--file).", file=sys.stderr)
        return 1

    result = post_slack(text, args.title, route=args.route)
    if result is None:
        print("[notify_slack] Slack not configured (no webhook) — skipping.", file=sys.stderr)
        return 2
    if result:
        print("[notify_slack] sent." if not _dry_run() else "[notify_slack] dry-run ok.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
