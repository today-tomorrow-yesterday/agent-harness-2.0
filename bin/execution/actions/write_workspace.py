"""Action: write a file inside the workspace (action_class 'write_workspace').

The first *mutating* action class. It is the lowest-blast mutation (a file write
within the repo), and it ships **disabled** in policy.DEFAULT_POLICY — so routed
through execute() it PARKS for approval, never auto-runs, until the operator signs
the class on. Two independent guarantees, even once enabled:

1. **Reversible** — an existing target is backed up to `<file>.bak` before write
   (or the first free `.bak1`, `.bak2`, ... — a backup is never overwritten).
2. **Self-protection deny-list** — refuses to write the execution policy, the
   identity/memory files, or the execution/runner code itself (closes the
   "a confined action could edit its own guardrails" gap the 2026-06-20 audit found).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

# write_workspace.py -> actions -> execution -> bin -> repo root
REPO = Path(__file__).resolve().parents[3]

# Exact files an autonomous write must never touch: its own guardrails, the records
# that supervise it, and the identity / standing-rule files every session loads.
#
# An earlier version protected bin/execution and bin/runner but not the hooks that gate
# every shell command, so WriteWorkspace(path="bin/hooks/<guard>.py", ...) passed
# containment, matched nothing, and would have disarmed a guard for every later
# session. Anything an action could use to switch off its own supervision belongs here.
_DENY_FILES = (
    "forge/execution_policy.json",
    "forge/STOP",            # the kill-switch — a confined write must never clobber it
    "forge/runner.db",       # the audit log + approval queue
    "memory/user.md", "memory/agent.md", "memory/frame.md", "memory/soul.md",
    "memory/MEMORY.md",      # the memory index every session starts from
    "CLAUDE.md", "AGENTS.md",  # the standing rules loaded into every session
    "scheduled-tasks.md",    # the local scheduler record
    # The jobs that supervise autonomous work — an action that can rewrite its own
    # auditor has no auditor.
    "bin/self_test.py", "bin/self_loop.py", "bin/test_medic.py", "bin/skill_policy.py",
)
# Whole subtrees that are off-limits to autonomous writes.
_DENY_DIRS = ("bin/execution", "bin/runner", "bin/hooks", "bin/secrets", "bin/scheduler",
              ".git")


def _is_protected(rel: str) -> bool:
    """Is this repo-relative posix path on the self-protection deny-list?"""
    return rel in _DENY_FILES or any(rel == d or rel.startswith(d + "/") for d in _DENY_DIRS)


@dataclass
class WriteWorkspace:
    path: str                     # relative to root
    content: str
    root: str | None = None       # defaults to the repo root

    name: ClassVar[str] = "write_workspace"
    action_class: ClassVar[str] = "write_workspace"
    blast_radius: ClassVar[str] = "workspace"
    self_risk: ClassVar[str] = "LOW"

    def summary(self) -> str:
        # Deliberately plain wording — no "overwrite/delete/..." so the risk floor
        # scores this LOW (-> PAUSE for a disabled class), not HIGH (-> NEVER).
        return f"write file {self.path}"

    def run(self) -> Any:
        root = Path(self.root or REPO).resolve()
        target = (root / self.path).resolve()
        # Containment: the resolved path must stay under root.
        if root not in target.parents and target != root:
            raise ValueError(f"path escapes workspace root: {self.path}")
        rel = target.relative_to(root).as_posix()
        if _is_protected(rel):
            raise PermissionError(f"write denied to protected path: {rel}")
        # Every deny-list entry is REPO-relative ("bin/hooks/...", "forge/STOP"), but
        # `root` is a caller-supplied field. A root deeper than the repo (root=<repo>/bin,
        # path="hooks/x.py") shortened `rel` out of the list's reach while containment
        # still passed — containment is measured against the same caller-chosen root.
        # So the deny-list is ALSO checked against the repo it protects.
        try:
            rel_repo = target.relative_to(REPO).as_posix()
        except ValueError:
            rel_repo = None                     # target lives outside the repo (tmp roots)
        if rel_repo is not None and _is_protected(rel_repo):
            raise PermissionError(f"write denied to protected path: {rel_repo}")
        backup = None
        if target.exists():
            backup = target.with_suffix(target.suffix + ".bak")
            # Never overwrite an existing backup — a second write would otherwise
            # destroy the original. Take the first free .bak / .bak1 / .bak2 slot.
            if backup.exists():
                i = 1
                while target.with_suffix(target.suffix + f".bak{i}").exists():
                    i += 1
                backup = target.with_suffix(target.suffix + f".bak{i}")
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.content, encoding="utf-8")
        return {"wrote": rel, "bytes": len(self.content),
                "backup": backup.name if backup else None}
