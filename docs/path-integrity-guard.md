# Path-integrity guard — a regression test for your next big reorg

## The failure mode

When you reorganize a drive/repo (rename a root folder, dissolve a directory,
move a tool), the *code* moves in one commit — but references to the old paths
hide everywhere: scripts, configs, docs, scheduled-task definitions, skill
files, memory notes. You fix the ones you find; the ones you miss resurface
weeks later as a farmer writing into a dead folder or a cockpit reading an
empty root. Worse, agents and generators keep *re-introducing* old paths they
learned from stale context.

The fix that actually holds is a **stale-path regression test**: after a reorg,
encode every retired path as a forbidden pattern, and let pytest fail the moment
one reappears anywhere in the operational tree. (This pattern caught five live
stragglers and one agent-reintroduced reference in its first week on the
system it was built for.)

## Template — drop into `bin/tests/test_path_integrity.py` after your reorg

```python
"""Stale-path guard: retired paths must never reappear in the operational tree."""
from __future__ import annotations
import re
from pathlib import Path

# The roots you actively maintain (NOT vendored/generated trees).
ROOTS = [Path(__file__).resolve().parents[2]]

# Dirs never scanned: vendored, generated, VCS, archives that legitimately
# describe history. ADD your synthesis/notes dirs — generated narrative will
# forever re-mention old paths when summarizing the reorg itself.
SKIP_DIRS = {"node_modules", ".git", ".venv", "__pycache__", "dist", "build",
             "_archive", "logs"}
# Files that legitimately DESCRIBE the migration (changelogs, this test).
SKIP_FILES = {"REORG-LOG.md", "test_path_integrity.py"}
EXTS = {".py", ".ps1", ".md", ".txt", ".json", ".yaml", ".yml",
        ".ts", ".tsx", ".js", ".toml", ".ini", ".cfg", ".sh"}

# Your retired paths. Word-boundary the patterns so NEW homes don't match
# (e.g. r"(?<![\\/])\bZ:\\oldname\b" won't match Z:\tools\oldname).
STALE: list[tuple[re.Pattern, str]] = [
    # (re.compile(r"Z:\\old-root\b", re.I), r"Z:\old-root (dissolved -> Z:\new\home)"),
]


def _iter_files():
    for root in ROOTS:
        for p in root.rglob("*"):
            if p.is_dir() or any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.name in SKIP_FILES or p.suffix.lower() not in EXTS:
                continue
            yield p


def test_no_stale_paths():
    hits = []
    for p in _iter_files():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for rx, label in STALE:
                if rx.search(line):
                    hits.append(f"{p}:{i}  [{label}]  {line.strip()[:100]}")
    assert not hits, "Stale paths reappeared:\n  " + "\n  ".join(hits[:40])
```

## Hard-won tuning notes

- **Skip generated/synthesis output.** Anything an agent writes that *narrates*
  history (session summaries, synthesis drafts, changelogs) will re-mention old
  paths forever. That's not breakage — exclude those dirs or the guard cries wolf.
- **The guard's own docs trip the guard.** Any README that documents the
  forbidden patterns must be in `SKIP_FILES` (or its dir skipped).
- **Word-boundary every pattern.** `Z:\nichefinder` must not match its new home
  `Z:\tools\nichefinder` — use `(?<![\\/])\b...` lookbehinds.
- **Windows consoles:** if you add a `__main__` runner, `sys.stdout.reconfigure(
  encoding="utf-8", errors="replace")` first — cp1252 chokes on glyphs.
- Wire it into `bin/self_test.py`'s suite (it lives in `bin/tests/`, so it's
  automatic) and the daily digest shows you the verdict.
