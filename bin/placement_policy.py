#!/usr/bin/env python3
"""placement_policy.py -- which NEW top-level directories may appear in a protected root.

Consumer: bin/hooks/placement-guard.py, which refuses a Write/Edit/mkdir that would create a new
top-level directory in a protected root that is not on that root's allowlist.

WHY. A note telling agents "do not create new folders at the top of this repo" is advisory
context, and agents create them anyway -- that is how a tidy repo grows a `scratch/`, a `tmp2/`,
and a stray app. The Write tool creates parent directories implicitly, so a shell-only `mkdir`
guard misses the common case. The rule only has teeth at the decision point: the tool call.

The barrier is meant to cost a DECISION, not to be impossible: to allow a new top-level name, add
it to the allowlist (here for this repo, or in your policy file) with a reason.

Deliberately narrow, because a guard that blocks ordinary work gets switched off:
  * only the TOP level of each protected root is policed
  * nested directories under an existing or allowed top-level entry are always fine
  * writing into a directory that already exists is always fine
  * plain files at the top level of a root are not policed (only new directories)

Protected roots:
  1. this repository, with REPO_ALLOWED below (always, unless "include_repo": false)
  2. any roots listed in a JSON policy file named by HARNESS_PLACEMENT_POLICY:
         {"include_repo": true,
          "roots": {"~/work": ["clients", "tools", "_scratch"]}}

stdlib only, no I/O at import time: a PreToolUse hook imports this on every matching tool call.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# This repository's top level. Each entry costs a reason.
REPO_ALLOWED: dict[str, str] = {
    "bin":          "scripts, jobs and hooks -- the harness runtime",
    "claude-brain": "transcript history + its MCP server and hooks",
    "config":       "example manifests (your own copies are gitignored)",
    "captures":     "page-clone output (gitignored)",
    "docs":         "designs, plans, decisions",
    "forge":        "runtime state and job output",
    "logs":         "job and hook logs (gitignored)",
    "memory":       "hand-curated identity, rules and project briefs",
    "security-ops": "security tooling",
    "skills":       "canonical SKILL.md sources",
    ".git":         "version control",
    ".githooks":    "repo-local git hooks",
    ".github":      "CI configuration",
    ".claude":      "project-scoped Claude Code settings",
    ".pytest_cache": "pytest cache",
    ".venv":        "local virtualenv",
    "node_modules": "package install output",
}


def _norm(p: str | Path) -> Path | None:
    try:
        s = str(p).strip()
        return Path(os.path.abspath(os.path.expanduser(s))) if s else None
    except (OSError, ValueError):
        return None


def protected_roots() -> list[tuple[Path, set[str]]]:
    """[(root, allowed_top_level_names)], repo first, then the optional policy file's roots."""
    roots: list[tuple[Path, set[str]]] = []
    include_repo = True
    extra: dict = {}
    policy_file = os.environ.get("HARNESS_PLACEMENT_POLICY")
    if policy_file:
        try:
            data = json.loads(Path(policy_file).expanduser().read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                include_repo = data.get("include_repo", True) is not False
                if isinstance(data.get("roots"), dict):
                    extra = data["roots"]
        except (OSError, ValueError):
            pass                                   # unreadable policy -> repo default only
    if include_repo:
        roots.append((ROOT, set(REPO_ALLOWED)))
    for root, names in extra.items():
        r = _norm(root)
        if r is not None and isinstance(names, list):
            roots.append((r, {str(n) for n in names}))
    return roots


def _top_level_under(p: Path, root: Path) -> str | None:
    """The first path component of `p` below `root`, if `p` is strictly inside a subdirectory of
    `root`. Comparison is case-insensitive only where the OS is."""
    pc, rc = os.path.normcase(str(p)), os.path.normcase(str(root))
    try:
        if os.path.commonpath([pc, rc]) != rc:
            return None
    except ValueError:                             # different drives
        return None
    rel = os.path.relpath(str(p), str(root))
    parts = Path(rel).parts
    if len(parts) < 2 or parts[0] in (".", ".."):  # a file directly in root is not policed
        return None
    return parts[0]


def check_path(target: str | Path, *, is_dir: bool = False) -> str | None:
    """Return a DENY REASON if writing `target` would create a disallowed top-level directory.

    `is_dir=True` means `target` itself is a directory being created (mkdir), so a single path
    component below the root already counts.
    """
    p = _norm(target)
    if p is None:
        return None
    try:
        for root, allowed in protected_roots():
            probe = p / "_" if is_dir else p
            top = _top_level_under(probe, root)
            if top is None:
                continue
            if top in allowed or (root / top).exists():
                return None
            here = "this repository" if root == ROOT else str(root)
            fix = ("add it to REPO_ALLOWED in bin/placement_policy.py" if root == ROOT
                   else "add it to that root's list in your HARNESS_PLACEMENT_POLICY file")
            return (
                f"BLOCKED by placement-guard: this would create a new top-level directory "
                f"'{top}' in {here} ({root}).\n"
                f"Allowed top-level names there: {', '.join(sorted(allowed))}.\n"
                f"Put the work inside an existing directory instead (nested directories are "
                f"fine), or somewhere outside this root. If '{top}' genuinely belongs at the top "
                f"level, {fix} with a reason -- that is a deliberate decision for the user."
            )
    except (OSError, ValueError, IndexError):
        return None                                # fail open: a policy bug never blocks work
    return None
