"""Render the weekly Skill-Forge report (Phase 0: read-only)."""
from __future__ import annotations

# Action items surface first (Tre's green-on-top: most-actionable at the top).
_ACTION_ORDER = {"retire-candidate": 0, "insufficient-evidence": 1,
                 "no-data": 2, "healthy": 3}


def render_report(rows: list[dict], today: str) -> str:
    head = (f"# Skill-Forge report — {today}\n\n"
            "> **READ-ONLY (Phase 0).** This report scores existing skills to\n"
            "> validate the signal. No skill was modified, installed, or retired.\n\n")
    if not rows:
        return head + "_No skills found to score._\n"
    ordered = sorted(rows, key=lambda r: (_ACTION_ORDER.get(r["action"], 9), -r["trials"]))
    lines = [head,
             "| Skill | Origin | Invocations | Trials | Contribution | Advisory |",
             "|---|---|---|---|---|---|"]
    for r in ordered:
        lines.append(
            f"| {r['name']} | {r['origin']} | {r['invocations']} | {r['trials']} "
            f"| {r['score']:+.2f} | {r['action']} |")
    lines.append("\n_Advisory labels only. Autonomy is enabled in Phase 2, "
                 "gated on the eval-harness precision check (skill-forge-eval.py)._\n")
    return "\n".join(lines)
