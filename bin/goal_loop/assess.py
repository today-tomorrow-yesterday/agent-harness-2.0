"""assess_progress: honest per-goal movement verdicts. Pure given gathered signals."""
from __future__ import annotations


def assess_progress(goals: list[dict], signals: dict) -> list[dict]:
    verdicts = []
    for g in goals:
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
