#!/usr/bin/env python3
"""design-gate.py -- frontend edits must go through your design skills. Enforcement, not prose.

Register with (pick YOUR skills; the gate names none by default):
    python bin/register_hook.py design-gate \
        --hook-arg=--build-skills=frontend-design,my-ui-skill \
        --hook-arg=--review-skills=my-design-review

Wired on three events (register_hook.py does all three):
  PreToolUse  Skill                -> records which skills this session invoked
  PreToolUse  Write|Edit|MultiEdit -> a frontend file may not be edited until at least one
                                      BUILD skill has been invoked this session
  Stop                             -> the turn may not end while a frontend file was edited
                                      AFTER the last run of EVERY review skill

Why: a written rule "use the design skills before touching UI, review with them before showing
anyone" was followed for the build half and skipped for the review half; an advisory reminder
fired and was walked past, and a generic-looking component shipped as "verified". Loading a skill
is not applying it, and a reminder is not a gate. This refuses instead.

Configuration (comma-separated skill names; a plugin skill may be given as `plugin:skill` or just
`skill`):
  --build-skills=...   / env DESIGN_GATE_BUILD_SKILLS    at least one must precede a frontend edit
  --review-skills=...  / env DESIGN_GATE_REVIEW_SKILLS   ALL must run after the last edit before
                                                         the turn may end (empty = no Stop check)
  --extensions=...     / env DESIGN_GATE_EXTENSIONS      default tsx,jsx,vue,svelte,css,html
The environment wins over the registered arguments. If NO build skills are configured, the gate
cannot know what to require: it does not block, and says so once per session in the model's
context instead of failing silently.

Never gated: tests/specs, node_modules, docs/, __tests__/.

Contract:
  * Deny = exit 2 + reason on stderr (PreToolUse: the tool call is refused; Stop: the model is
    handed the reason and keeps working). Allow = exit 0.
  * FAIL-SAFE: any internal error -> exit 0.
  * Off switches: DESIGN_GATE=off (this gate), HARNESS_HOOKS_DISABLED=1 (all hooks).
  * The Stop block is capped at STOP_BLOCK_CAP per edit, so a gate that cannot be satisfied
    cannot loop a session forever.

State: one JSON file per session under logs/hook-state/design-gate/ (see _hook_common.state_dir).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_common import (  # noqa: E402
    deny, emit_context, hooks_disabled, read_payload, safe_name, state_dir, tool_input,
)

STOP_BLOCK_CAP = 2
DEFAULT_EXTENSIONS = ("tsx", "jsx", "vue", "svelte", "css", "html")
NOT_FRONTEND = re.compile(
    r"(\.test\.|\.spec\.|[\\/]node_modules[\\/]|[\\/]docs[\\/]|[\\/]__tests__[\\/])", re.I,
)
EDIT_TOOLS = ("Write", "Edit", "MultiEdit")


def _split(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def load_config(argv: list[str]) -> dict:
    cfg = {"build": [], "review": [], "ext": list(DEFAULT_EXTENSIONS)}
    for a in argv:
        if "=" not in a:
            continue
        k, v = a.split("=", 1)
        if k == "--build-skills":
            cfg["build"] = _split(v)
        elif k == "--review-skills":
            cfg["review"] = _split(v)
        elif k == "--extensions":
            cfg["ext"] = [e.lstrip(".") for e in _split(v)] or cfg["ext"]
    if os.environ.get("DESIGN_GATE_BUILD_SKILLS") is not None:
        cfg["build"] = _split(os.environ["DESIGN_GATE_BUILD_SKILLS"])
    if os.environ.get("DESIGN_GATE_REVIEW_SKILLS") is not None:
        cfg["review"] = _split(os.environ["DESIGN_GATE_REVIEW_SKILLS"])
    if os.environ.get("DESIGN_GATE_EXTENSIONS"):
        cfg["ext"] = [e.lstrip(".") for e in _split(os.environ["DESIGN_GATE_EXTENSIONS"])]
    return cfg


def _bare(name: str) -> str:
    """`plugin:skill` and `skill` name the same skill."""
    return name.split(":", 1)[-1].strip().lower()


def is_frontend(path: str, extensions: list[str]) -> bool:
    if not path or NOT_FRONTEND.search(path):
        return False
    alts = "|".join(re.escape(e) for e in extensions)
    return bool(re.search(rf"\.({alts})$", path, re.I))


def state_file(session: str) -> Path:
    return state_dir("design-gate") / f"{safe_name(session)}.json"


def load(session: str) -> dict:
    try:
        st = json.loads(state_file(session).read_text(encoding="utf-8"))
        if isinstance(st, dict):
            st.setdefault("skills", {})
            return st
    except (OSError, ValueError):
        pass
    return {"skills": {}, "last_edit": None, "edited": [], "stop_blocks": 0}


def save(session: str, st: dict) -> None:
    state_file(session).write_text(json.dumps(st), encoding="utf-8")


def handle(payload: dict, cfg: dict) -> int:
    if os.environ.get("DESIGN_GATE", "").lower() in ("off", "0", "false"):
        return 0
    session = str(payload.get("session_id", ""))
    event = str(payload.get("hook_event_name", ""))
    tool = str(payload.get("tool_name", ""))
    tin = tool_input(payload)
    build = {_bare(s) for s in cfg["build"]}
    review = [_bare(s) for s in cfg["review"]]

    # -- record skill invocations
    if tool == "Skill":
        name = _bare(str(tin.get("skill", "")))
        if name:
            st = load(session)
            st["skills"][name] = time.time()
            save(session, st)
        return 0

    # -- gate frontend edits on a build skill having been invoked
    if tool in EDIT_TOOLS:
        path = str(tin.get("file_path", ""))
        if not is_frontend(path, cfg["ext"]):
            return 0
        st = load(session)
        if not build:
            if not st.get("warned_unconfigured"):
                st["warned_unconfigured"] = True
                save(session, st)
                emit_context("PreToolUse",
                             "design-gate is registered but has no build skills configured, so it "
                             "is not enforcing anything. Configure it with --build-skills / "
                             "DESIGN_GATE_BUILD_SKILLS (see docs/hooks.md).")
            return 0
        if not (set(st["skills"]) & build):
            return deny(
                "BLOCKED by design-gate: this is a frontend file and no design skill has been "
                f"invoked this session. Invoke one of: {', '.join(sorted(build))} via the Skill "
                "tool, apply it, then edit. Off switch for the user: DESIGN_GATE=off."
            )
        st["last_edit"] = time.time()
        st["stop_blocks"] = 0
        edited = st.setdefault("edited", [])
        if path not in edited:
            edited.append(path)
        save(session, st)
        return 0

    # -- the turn may not end unreviewed: every review skill must post-date the last edit
    if event == "Stop":
        if not review:
            return 0
        st = load(session)
        last = st.get("last_edit")
        if not last:
            return 0
        missing = [g for g in review if st["skills"].get(g, 0) <= last]
        if not missing:
            return 0
        if st.get("stop_blocks", 0) >= STOP_BLOCK_CAP:
            return 0
        st["stop_blocks"] = st.get("stop_blocks", 0) + 1
        save(session, st)
        files = ", ".join(st.get("edited", [])[-6:])
        return deny(
            "DESIGN GATE not run: frontend files were edited after the last review pass "
            f"({files}). Invoke {' and '.join(missing)} via the Skill tool on the RESULT, fix "
            "what they find, and only then finish. If the result was not reviewed, say "
            "'not reviewed' -- never 'done'."
        )

    return 0


def main(argv: list[str]) -> int:
    if hooks_disabled():
        return 0
    payload = read_payload()
    if payload is None:
        return 0
    return handle(payload, load_config(argv))


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-safe
