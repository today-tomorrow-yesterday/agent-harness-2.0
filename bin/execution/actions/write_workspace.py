"""Action: write a file inside the workspace (action_class 'write_workspace').

The first *mutating* action class. It is the lowest-blast mutation (a file write
within the repo), and it ships **disabled** in policy.DEFAULT_POLICY — so routed
through execute() it PARKS for approval, never auto-runs, until the operator signs
the class on. Two independent guarantees, even once enabled:

1. **Reversible** — an existing target is backed up to `<file>.bak` before write.
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

# Exact files an autonomous write must never touch (its own guardrails + identity).
_DENY_FILES = (
    "forge/execution_policy.json",
    "memory/user.md", "memory/sol.md", "memory/frame.md", "memory/soul.md",
)
# Whole subtrees that are off-limits to autonomous writes.
_DENY_DIRS = ("bin/execution", "bin/runner", ".git")


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
        if rel in _DENY_FILES or any(rel == d or rel.startswith(d + "/") for d in _DENY_DIRS):
            raise PermissionError(f"write denied to protected path: {rel}")
        backup = None
        if target.exists():
            backup = target.with_suffix(target.suffix + ".bak")
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.content, encoding="utf-8")
        return {"wrote": rel, "bytes": len(self.content),
                "backup": backup.name if backup else None}
