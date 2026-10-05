"""The canonical list of secret SHAPES — the one definition of "what a credential
looks like" for every scrubber in this repo.

Dependency-free on purpose (stdlib `re` only, no package imports), so that both
execution.redaction (the event log / approval queue) and notify_slack (the off-box
egress chokepoint) can load it even when the rest of the package is broken.

Why one list and not copies: an earlier version kept a separate pattern list in
each scrubber. They drifted, and the scrubbers on the path that LEAVES the machine
ended up the weakest — AWS keys, GitHub tokens, PEM headers and Google API keys
went through them unmasked. Every scrubber now derives from this tuple; a test
pins that redaction._PATTERNS is built from it rather than from a private copy.

Patterns are raw regex strings (not compiled) so callers can compile them
individually or join them into one alternation. Never use a bare `(?i)` here —
global flags are an error once the patterns are joined; scope them `(?i:...)`.
"""
from __future__ import annotations

import re

SECRET_PATTERNS: tuple[str, ...] = (
    r"-----BEGIN[ A-Z]*PRIVATE KEY-----",   # PEM private key header
    r"Bearer\s+[A-Za-z0-9._\-]+",
    r"\bAKIA[0-9A-Z]{16}\b",                # AWS access-key id
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",      # GitHub PAT / OAuth / refresh token
    r"\bAIza[0-9A-Za-z_\-]{35}\b",          # Google API key
    r"sk-[A-Za-z0-9]{8,}",                  # OpenAI / Anthropic style secret keys
    r"xox[baprs]-[A-Za-z0-9-]{8,}",         # Slack tokens
    r"eyJ[A-Za-z0-9._\-]{10,}",             # JWT
    r"\b[A-Fa-f0-9]{32,}\b",                # long hex (keys / hashes)
    # Assignment-shaped leak: `SOME_API_TOKEN=<long value>` and friends. Keyed off
    # the NAME so it catches provider tokens with no distinctive prefix, without
    # redacting every long identifier in an ordinary log line.
    r"(?i:\b\w*(?:api[_-]?key|token|secret|password|passwd)\b\s*[=:]\s*"
    r"['\"]?[A-Za-z0-9_\-\.]{12,})",
)

MASK = "[REDACTED]"  # ASCII only: survives a cp1252 console or file on Windows

_JOINED = re.compile("(" + "|".join(SECRET_PATTERNS) + ")")


def scrub_shapes(text: str) -> str:
    """Mask every token-shaped substring. Shape-only (no registered exact values) —
    execution.redaction.scrub adds the exact-value layer on top of this."""
    return _JOINED.sub(MASK, text or "")
