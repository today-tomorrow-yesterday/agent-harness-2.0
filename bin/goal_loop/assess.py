"""assess_progress: honest per-goal movement verdicts. Pure given gathered signals."""
from __future__ import annotations

import sys
from pathlib import Path

_BIN = str(Path(__file__).resolve().parents[1])
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)
from goal_loop.goals_io import is_paused  # noqa: E402


def assess_progress(goals: list[dict], signals: dict) -> list[dict]:
    """One verdict per ACTIVE goal. A paused goal gets no verdict, so it gets no
    weekly question either (questions are generated from verdicts)."""
    verdicts = []
    for g in goals:
        if is_paused(g):
            continue
        s = signals.get(g["id"], {})
        if s.get("blocker"):
            verdicts.append({"id": g["id"], "verdict": "blocked",
                             "evidence": [f"blocked: {s['blocker']}"]})
            continue
        evidence = []
        if s.get("git_commits"):
            evidence.append(f"{s['git_commits']} git commit(s)")
        if s.get("artifacts"):
            evidence.append(f"{s['artifacts']} shipped artifact(s)")
        if s.get("brain_hits"):
            evidence.append(f"{s['brain_hits']} brain mention(s)")
        for a in s.get("log_activity", []):
            evidence.append(f"activity: {a}")
        if evidence:
            verdicts.append({"id": g["id"], "verdict": "moved", "evidence": evidence})
        else:
            verdicts.append({"id": g["id"], "verdict": "stalled",
                             "evidence": [f"no movement detected since {g.get('last_moved','?')}"]})
    return verdicts
