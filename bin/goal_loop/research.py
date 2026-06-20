"""research_dispatch: capped web research on goals with an info-need. Impure (web)."""
from __future__ import annotations
import os
import shutil
import subprocess


def select_for_research(goals: list[dict], cap: int = 2) -> list[dict]:
    picked = [g for g in goals if "research" in (g.get("next_step") or "").lower()]
    return picked[:cap]


def run_research(question: str, timeout: int = 600) -> str | None:
    """One web-research query via `claude -p` with web tools. Returns a summary or None."""
    claude = shutil.which("claude") or shutil.which("claude.cmd")
    if not claude:
        return None
    env = os.environ.copy()
    env["CLAUDE_BRAIN_SKIP_HOOKS"] = "1"
    prompt = (f"Research this question and return a concise, sourced summary "
              f"(bullet points + links). Question: {question}")
    try:
        r = subprocess.run([claude, "-p", "--allowed-tools", "WebSearch WebFetch",
                            "--fallback-model", "claude-sonnet-4-6"],
                           input=prompt, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def research_dispatch(goals: list[dict], cap: int = 2, dry_run: bool = False) -> dict:
    findings = {}
    for g in select_for_research(goals, cap):
        q = g.get("next_step") or g.get("title", "")
        if dry_run:
            findings[g["id"]] = f"[dry-run] would research: {q}"
        else:
            res = run_research(q)
            if res:
                findings[g["id"]] = res
    return findings
