"""gather_signals: best-effort movement signals per goal (git/logs/brain). Impure.

Missing data defaults to 0/empty so assess.py reports 'no movement detected'
rather than inventing progress (honest-progress rule)."""
from __future__ import annotations
import subprocess
from pathlib import Path


def count_git_commits_since(repo, since: str) -> int:
    try:
        out = subprocess.run(["git", "-C", str(repo), "log", f"--since={since}", "--oneline"],
                             capture_output=True, text=True, timeout=30)  # don't hang the weekly brief on a locked repo
        if out.returncode != 0:
            return 0
        return len([ln for ln in out.stdout.splitlines() if ln.strip()])
    except Exception:
        return 0


def gather_signals(goals: list[dict], repo_base, since: str) -> dict:
    out = {}
    for g in goals:
        commits = sum(count_git_commits_since(Path(repo_base) / r, since)
                      for r in g.get("repos", []))
        out[g["id"]] = {"git_commits": commits, "artifacts": 0,
                        "log_activity": [], "brain_hits": 0, "blocker": None}
    return out
