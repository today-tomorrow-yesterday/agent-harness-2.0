#!/usr/bin/env python3
"""pre-tool-guard.py -- PreToolUse(Bash|PowerShell) deny-guard for destructive/irreversible commands.

Register with:  python bin/register_hook.py pre-tool-guard

What it blocks (exit 2, reason on stderr):
  * git history rewrites and force operations: force-push (incl. `+refspec`), rebase,
    filter-branch/filter-repo, `commit --amend`, `reset --hard`, deleting a remote branch
  * recursive force-delete of a filesystem root, or of an absolute path OUTSIDE the session's
    working directory (bash `rm -rf` and PowerShell `Remove-Item -Recurse -Force` + aliases)
  * disk-level writes (mkfs, dd to /dev/...)
  * piping a download straight into a shell (`curl | sh`, `iwr | iex`)
  * destructive SQL (DROP TABLE/DATABASE/SCHEMA, TRUNCATE TABLE)
  * recursive chmod/chown on a root path
  * `git commit` when the STAGED diff contains a secret shape (private key, AWS key id,
    `sk-` API key, GitHub token) -- the value is never echoed
  * in unattended runs (HARNESS_UNATTENDED=1): every `git commit` / `git push`, because no human
    is present to approve them

What it deliberately does NOT block: plain `git commit` / `git add` in interactive sessions (commit
policy is a per-project decision), `--force-with-lease`, deletes inside the working directory.

Threat model: accidents, not adversaries. Quoted strings are blanked before matching, so data that
merely MENTIONS a destructive command (a grep pattern, echo text, a commit message) passes.
Deliberate quoting evasion is out of scope for a guardrail.

Contract:
  * Deny = exit 2 + reason on stderr. Allow = exit 0.
  * FAIL-SAFE: any internal error -> exit 0. A guard bug must never brick a session.
  * Off switch: HARNESS_HOOKS_DISABLED=1.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_common import (  # noqa: E402
    deny, hooks_disabled, read_payload, same_or_under, strip_quoted, tool_input, unattended,
)

ASK = ("If this action is truly intended, get the user's explicit approval in chat for this exact "
       "command, let them run it themselves, or narrow the scope.")

DENY = [
    # -- git history rewrite / force ops
    (r"\bgit\s+push\b[^|;&]*(--force\b(?!-with-lease)|\s-f\b)",
     "git force-push rewrites shared history. Use --force-with-lease after explicit approval."),
    (r"\bgit\s+push\b[^|;&]*\s\+\S+",
     "git push with a +refspec is a force-push in disguise."),
    (r"\bgit\s+(rebase|filter-branch|filter-repo)\b",
     "git history rewrite."),
    (r"\bgit\s+commit\b[^|;&]*--amend",
     "commit --amend rewrites history. Prefer a new commit."),
    (r"\bgit\s+reset\b[^|;&]*--hard",
     "git reset --hard discards local work irrecoverably. Use git stash instead."),
    (r"\bgit\s+push\b[^|;&]*(--delete|\s:\S+)",
     "deleting a remote branch is outward-facing and irreversible for others."),
    # -- filesystem (bash)
    (r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)[a-zA-Z]*\s+(/|~|\$HOME|[A-Za-z]:[\\/])(\s|$)",
     "recursive force-delete of a filesystem root."),
    (r"\bmkfs\b|\bdd\s+[^|;&]*of=/dev/",
     "disk-level destructive operation."),
    # -- filesystem (PowerShell; incl. aliases rm/ri/del/erase and truncated -Fo/-Rec flags)
    (r"(?i)\b(remove-item|ri|del|erase|rm)\b(?=[^|;]*\s-rec\w*)(?=[^|;]*\s-fo\w*)[^|;]*\s([A-Za-z]:[\\/]|/|~)(\s|$|[\\/])",
     "PowerShell recursive force-delete of a root path."),
    # -- remote code execution
    (r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh|python3?)\b",
     "piping a download straight into a shell executes unreviewed remote code. Download, read, then run."),
    (r"(?i)\b(iwr|invoke-webrequest|invoke-restmethod|irm)\b[^|]*\|\s*(iex|invoke-expression)\b",
     "PowerShell download-piped-to-iex executes unreviewed remote code."),
    # -- SQL
    (r"(?i)\b(drop\s+(table|database|schema)|truncate\s+table)\b",
     "destructive SQL. Needs explicit approval with the exact statement quoted."),
    # -- mass permission changes on roots
    (r"\b(chmod|chown)\s+-[a-zA-Z]*R[a-zA-Z]*\s+[^;|&]*\s(/|~|\$HOME)(\s|$)",
     "recursive permission change on a root path."),
]
DENY = [(re.compile(p), r) for p, r in DENY]

RM_RF = re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)[a-zA-Z]*\s+([^|;&]*)")
PS_RM = re.compile(
    r"(?i)\b(?:remove-item|ri|del|erase|rm)\b(?=[^|;]*\s-rec\w*)(?=[^|;]*\s-fo\w*)([^|;&]*)"
)
ABSOLUTE = re.compile(r"^(/|~|\$HOME|[A-Za-z]:[\\/])")

SECRET_PATTERNS = [re.compile(p) for p in (
    r"-----BEGIN[ A-Z]*PRIVATE KEY-----",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bsk-[A-Za-z0-9]{20,}\b",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
)]


def outside_workspace(raw_targets: str) -> bool:
    """Does any absolute target lie outside the session's working directory?"""
    project = os.getcwd()
    for tok in raw_targets.split():
        if tok.startswith("-") or not ABSOLUTE.match(tok):
            continue
        tok = os.path.expandvars(os.path.expanduser(tok))
        if not same_or_under(tok, project):
            return True
    return False


