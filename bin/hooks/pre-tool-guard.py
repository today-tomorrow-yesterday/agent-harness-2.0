#!/usr/bin/env python3
"""pre-tool-guard.py -- PreToolUse(Bash|PowerShell) deny-guard for destructive/irreversible commands.

Register with:  python bin/register_hook.py pre-tool-guard

What it blocks (exit 2, reason on stderr):
  * git history rewrites and force operations: force-push (incl. `+refspec`), rebase,
    filter-branch/filter-repo, `commit --amend`, `reset --hard`, deleting a remote branch
  * recursive force-delete of a filesystem root, or of an absolute path OUTSIDE the session's
    working directory (bash `rm -rf`, PowerShell `Remove-Item -Recurse -Force` + aliases, cmd
    `rd /s`) -- quoted targets such as "/srv/old project" included
  * disk-level writes (mkfs, dd to /dev/...)
  * piping a download straight into a shell (`curl | sh`, `iwr | iex`)
  * destructive SQL (DROP TABLE/DATABASE/SCHEMA, TRUNCATE TABLE), unquoted or passed to a SQL
    client such as `psql -c "..."`
  * recursive chmod/chown on a root path
  * `git commit` when the STAGED diff contains a secret shape (private key, AWS key id,
    `sk-` API key, GitHub token) -- the value is never echoed
  * in unattended runs (HARNESS_UNATTENDED=1): every `git commit` / `git push`, because no human
    is present to approve them
Commands nested as a string in `bash -c "..."`, `pwsh -Command "..."`, `cmd /c ...` or
`eval "..."` are checked as commands too.

What it deliberately does NOT block: plain `git commit` / `git add` in interactive sessions (commit
policy is a per-project decision), `--force-with-lease`, deletes inside the working directory.

Threat model: accidents, not adversaries. A quoted MENTION of a destructive command (a grep
pattern, echo text, a commit message) is an argument of grep/echo/git, not a command, and passes.
Deliberate evasion is out of scope for a guardrail.

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
    deny, hooks_disabled, nested_texts, read_payload, same_or_under, segments, strip_quoted,
    tool_input, unattended, verb,
)

ASK = ("If this action is truly intended, get the user's explicit approval in chat for this exact "
       "command, let them run it themselves, or narrow the scope.")

# Regex checks: shape of the command line. They run on views where data is blanked (see evaluate).
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
    # command position only: a quoted single word such as `grep "mkfs"` must not read as one
    (r"(?:^|[;&|]\s*)(?:sudo\s+)?mkfs(?:\.\w+)?\b|\bdd\s+[^|;&]*of=/dev/",
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

# Argument checks: run on parsed segments, where quoted arguments are real arguments.
ROOTISH = re.compile(
    r"^(/|/\*|~|~/|\$HOME/?|\$env:USERPROFILE[\\/]?|[A-Za-z]:[\\/]?\*?|\\\\[^\\/]+[\\/]?)$", re.I)
ABSOLUTE = re.compile(r"^(/|~|\$HOME|\$env:|[A-Za-z]:[\\/]|\\\\)", re.I)
SQL = re.compile(r"(?i)\b(drop\s+(table|database|schema)|truncate\s+table)\b")
SQL_CLIENTS = {"psql", "mysql", "mariadb", "sqlite3", "sqlcmd", "invoke-sqlcmd", "duckdb",
               "clickhouse-client", "mongosh", "bq"}
PS_DELETE = {"remove-item", "ri", "del", "erase", "rm", "rd", "rmdir"}
CMD_SWITCH = re.compile(r"^/[A-Za-z]$")

SECRET_PATTERNS = [re.compile(p) for p in (
    r"-----BEGIN[ A-Z]*PRIVATE KEY-----",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bsk-[A-Za-z0-9]{20,}\b",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
)]


def _expand(tok: str) -> str:
    if tok.lower().startswith("$env:userprofile"):
        tok = str(Path.home()) + tok[len("$env:userprofile"):]
    return os.path.expandvars(os.path.expanduser(tok))


def outside_workspace(targets: list[str]) -> bool:
    """Does any absolute target lie outside the session's working directory?"""
    project = os.getcwd()
    return any(ABSOLUTE.match(t) and not same_or_under(_expand(t), project) for t in targets)


def _positional(args: list[str]) -> list[str]:
    out, after_dd = [], False
    for a in args:
        if a == "--":
            after_dd = True
        elif after_dd or not a.startswith("-"):
            out.append(a)
    return out


def delete_targets(seg: list[str]) -> list[str] | None:
    """If `seg` is a RECURSIVE FORCE delete, its target arguments (quoted ones included);
    otherwise None. Covers bash rm, PowerShell Remove-Item and its aliases with full or
    abbreviated flags, and cmd rd/rmdir/del with /s."""
    v = verb(seg)
    args = seg[1:]
    flags = [a for a in args if a.startswith("-") and a != "--"]
    if v == "rm":
        short = [f[1:] for f in flags if not f.startswith("--")]
        if (any(re.search("[rR]", f) for f in short) or "--recursive" in flags) and \
                (any("f" in f for f in short) or "--force" in flags):
            return _positional(args)
    if v in PS_DELETE:
        low = [f.lower() for f in flags]
        if any(f.startswith("-rec") for f in low) and any(f.startswith("-fo") for f in low):
            return _positional(args)
        if v in ("rd", "rmdir", "del", "erase") and any(a.lower() == "/s" for a in args):
            return [a for a in args if not CMD_SWITCH.match(a) and not a.startswith("-")]
    return None


def check_segment(seg: list[str]) -> str | None:
    targets = delete_targets(seg)
    if targets is not None:
        if any(ROOTISH.match(t.strip()) for t in targets):
            return "recursive force-delete of a filesystem root."
        if outside_workspace(targets):
            return ("recursive force-delete targeting an absolute path outside the current "
                    "workspace.")
    if verb(seg) in SQL_CLIENTS and any(SQL.search(t) for t in seg[1:]):
        return "destructive SQL. Needs explicit approval with the exact statement quoted."
    return None


def staged_secrets() -> bool:
    """Scan the staged diff's ADDED lines for secret shapes (called on `git commit`)."""
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
    """Return a denial reason, or None to allow. Pure apart from the staged-diff read.

    Two views, so that quoting neither hides a target nor invents a command:
      * regex checks run on the command with quoted text blanked, AND on each parsed segment
        (nested `bash -c "..."` included) with only multi-word tokens blanked -- so a quoted
        single-word target like "/" still reads as a root;
      * argument checks run on the parsed segments, where `rm -rf "/srv/old project"` has a real
        target. A quoted mention (echo text, a commit message) is an ARGUMENT there, never a
        command of its own.
    """
    if not command:
        return None
    views = [strip_quoted(t) for t in nested_texts(command)]

    if unattended() and any(re.search(r"\bgit\s+(commit|push)\b", v) for v in views):
        return ("BLOCKED by pre-tool-guard (unattended mode): git commit/push cannot be approved "
                "with no human present. Leave the change uncommitted for interactive review.")

    for view in views:
        for pattern, reason in DENY:
            if pattern.search(view):
                return f"BLOCKED by pre-tool-guard: {reason}\n{ASK}"

    for seg in segments(command):
        reason = check_segment(seg)
        if reason:
            return f"BLOCKED by pre-tool-guard: {reason}\n{ASK}"

    if any(re.search(r"\bgit\s+commit\b", v) for v in views) and staged_secrets():
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
