"""evolution.py — append EvolutionEvent entries to forge/evolution.jsonl.

Schema: {ts, strategy, asset, what, why, session}
Strategies: repair | harden | innovate | calibrate | document
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

VALID_STRATEGIES = ("repair", "harden", "innovate", "calibrate", "document")


def append_event(
    *,
    strategy: str,
    asset: str,
    what: str,
    why: str,
    session: str,
    log_path: Path,
) -> None:
    """Append one evolution entry to evolution.jsonl. Creates the file if absent."""
    if strategy not in VALID_STRATEGIES:
        raise ValueError(
            f"strategy must be one of {VALID_STRATEGIES}, got {strategy!r}"
        )
    entry = {
        "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategy": strategy,
        "asset": asset,
        "what": what,
        "why": why,
        "session": session,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
