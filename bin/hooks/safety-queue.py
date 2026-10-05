#!/usr/bin/env python3
"""safety-queue.py -- PreToolUse(Bash|PowerShell) "ask a human and wait" queue for unattended runs.

Register with:  python bin/register_hook.py safety-queue
Review with:    the /safety-review skill (skills/safety-review/)

The tier BELOW pre-tool-guard.py's hard deny. pre-tool-guard blocks things that are destructive
or irreversible to YOU (rm -rf /, force-push, DROP TABLE, curl|sh). This hook does not duplicate
any of that. It adds a PAUSE-FOR-HUMAN tier for a narrow, conservative set of actions that are
outward-facing or irreversible to OTHERS:

  * sending email or messages (sendmail, Send-MailMessage, aws ses/sns/sqs send, ...)
  * external HTTP writes (POST/PUT/PATCH/DELETE, or any request carrying a body) to a
    non-localhost host
  * publishing packages or images (npm/pnpm/yarn publish, twine upload, cargo publish,
    gem push, docker push)
  * public GitHub actions (gh release/pr/issue/gist create)
  * production deploys (vercel --prod, netlify deploy --prod, wrangler deploy)

None of those is wrong enough to hard-deny, but in a headless run there is no human to approve
them. So the hook records the request in forge/safety/queue.json, denies THIS attempt (exit 2),
optionally pings Slack, and tells the model to move on. A human works the queue later.

INERT unless HARNESS_UNATTENDED=1. Interactive sessions are never touched. Ordinary file
reads/writes, plain GETs/downloads and localhost traffic are never queued.

Contract:
  * Queue+deny = exit 2 + reason on stderr. Everything else = exit 0.
  * FAIL-SAFE before a match: any internal error -> exit 0, so a queue bug never blocks a
    legitimate headless run. AFTER a match the deny is kept even if writing the queue or the
    notification fails -- side effects are best-effort, the deny is not.
  * Off switch: HARNESS_HOOKS_DISABLED=1. Slack ping off: HARNESS_SAFETY_NOTIFY=off.
  * Threat model: accidents in unattended runs, not adversaries. Quoted text is blanked before
    matching verbs, so a command that merely MENTIONS an outward action passes.

State (gitignore `forge/safety/`):
  forge/safety/queue.json    JSON array of PENDING requests
                             {id, ts, status, label, reason, command, cwd, session_id}
  forge/safety/history.json  append-only event log (queued / approved / denied / cleared)
  HARNESS_SAFETY_DIR overrides the directory.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_common import (  # noqa: E402
    BIN, ROOT, deny, hooks_disabled, read_payload, strip_quoted, tool_input, unattended,
)


def safety_dir() -> Path:
    override = os.environ.get("HARNESS_SAFETY_DIR")
    return Path(override).expanduser() if override else ROOT / "forge" / "safety"


# hosts that are NOT outward-facing (a POST to your own box is not "irreversible to others")
LOCALHOST = re.compile(
    r"^(localhost|127(?:\.\d{1,3}){3}|0\.0\.0\.0|::1|host\.docker\.internal)$", re.I
)

SIMPLE_TIER2 = [
    # sending email / messages
    (r"(?i)\bSend-MailMessage\b", "sending email"),
    (r"(?i)\b(sendmail|msmtp|mailx|swaks|sendemail|ssmtp)\b", "sending email"),
    (r"(?i)\bmutt\b[^|;&]*\s-s\b", "sending email (mutt)"),
    (r"(?i)\bmail\s+-s\b", "sending email"),
    (r"(?i)\baws\s+ses\s+send-(email|raw-email|templated-email)\b", "sending email via AWS"),
    (r"(?i)\baws\s+sns\s+publish\b", "publishing a message via SNS"),
    (r"(?i)\baws\s+sqs\s+send-message\b", "sending a message via SQS"),
    # publishing / releasing packages & artifacts
    (r"(?i)\b(npm|pnpm|yarn)\s+publish\b", "publishing a package to a registry"),
    (r"(?i)\btwine\s+upload\b", "publishing a package to PyPI"),
    (r"(?i)\bcargo\s+publish\b", "publishing a crate to crates.io"),
    (r"(?i)\bgem\s+push\b", "publishing a gem to RubyGems"),
    (r"(?i)\bdocker\s+push\b", "pushing an image to a container registry"),
    (r"(?i)\bgh\s+release\s+create\b", "creating a public GitHub release"),
    (r"(?i)\bgh\s+(pr|issue)\s+create\b", "opening an outward-facing GitHub PR/issue"),
    (r"(?i)\bgh\s+gist\s+create\b", "publishing a gist"),
    # deploying to production (preview deploys are fine)
    (r"(?i)\bvercel\b[^|;&]*\s--prod\b", "deploying to production (vercel)"),
    (r"(?i)\bnetlify\s+deploy\b[^|;&]*\s--prod\b", "deploying to production (netlify)"),
    (r"(?i)\bwrangler\s+(deploy|publish)\b", "deploying a Cloudflare Worker"),
]
SIMPLE_TIER2 = [(re.compile(p), r) for p, r in SIMPLE_TIER2]

_NET_CLIENT = re.compile(
    r"(?i)\b(curl|wget|invoke-webrequest|iwr|invoke-restmethod|irm|http|xh|httpie)\b"
)
_NET_METHOD = re.compile(
    r"(?i)("
    r"-X\s*\"?(POST|PUT|PATCH|DELETE)"                 # curl -X POST
    r"|--request\s*\"?(POST|PUT|PATCH|DELETE)"          # curl --request PUT
    r"|-Method\s+\"?(POST|PUT|PATCH|DELETE)"            # PowerShell -Method Post
    r"|--method\s*=?\s*\"?(POST|PUT|PATCH|DELETE)"      # wget --method=PUT
    r"|(?<![\w-])(--data-raw|--data-binary|--data-urlencode|--data|-d|--form|-F"
    r"|--upload-file|--post-data|--post-file|-InFile|-Body)\b"  # a body implies a write
    r")"
)
_URL = re.compile(r"https?://[^\s\"'`>)\]]+", re.I)


def _external_host(raw: str) -> str | None:
    """The first non-localhost host among the URLs in the raw command, else None."""
    for u in _URL.findall(raw):
        authority = re.sub(r"(?i)^https?://", "", u).split("/")[0].split("@")[-1]
        if authority.startswith("["):                       # [::1]:8080
            host = authority[1:].split("]")[0]
        else:
            host = authority.split(":")[0]
        if host and not LOCALHOST.match(host):
            return host
    return None


def detect_tier2(raw: str, stripped: str) -> tuple[str, str] | None:
    """(label, reason) if the command is a pause-for-human action, else None."""
    for pat, reason in SIMPLE_TIER2:
        if pat.search(stripped):
            return (re.sub(r"\W+", "_", reason).strip("_")[:40], reason)
    # The client must be a real command token (found in the stripped text), but URLs are read
    # from the raw text: stripping quotes would remove a quoted URL itself.
    # The method may itself be quoted (`-X "POST"`), so it is read with quote characters removed.
    if _NET_CLIENT.search(stripped) and _NET_METHOD.search(re.sub(r"[\"']", "", raw)):
        host = _external_host(raw)
        if host:
            return ("external_http_write",
                    f"an external HTTP write (POST/PUT/PATCH/DELETE) to {host}")
    return None


# ---- persistence (atomic rewrite of a JSON array) ------------------------------------------

def load_array(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def atomic_write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def append_record(path: Path, record: dict) -> None:
    arr = load_array(path)
    arr.append(record)
    atomic_write(path, arr)


# ---- notification (best-effort; must never fail or block the hook) ------------------------

def notify(req_id: str, reason: str) -> None:
    """Fire-and-forget Slack ping through bin/notify_slack.py, if a webhook is configured there.

    Runs detached so a slow network cannot stall the hook, and with hooks disabled in the child's
    environment so it can never re-enter this chain. The command text is NOT sent -- only the id
    and the human-readable reason.
    """
    if os.environ.get("HARNESS_SAFETY_NOTIFY", "").lower() in ("off", "0", "false"):
        return
    script = BIN / "notify_slack.py"
    if not script.is_file():
        return
    env = dict(os.environ, HARNESS_HOOKS_DISABLED="1", CLAUDE_BRAIN_SKIP_HOOKS="1")
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL, "env": env}
    if os.name == "nt":
        kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(
            [sys.executable, str(script), "--title", "Safety review queue",
             "--text", f"Paused (unattended): {reason}. Review with /safety-review [{req_id}]."],
            **kwargs,
        )
    except Exception:
        pass


# ---- main ----------------------------------------------------------------------------------

def main() -> int:
    if hooks_disabled() or not unattended():
        return 0
    data = read_payload()
    if data is None:
        return 0
    command = tool_input(data).get("command", "")
    if not isinstance(command, str) or not command:
        return 0

    match = detect_tier2(command, strip_quoted(command))
    if not match:
        return 0

    # --- MATCHED. From here the deny is guaranteed; side effects are best-effort. ---
    label, reason = match
    req_id = "q_" + uuid.uuid4().hex[:10]
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session_id = str(data.get("session_id", ""))
    try:
        d = safety_dir()
        append_record(d / "queue.json", {
            "id": req_id, "ts": ts, "status": "pending", "label": label, "reason": reason,
            "command": command, "cwd": os.getcwd(), "session_id": session_id,
        })
        append_record(d / "history.json", {
            "ts": ts, "id": req_id, "event": "queued", "label": label, "reason": reason,
            "command": command, "session_id": session_id,
        })
    except Exception:
        pass
    try:
        notify(req_id, reason)
    except Exception:
        pass

    return deny(
        f"PAUSED by safety-queue (unattended): this is {reason}, which needs a human's OK and "
        f"no one is present. Request QUEUED as {req_id} for review (/safety-review). Do NOT "
        f"retry or work around this -- move on to other work and leave this action for the queue."
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-safe: a queue bug must never block a headless run
