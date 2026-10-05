#!/usr/bin/env python3
"""capability-gate.py -- advisory discovery: say the one useful thing at the moment it matters.

Register with:  python bin/register_hook.py capability-gate
(wires PreToolUse for tool-keyed rules and UserPromptSubmit for skill hints)

Two sources, both ADVISORY -- this hook never denies anything; blocking belongs to
pre-tool-guard.py, placement-guard.py and friends:

1. PreToolUse RULES keyed on the (tool, target) pair -- what the agent is ABOUT TO DO -- rather
   than on the user's phrasing. Prompt-keyed discovery depends on how the question was worded and
   cannot fire at all in an unattended run where there is no prompt; the (tool, target) pair
   exists in every case:
     keyring       reading bin/secrets/keyring.env  -> use bin/api.py, which redacts keys
     memory-index  writing memory/*.md              -> keep memory/MEMORY.md's index current
     skill-map     writing skills/**                -> regenerate the skill-discovery map
     new-bin-job   creating bin/<script>.py         -> scheduled? register it in jobs.py

2. UserPromptSubmit SKILL HINTS from bin/hooks/capability_map_generated.py, which
   bin/capability-map-gen.py builds from this repo's own skills/. A prompt that matches a skill's
   declared triggers gets a one-line pointer to that skill. Skills switched "off" in settings.json
   (skillOverrides) are never suggested.

Design constraints, in priority order:
  1. PRECISION OVER RECALL. A hint that fires on everything gets muted, and muting is invisible.
  2. FAIL OPEN, ALWAYS. Any error -> exit 0 with no output.
  3. SAY IT ONCE. Each rule / skill hint fires at most once per session.

Off switches: HARNESS_HOOKS_DISABLED=1 (all hooks), CAPABILITY_GATE=off (this one).
State: logs/hook-state/capability-gate/seen.json (bounded).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _hook_common import (  # noqa: E402
    BIN, ROOT, emit_context, hooks_disabled, read_payload, same_or_under, settings_path,
    state_dir, tool_input,
)

MAX_PROMPT_HINTS = 3


def _rel(path: str) -> str | None:
    """Repo-relative POSIX path, or None when outside the repo."""
    if not path or not same_or_under(path, ROOT):
        return None
    return os.path.relpath(os.path.abspath(path), str(ROOT)).replace("\\", "/")


def rule_hits(tool: str, ti: dict) -> list[tuple[str, str]]:
    """[(rule_id, message)] for one PreToolUse call."""
    hits: list[tuple[str, str]] = []
    api = (BIN / "api.py").as_posix()

    if tool in ("Bash", "PowerShell"):
        target = str(ti.get("command", ""))
    elif tool in ("Grep", "Glob"):
        target = f'{ti.get("path", "")} {ti.get("pattern", "")}'
    else:
        target = str(ti.get("file_path", "") or ti.get("notebook_path", ""))
    if not target:
        return hits

    if tool in ("Read", "Grep", "Glob", "Bash", "PowerShell") and \
            re.search(r"keyring\.env(?!\.template)|bin[\\/]secrets[\\/]?(?=\s|$|[\"'])",
                      target, re.I):
        hits.append(("keyring",
                     f"KEYRING -- do not read keyring.env directly. Call the API through "
                     f"`python {api}`, which injects the key and REDACTS it from output; "
                     f"`python {api} list` shows which services are configured (names only)."))

    if tool in ("Write", "Edit", "MultiEdit"):
        rel = _rel(target)
        if rel and rel.startswith("memory/") and rel.endswith(".md") and rel != "memory/MEMORY.md":
            hits.append(("memory-index",
                         "MEMORY INDEX -- memory/MEMORY.md is the router for memory/. If this "
                         "creates a new memory file or changes what one is for, update its "
                         "MEMORY.md entry in the same change."))
        if rel and rel.startswith("skills/"):
            hits.append(("skill-map",
                         "SKILL MAP -- after adding, renaming or re-describing a skill, run "
                         "`python bin/capability-map-gen.py --write` so the skill-discovery hints "
                         "know about it (bin/tests/test_capability_map_gen.py fails while stale)."))
        if tool == "Write" and rel and re.fullmatch(r"bin/[^/]+\.py", rel) \
                and not (ROOT / rel).exists():
            hits.append(("new-bin-job",
                         "NEW SCRIPT -- if this will run on a schedule, add a Job for it to "
                         "bin/scheduler/jobs.py REGISTRY. A job outside the registry is neither "
                         "installed nor watched by the self-loop."))
    return hits


def disabled_skills() -> set[str]:
    """Skill names switched "off" in settings.json skillOverrides (plugin prefix stripped)."""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8-sig"))
        ov = data.get("skillOverrides") or {}
    except (OSError, ValueError, AttributeError):
        return set()
    if not isinstance(ov, dict):
        return set()
    return {str(k).split(":", 1)[-1].lower() for k, v in ov.items() if str(v).lower() == "off"}


def prompt_hits(prompt: str) -> list[tuple[str, str]]:
    try:
        from capability_map_generated import GENERATED_CAPABILITY_MAP
    except Exception:
        return []
    off = disabled_skills()
    hits = []
    for entry_id, skills, pattern, message in GENERATED_CAPABILITY_MAP:
        if all(s.lower() in off for s in skills):
            continue
        if re.search(pattern, prompt, re.IGNORECASE):
            hits.append((f"skill:{entry_id}", message))
    return hits[:MAX_PROMPT_HINTS]


def already_fired(session: str, rule_id: str) -> bool:
    """Say it once per session. Any state failure means we DO fire: an extra hint is cheaper
    than a missed one."""
    path = state_dir("capability-gate") / "seen.json"
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(seen, dict):
            seen = {}
    except (OSError, ValueError):
        seen = {}
    key = f"{session}:{rule_id}"
    if key in seen:
        return True
    seen[key] = 1
    if len(seen) > 500:                         # bound it on a long-lived machine
        seen = dict(list(seen.items())[-200:])
    try:
        path.write_text(json.dumps(seen), encoding="utf-8")
    except OSError:
        pass
    return False


def main() -> int:
    if hooks_disabled() or os.environ.get("CAPABILITY_GATE", "").lower() in ("off", "0", "false"):
        return 0
    data = read_payload()
    if data is None:
        return 0
    session = str(data.get("session_id", "nosession"))
    event = str(data.get("hook_event_name", ""))

    if event == "UserPromptSubmit" or ("prompt" in data and "tool_name" not in data):
        prompt = data.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return 0
        hits, out_event, prefix = prompt_hits(prompt), "UserPromptSubmit", "SKILL HINT -- "
    else:
        tool = str(data.get("tool_name", ""))
        if not tool:
            return 0
        hits, out_event, prefix = rule_hits(tool, tool_input(data)), "PreToolUse", "CAPABILITY -- "

    fresh = [msg for rid, msg in hits if not already_fired(session, rid)]
    if fresh:
        emit_context(out_event, "\n\n".join(prefix + m for m in fresh))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # FAIL OPEN: a discovery hook must never be why a tool call dies
