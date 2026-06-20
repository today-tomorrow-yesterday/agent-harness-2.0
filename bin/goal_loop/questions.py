"""generate_questions: <=4 strategic, action-biased questions from verdicts. Pure."""
from __future__ import annotations


def generate_questions(verdicts: list[dict], goals: list[dict], cap: int = 4) -> list[str]:
    by_id = {g["id"]: g for g in goals}
    qs = []
    order = {"blocked": 0, "stalled": 1, "moved": 2}
    for v in sorted(verdicts, key=lambda v: order.get(v["verdict"], 9)):
        g = by_id.get(v["id"], {})
        title = g.get("title", v["id"])
        if v["verdict"] == "blocked":
            ev = "; ".join(v.get("evidence", []))
            qs.append(f"{v['id']} ({title}) is blocked ({ev}) — what unblocks it this week?")
        elif v["verdict"] == "stalled":
            qs.append(f"{v['id']} ({title}) hasn't moved since {g.get('last_moved','?')} — "
                      f"kill it, or what's the ONE next shippable step?")
        if len(qs) >= cap:
            break
    return qs