def staged_secrets(command: str) -> bool:
    """On `git commit`, scan the staged diff's ADDED lines for secret shapes."""
    if not re.search(r"\bgit\s+commit\b", command):
        return False
    try:
        r = subprocess.run(
            ["git", "diff", "--cached", "-U0"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8,
        )
    except Exception:
        return False
    if r.returncode != 0:
        return False
    for line in r.stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            if any(p.search(line) for p in SECRET_PATTERNS):
                return True
    return False


def evaluate(command: str) -> str | None:
    """Return a denial reason, or None to allow. Pure apart from the staged-diff read."""
    if not command:
        return None
    stripped = strip_quoted(command)

    if unattended() and re.search(r"\bgit\s+(commit|push)\b", stripped):
        return ("BLOCKED by pre-tool-guard (unattended mode): git commit/push cannot be approved "
                "with no human present. Leave the change uncommitted for interactive review.")

    for pattern, reason in DENY:
        if pattern.search(stripped):
            return f"BLOCKED by pre-tool-guard: {reason}\n{ASK}"

    m = RM_RF.search(stripped)
    if m and outside_workspace(m.group(2)):
        return ("BLOCKED by pre-tool-guard: recursive force-delete targeting an absolute path "
                f"outside the current workspace.\n{ASK}")
    pm = PS_RM.search(stripped)
    if pm and outside_workspace(pm.group(1)):
        return ("BLOCKED by pre-tool-guard: PowerShell recursive force-delete outside the current "
                f"workspace.\n{ASK}")

    if staged_secrets(stripped):
        return ("BLOCKED by pre-tool-guard: the staged diff contains what looks like a secret "
                "(private key / AWS / API / GitHub token shape -- value not shown). Unstage it, "
                "move it to bin/secrets/keyring.env (gitignored), then commit.")
    return None


def main() -> int:
    if hooks_disabled():
        return 0
    data = read_payload()
    if data is None:
        return 0
    command = tool_input(data).get("command", "")
    if not isinstance(command, str):
        return 0
    reason = evaluate(command)
    return deny(reason) if reason else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-safe: never brick the session
