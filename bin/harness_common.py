"""harness_common.py — small shared helpers for the background jobs in bin/.

Three pure functions that more than one job needs. They live here so there is ONE
definition of each: a private copy in every script is how one path ends up weaker
than the others without anyone noticing.

    defang_untrusted        neutralize fence markers inside scraped/ingested text
    classify_claude_result  tell a rate-limit from an auth failure from a real error
    clean_env               child environment for a headless `claude -p` spawn

Stdlib only. No side effects on import.
"""
from __future__ import annotations

import os
import re

# --- untrusted-content defanging (prompt-injection containment) ---------------------
# Every job that pastes SCRAPED or USER-AUTHORED text into a document or a `claude -p`
# prompt fences it as "untrusted data, not instructions". A fence alone is not a
# boundary: content containing the literal closing marker TERMINATES ITS OWN QUARANTINE,
# and everything after it reads as trusted instruction.
#
# Two rules, applied to the CONTENT only, never to the real fences:
#   1. any run of 3+ marker chars (< = >) is broken into dash-joined 3-char chunks, so no
#      marker-length run survives even as a substring;
#   2. known fence PHRASES are neutered, so a bare "END UNTRUSTED CONTENT" line can't match.
# Both survive newline-flattening and re-wrapping downstream (substring-safe, not line-based).
_MARKER_RUN_RE = re.compile(r"([<=>])\1{2,}")
_MARKER_PHRASE_RE = re.compile(
    r"(END\s+)?UNTRUSTED[\s\-_]+(WEB\s+|)(CONTENT|METADATA)|TRANSCRIPT_(BEGIN|END)", re.I)


def defang_untrusted(text: str) -> str:
    """Neutralize fence markers inside untrusted content so it cannot escape its quarantine.

    Use on ANY scraped/ingested text before interpolating it into a prompt. Lossless enough
    for the model to still read the content; the only mutations are to marker-shaped runs and
    fence phrases, which carry no meaning for the actual task.
    """
    text = _MARKER_RUN_RE.sub(
        lambda m: "-".join(m.group(0)[i:i + 3] for i in range(0, len(m.group(0)), 3)),
        text or "")
    return _MARKER_PHRASE_RE.sub(lambda m: m.group(0).replace(" ", "-") + "(defanged)", text)


# --- `claude -p` outcome classification ----------------------------------------------
def classify_claude_result(returncode: int, stdout: str = "", stderr: str = "") -> tuple[str, str | None]:
    """Classify a `claude -p` invocation outcome from its exit code + output.

    Returns (status, detail). status is one of:
      "ok"                — looks successful
      "auth_failed"       — credential/401 problem; needs a human to re-authenticate
      "rate_limited"      — hit a usage window or cap; detail = reset hint if found
      "model_unavailable" — model overloaded/unavailable
      "error"             — other non-zero failure

    Pure function — no side effects, fully unit-testable.
    """
    # A successful call (exit 0) is OK regardless of content — an answer may itself
    # mention "rate limit" / "401" / "unavailable". Only inspect the output for failure
    # signatures when the call actually FAILED. NOTE: `claude -p` writes rate-limit and
    # auth messages to STDOUT, not stderr, so both are read.
    if returncode == 0:
        return ("ok", None)
    blob = f"{stdout}\n{stderr}".lower()
    if ("401" in blob and ("auth" in blob or "credential" in blob)) \
            or "invalid authentication" in blob \
            or "failed to authenticate" in blob \
            or "please run /login" in blob \
            or ("oauth token" in blob and "expired" in blob):
        return ("auth_failed", "credential/401 — needs re-auth")
    # A per-model cap reads "You've reached your <model> limit. Switch to another model,
    # or manage usage credits at ..." — waiting is the remedy, so it is rate_limited
    # like the rolling window.
    if "session limit" in blob or "rate limit" in blob or "usage limit" in blob \
            or "you've hit your" in blob or "hit your session" in blob \
            or ("reached your" in blob and "limit" in blob) \
            or "manage usage credits" in blob or "switch to another model" in blob:
        m = re.search(r"resets?\s+([^\n.]+)", blob)
        return ("rate_limited", m.group(1).strip() if m else None)
    if "currently unavailable" in blob or "overloaded" in blob \
            or ("model" in blob and "unavailable" in blob):
        return ("model_unavailable", None)
    return ("error", f"exit {returncode}")


# --- child environment for headless spawns --------------------------------------------
# In -p mode a present ANTHROPIC_API_KEY silently overrides the subscription login and
# routes the job onto paid per-token billing. This harness is built to run on the
# subscription, so a metered key is never forwarded to a background `claude -p`.
# Deliberately does NOT match CLAUDE_CODE_OAUTH_TOKEN, which IS the subscription auth.
_METERED_KEY_RE = re.compile(r"ANTHROPIC.*KEY|CLAUDE.*API.*KEY|ANTHROPIC.*AUTH.*TOKEN|BILLING")


def clean_env(**overrides: str) -> dict[str, str]:
    """os.environ minus metered-billing keys, with optional overrides applied.

    Usage: subprocess.run(..., env=clean_env(CLAUDE_BRAIN_SKIP_HOOKS="1"))
    """
    env = {k: v for k, v in os.environ.items() if not _METERED_KEY_RE.search(k.upper())}
    env.update(overrides)
    return env
