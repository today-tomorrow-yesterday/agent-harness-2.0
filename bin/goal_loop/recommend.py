"""recommend_actions: per-goal next-step recs, flagging real-world actions for approval. Pure."""
from __future__ import annotations

# keywords implying an irreversible / outward-facing / ToS-bound real-world action
_APPROVAL_KEYWORDS = ("create account", "create a ", "sign up", "post", "publish",
                      "deploy", "send", "buy", "purchase", "register", "link them",
                      "credential", "password", "email account")


def recommend_actions(goals: list[dict], verdicts: list[dict]) -> list[dict]:
    recs = []
    for g in goals:
        step = (g.get("next_step") or "").strip()
        if not step:
            continue
        low = step.lower()
        needs = any(k in low for k in _APPROVAL_KEYWORDS)
        recs.append({"id": g["id"], "action": step, "needs_approval": needs})
    return recs
