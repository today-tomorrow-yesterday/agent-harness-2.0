"""Risk scorer: score an action LOW/MED/HIGH from a deterministic floor + the
action's self-hint, MAX-severity wins. The floor can only push risk UP — the model
(via self_risk) can never talk its way DOWN to a lower tier. This is the spine's
first guarantee.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

LEVELS = ("LOW", "MED", "HIGH")
_ORDER = {lvl: i for i, lvl in enumerate(LEVELS)}


def _max(a: str, b: str) -> str:
    """Max-severity of two NORMALIZED levels (see _normalize_hint)."""
    return a if _ORDER.get(a, 0) >= _ORDER.get(b, 0) else b


def _normalize_hint(raw) -> tuple[str, str | None]:
    """Map a self-declared risk token onto LEVELS. Returns (level, unrecognized_token).

    Fail-CLOSED: anything that is not LOW/MED/HIGH (after trimming and upper-casing)
    scores HIGH. An earlier version scored it LOW, silently: `_ORDER.get(tok, 0)` put
    an unknown token such as "high" (lowercase) or "CRITICAL" at index 0, tied with the
    LOW floor, and the floor won. A token the scorer cannot read is a token it cannot
    trust, and the module promise is that an action can never talk its risk DOWN. The
    discarded token is surfaced as a reason so it appears in the audit event.
    """
    tok = str(raw or "").strip().upper()
    if tok in _ORDER:
        return tok, None
    return "HIGH", (str(raw).strip() or "(empty)")


# Deterministic floor: (compiled pattern, forced-level, reason). Matched against
# "<name> <summary>". These force HIGH for irreversible / identity / financial /
# destructive intent regardless of what the action claims about itself.
_FLOOR_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\brm\s+-rf\b|\bdel(ete)?\b|\bdrop\s+table\b|\btruncate\b", re.I),
     "HIGH", "destructive/irreversible verb"),
    (re.compile(r"\bforce[- ]?push\b|\bgit\s+reset\s+--hard\b|\boverwrite\b", re.I),
     "HIGH", "irreversible repo/file op"),
    (re.compile(r"\bsend\b|\bpost\b|\bpublish\b|\bsubmit\b|\bemail\b|\btweet\b|\bDM\b", re.I),
     "HIGH", "outward-facing publish/send"),
    (re.compile(r"\bcreate\s+account\b|\bsign\s*up\b|\bregister\b|\bpassword\b|\blogin\b|\bauth\b", re.I),
     "HIGH", "identity/credential op"),
    (re.compile(r"\bpay\b|\bpurchase\b|\bbuy\b|\btransfer\b|\bcharge\b|\bcheckout\b|\binvoice\b|\$\d", re.I),
     "HIGH", "financial op"),
]


@dataclass
class Risk:
    level: str                  # LOW / MED / HIGH (final, after max-severity)
    blast_radius: str           # none / workspace / external_write / unrestricted
    reasons: list[str] = field(default_factory=list)


def score_action(action) -> Risk:
    """Score an action. floor(rules) maxed against action.self_risk."""
    text = f"{getattr(action, 'name', '')} {action.summary()}"
    floor = "LOW"
    reasons: list[str] = []
    for pat, lvl, why in _FLOOR_RULES:
        if pat.search(text):
            floor = _max(floor, lvl)
            reasons.append(f"floor:{why}")
    self_hint, unrecognized = _normalize_hint(getattr(action, "self_risk", "LOW"))
    if unrecognized is not None:
        reasons.append(f"self-hint:unrecognized {unrecognized!r} -> HIGH (fail-closed)")
    level = _max(floor, self_hint)
    if unrecognized is None and level == self_hint and self_hint != floor:
        reasons.append(f"self-hint:{self_hint}")
    return Risk(level=level, blast_radius=getattr(action, "blast_radius", "unrestricted"),
                reasons=reasons)
