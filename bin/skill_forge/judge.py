"""LLM-as-judge: classify whether a skill invocation helped or hurt.

Bias note (NeurIPS 2024 self-preference; RAND 2026): the judge scores skills
[NAME] may have authored. Mitigation is a STRUCTURED RUBRIC with a fixed verdict
vocabulary (no free-form scoring), and — where the caller chooses — a different
judge model than the author. Unknown/garbled output defaults to 'inapplicable'
so a parse failure can never be mistaken for a 'hurt' signal.
"""
from __future__ import annotations
import re
from .config import VERDICTS

_VERDICT_RE = re.compile(r"VERDICT:\s*([A-Za-z]+)", re.IGNORECASE)


def build_judge_prompt(skill_name: str, skill_description: str,
                       after_window: list[dict]) -> str:
    convo = "\n".join(f"[{m['role']}] {m['content']}" for m in after_window)
    return f"""You are evaluating whether a skill invocation HELPED the user.

SKILL: {skill_name}
SKILL PURPOSE: {skill_description}

What happened immediately AFTER the skill ran (the outcome window):
----
{convo}
----

Classify the outcome using EXACTLY one of these four verdicts:
- helped       : the skill produced the intended result; the user moved on or approved.
- hurt         : the user corrected it, redid the work, re-ran it, or expressed dissatisfaction.
- neutral      : the skill ran but the outcome is genuinely ambiguous.
- inapplicable : the window doesn't actually show this skill's outcome.

Rules:
- Judge ONLY from the outcome window above. Do not assume.
- A correction, "no", "that's wrong", a manual redo, or an immediate re-run => hurt.
- Brief acknowledgement or moving to the next task => helped.

Think briefly, then end with a final line in EXACTLY this form:
VERDICT: <helped|hurt|neutral|inapplicable>"""


def parse_verdict(text: str) -> str:
    """Extract the verdict token; default to 'inapplicable' on miss/unknown."""
    m = _VERDICT_RE.search(text or "")
    if not m:
        return "inapplicable"
    token = m.group(1).lower()
    return token if token in VERDICTS else "inapplicable"


def classify_invocation(skill_name: str, skill_description: str,
                        after_window: list[dict], invoke_fn) -> str:
    """Build the rubric prompt, call invoke_fn(prompt)->str, parse the verdict.
    invoke_fn returning None/empty (e.g. claude -p failed) yields 'inapplicable'."""
    prompt = build_judge_prompt(skill_name, skill_description, after_window)
    raw = invoke_fn(prompt)
    if not raw:
        return "inapplicable"
    return parse_verdict(raw)
