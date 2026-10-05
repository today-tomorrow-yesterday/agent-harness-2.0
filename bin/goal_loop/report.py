"""build_goal_section: render the goal-progress markdown for the weekly briefing. Pure."""
from __future__ import annotations


def build_goal_section(goals, verdicts, questions, recs, paused=()) -> str:
    by_id = {g["id"]: g for g in goals}
    lines = ["## Goal Progress", ""]
    for v in verdicts:
        g = by_id.get(v["id"], {})
        lines.append(f"- **{v['id']} {g.get('title','')}** — {v['verdict']}: "
                     + "; ".join(v.get("evidence", [])))
    if paused:
        # One line, not one per goal: paused goals are decided, so they earn a
        # reminder that they exist and nothing more.
        lines += ["", "Paused (not assessed): " + ", ".join(g["id"] for g in paused)]
    lines += ["", "## Questions", ""]
    for q in questions:
        lines.append(f"- {q}")
    lines += ["", "## Recommended actions", ""]
    for r in recs:
        tag = " [needs approval]" if r["needs_approval"] else ""
        lines.append(f"- **{r['id']}**: {r['action']}{tag}")
    return "\n".join(lines) + "\n"
