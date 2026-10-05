"""Secret redaction for the event log / approval queue / digest. Two layers:

1. exact-value scrubbing — secrets handed out by execution.secrets register here,
   so even if one slips into a payload it is replaced before persistence;
2. a regex pack for common token shapes, built from execution.secret_patterns
   .SECRET_PATTERNS — the single canonical list, shared with notify_slack's
   egress scrub. Never re-inline a private copy here: separate copies drifted
   once, and the off-box path ended up the weakest.

scrub() runs on every event payload in execute._log and on every approval
summary/payload BEFORE it touches the DB.
"""
from __future__ import annotations

import re


def _load_patterns():
    """Import the canonical shape list, resolved from __file__ so it does not depend
    on the caller's sys.path. This module is a security control: it must fail loudly
    rather than silently fall back to a weaker local copy."""
    import sys
    from pathlib import Path
    bin_dir = str(Path(__file__).resolve().parents[1])
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    from execution.secret_patterns import SECRET_PATTERNS
    return [re.compile(p) for p in SECRET_PATTERNS]


_SECRETS: set[str] = set()

_PATTERNS = _load_patterns()

_MASK = "[REDACTED]"  # ASCII only — cp1252-safe on a Windows console or file


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
