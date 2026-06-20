"""Secret redaction for the event log / digest. Two layers:

1. exact-value scrubbing — secrets handed out by execution.secrets register here,
   so even if one slips into a payload it is replaced before persistence;
2. a regex pack for common token shapes (Bearer / sk- / xox- / JWT / long hex).

scrub() runs on every event payload in execute._log BEFORE it touches the DB.
"""
from __future__ import annotations

import re

_SECRETS: set[str] = set()

_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]+"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWT
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),                                    # long hex
]

_MASK = "‹redacted›"  # ‹redacted›


def register_secret(value) -> None:
    """Register a secret value so scrub() removes it by exact match."""
    if value:
        _SECRETS.add(str(value))


def clear() -> None:
    """Drop the registered secret set (call between turns)."""
    _SECRETS.clear()


def scrub(text: str) -> str:
    if not text:
        return text
    out = text
    # exact registered values first (longest first, so substrings don't pre-empt)
    for val in sorted(_SECRETS, key=len, reverse=True):
        if val:
            out = out.replace(val, _MASK)
    for pat in _PATTERNS:
        out = pat.sub(_MASK, out)
    return out
