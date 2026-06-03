# Evolution Audit Trail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an append-only `forge/evolution.jsonl` audit trail that records every change to any agent-os asset (memory files, skills, settings) with strategy, reason, and session context.

**Architecture:** Convention-based — a `skill_forge/evolution.py` helper module provides the `append_event()` write function; all writers (session-reflect, Skill-Forge, direct Claude edits) call it by convention rather than by hook. A standing feedback rule (`feedback/evolution_log_convention.md`) codifies the convention for direct edits.

**Tech Stack:** Python 3 (stdlib only: `json`, `datetime`, `pathlib`), JSONL, PowerShell for verification. No new dependencies.

---

## File Map

| Action | Path |
|---|---|
| Create | `Z:\agent-os\bin\skill_forge\evolution.py` |
| Create | `Z:\agent-os\bin\tests\test_evolution.py` |
| Modify | `Z:\agent-os\bin\skill_forge\config.py` |
| Modify | `Z:\agent-os\bin\skill-refiner.py` |
| Create | `Z:\agent-os\forge\evolution.jsonl` |
| Create | `Z:\agent-os\memory\feedback\evolution_log_convention.md` |
| Modify | `Z:\agent-os\memory\MEMORY.md` |
| Modify | `Z:\agent-os\skills\session-reflect\SKILL.md` |
| Modify | `C:\Users\<USERNAME>\.claude-<profile>\skills\session-reflect\SKILL.md` |
| Modify | `C:\Users\<USERNAME>\.claude\skills\session-reflect\SKILL.md` |

---

## Task 1: Add `EVOLUTION_LOG` path to config

**Files:**
- Modify: `Z:\agent-os\bin\skill_forge\config.py`

- [ ] **Step 1: Add the constant after `REPORT_PATH`**

In `Z:\agent-os\bin\skill_forge\config.py`, after line 14 (`REPORT_PATH = FORGE_DIR / "report-latest.md"`), add:

```python
EVOLUTION_LOG = FORGE_DIR / "evolution.jsonl"
```

- [ ] **Step 2: Verify**

```powershell
python -c "import sys; sys.path.insert(0,'Z:\\agent-os\\bin'); from skill_forge import config; print(config.EVOLUTION_LOG)"
```

Expected output: `Z:\agent-os\forge\evolution.jsonl`

---

## Task 2: Write failing tests for `evolution.py`

**Files:**
- Create: `Z:\agent-os\bin\tests\test_evolution.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for skill_forge.evolution.append_event."""
from __future__ import annotations
import json
import pytest
from skill_forge.evolution import append_event, VALID_STRATEGIES


def test_append_creates_file(tmp_path):
    log = tmp_path / "evolution.jsonl"
    append_event(strategy="repair", asset="feedback/foo.md",
                 what="fixed x", why="x was broken", session="abc12345",
                 log_path=log)
    assert log.exists()


def test_append_valid_json(tmp_path):
    log = tmp_path / "evolution.jsonl"
    append_event(strategy="innovate", asset="skills/my-skill/SKILL.md",
                 what="new skill", why="repeatable workflow detected", session="def67890",
                 log_path=log)
    entry = json.loads(log.read_text(encoding="utf-8").strip())
    assert entry["strategy"] == "innovate"
    assert entry["asset"] == "skills/my-skill/SKILL.md"
    assert entry["what"] == "new skill"
    assert entry["why"] == "repeatable workflow detected"
    assert entry["session"] == "def67890"
    assert "ts" in entry


def test_append_multiple_lines(tmp_path):
    log = tmp_path / "evolution.jsonl"
    append_event(strategy="repair", asset="a.md", what="w1", why="r1",
                 session="s1", log_path=log)
    append_event(strategy="harden", asset="b.md", what="w2", why="r2",
                 session="s2", log_path=log)
    lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["strategy"] == "repair"
    assert json.loads(lines[1])["strategy"] == "harden"


def test_append_invalid_strategy_raises(tmp_path):
    log = tmp_path / "evolution.jsonl"
    with pytest.raises(ValueError, match="strategy must be one of"):
        append_event(strategy="unknown", asset="x.md", what="w", why="r",
                     session="s", log_path=log)


def test_append_creates_parent_dirs(tmp_path):
    log = tmp_path / "nested" / "deep" / "evolution.jsonl"
    append_event(strategy="document", asset="memory/user.md",
                 what="added fact", why="new identity context", session="aaa00000",
                 log_path=log)
    assert log.exists()


def test_all_valid_strategies_accepted(tmp_path):
    log = tmp_path / "evolution.jsonl"
    for s in VALID_STRATEGIES:
        append_event(strategy=s, asset="x.md", what="w", why="r",
                     session="s", log_path=log)
    lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == len(VALID_STRATEGIES)
```

- [ ] **Step 2: Run tests — expect FAIL (module not yet created)**

```powershell
cd Z:\agent-os\bin; python -m pytest tests/test_evolution.py -v
```

Expected: `ModuleNotFoundError: No module named 'skill_forge.evolution'`

---

## Task 3: Implement `evolution.py`

**Files:**
- Create: `Z:\agent-os\bin\skill_forge\evolution.py`

- [ ] **Step 1: Create the module**

```python
"""evolution.py — append EvolutionEvent entries to forge/evolution.jsonl.

Schema: {ts, strategy, asset, what, why, session}
Strategies: repair | harden | innovate | calibrate | document
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

VALID_STRATEGIES = ("repair", "harden", "innovate", "calibrate", "document")


def append_event(
    *,
    strategy: str,
    asset: str,
    what: str,
    why: str,
    session: str,
    log_path: Path,
) -> None:
    """Append one evolution entry to evolution.jsonl. Creates the file if absent."""
    if strategy not in VALID_STRATEGIES:
        raise ValueError(
            f"strategy must be one of {VALID_STRATEGIES}, got {strategy!r}"
        )
    entry = {
        "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategy": strategy,
        "asset": asset,
        "what": what,
        "why": why,
        "session": session,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
```

- [ ] **Step 2: Run tests — expect all PASS**

```powershell
cd Z:\agent-os\bin; python -m pytest tests/test_evolution.py -v
```

Expected: 6 tests pass, 0 failures.

- [ ] **Step 3: Run full test suite to check for regressions**

```powershell
cd Z:\agent-os\bin; python -m pytest tests/ -v
```

Expected: all 38 existing tests + 6 new = 44 tests pass.

---

## Task 4: Create `evolution.jsonl` with bootstrap entry

**Files:**
- Create: `Z:\agent-os\forge\evolution.jsonl`

- [ ] **Step 1: Write bootstrap entry via Python**

```powershell
cd Z:\agent-os\bin
python -c "
import sys, datetime as dt
sys.path.insert(0, '.')
from skill_forge import config
from skill_forge.evolution import append_event
append_event(
    strategy='innovate',
    asset='forge/evolution.jsonl',
    what='Created evolution audit trail',
    why='Inspired by EvoMap/evolver EvolutionEvent concept; fills the changelog gap in agent-os',
    session='bootstrap',
    log_path=config.EVOLUTION_LOG,
)
print('written:', config.EVOLUTION_LOG)
"
```

Expected: `written: Z:\agent-os\forge\evolution.jsonl`

- [ ] **Step 2: Verify the file**

```powershell
Get-Content Z:\agent-os\forge\evolution.jsonl
```

Expected: one line of valid JSON with `"strategy": "innovate"` and `"asset": "forge/evolution.jsonl"`.

---

## Task 5: Wire `skill-refiner.py` to log on report write

**Files:**
- Modify: `Z:\agent-os\bin\skill-refiner.py`

Read lines 119–end of `skill-refiner.py` to see where the report is written before making this change.

- [ ] **Step 1: Read the rest of `main()` in skill-refiner.py**

```powershell
Get-Content Z:\agent-os\bin\skill-refiner.py | Select-Object -Skip 118
```

Note the exact line where `render_report` is called and the report file is written.

- [ ] **Step 2: Add the import at the top of the file (after existing imports)**

In `Z:\agent-os\bin\skill-refiner.py`, after the `from skill_forge.report import render_report` line, add:

```python
from skill_forge.evolution import append_event
```

- [ ] **Step 3: Add evolution entry after the report is written**

Find the block in `main()` where `render_report(rows)` is called and the report is written to disk. Immediately after that block, add:

```python
    append_event(
        strategy="calibrate",
        asset="forge/report-latest.md",
        what=f"Skill-Forge Phase 0 report: {len(rows)} skills scored",
        why=f"Weekly signal scan (lookback={args.lookback_days}d)",
        session="skill-refiner",
        log_path=config.EVOLUTION_LOG,
    )
```

- [ ] **Step 4: Smoke-test with `--skip-claude`**

```powershell
cd Z:\agent-os\bin; python skill-refiner.py --skip-claude
```

Expected: exits 0, no errors. Then verify:

```powershell
Get-Content Z:\agent-os\forge\evolution.jsonl
```

Expected: now 2 lines — the bootstrap entry + a `calibrate` entry for `forge/report-latest.md`.

---

## Task 6: Create the standing feedback rule

**Files:**
- Create: `Z:\agent-os\memory\feedback\evolution_log_convention.md`

- [ ] **Step 1: Write the feedback rule**

```markdown
---
name: evolution_log_convention
description: Standing rule — before writing or editing any agent-os asset (memory/, skills/, settings), append an evolution entry to forge/evolution.jsonl first.
type: feedback
---

# Evolution Log Convention

Before writing or editing any file under `Z:\agent-os\memory\`, `Z:\agent-os\skills\`, or either Claude profile's `settings.json`, append one entry to `Z:\agent-os\forge\evolution.jsonl` using the schema below.

**Schema:**
```json
{"ts": "<ISO 8601>", "strategy": "<see below>", "asset": "<Z:\\agent-os\\-relative path>", "what": "<one sentence: what changed>", "why": "<one sentence: the reason>", "session": "<first 8 chars of session ID>"}
```

**Strategies:**

| strategy | when |
|---|---|
| `repair` | Fixing a broken behavior, wrong rule, or incorrect assumption |
| `harden` | Strengthening a working pattern — more explicit guidance or tighter scope |
| `innovate` | New capability — new skill, new project, new tool |
| `calibrate` | Adjusting autonomy level, threshold, or collaboration balance |
| `document` | First-time capture of something already happening implicitly |

**Why:** The memory files record the current state of rules but not how they changed over time. The evolution log is the changelog layer — what broke, what was fixed, what drove each decision. Without it, the "why" of every rule is lost.

**How to apply:** Any time Claude writes or edits a file in `memory/`, `skills/`, or a profile `settings.json` — whether inside session-reflect, responding to a direct "update this rule" request, or modifying a SKILL.md — write the evolution entry first, then write the file. Use python or the Write tool to append directly to `Z:\agent-os\forge\evolution.jsonl`.

## Append directly (no helper required)

```python
import json, datetime as dt
entry = {
    "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "strategy": "repair",
    "asset": "feedback/my_rule.md",
    "what": "one sentence",
    "why": "one sentence",
    "session": "abc12345",
}
with open(r"Z:\agent-os\forge\evolution.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(entry) + "\n")
```

Or use `skill_forge.evolution.append_event()` when inside a Python script.

## Cross-references

- [[projects/agent_os]] — agent-os architecture; `Z:\agent-os\forge\` context
- [[projects/skill_forge]] — Skill-Forge; uses `append_event()` from `bin/skill_forge/evolution.py`
- [[memory_routing]] — identity-level memory routing rule
- [[never_commit_without_permission]] — agent-os is not a git repo; this log is local-only
```

- [ ] **Step 2: Verify file is readable**

```powershell
Get-Content "Z:\agent-os\memory\feedback\evolution_log_convention.md" | Select-Object -First 5
```

Expected: frontmatter with `name: evolution_log_convention`.

---

## Task 7: Update `MEMORY.md`

**Files:**
- Modify: `Z:\agent-os\memory\MEMORY.md`

- [ ] **Step 1: Add reference line under "Reference — tooling / setup"**

In `Z:\agent-os\memory\MEMORY.md`, find the existing line:

```
- [reference_frontend_design_stack.md](reference_frontend_design_stack.md) — UI/UX tooling stack ...
```

Add this line immediately after it:

```
- [`forge/evolution.jsonl`](../forge/evolution.jsonl) — **Evolution audit trail.** Append-only JSONL log of every change to memory/, skills/, or settings. Fields: ts, strategy (repair/harden/innovate/calibrate/document), asset, what, why, session. Written by session-reflect (Step 5), Skill-Forge (on report/install/retire), and direct Claude edits per [[evolution_log_convention]].
```

Also add the feedback rule to the Behavioral rules section. Find the last line in the `## Behavioral rules` section and append:

```
- [feedback/evolution_log_convention.md](feedback/evolution_log_convention.md) — Before writing/editing any memory/, skills/, or settings asset, append an evolution entry to `forge/evolution.jsonl` first. Schema + strategy guide inside.
```

- [ ] **Step 2: Verify MEMORY.md**

```powershell
Select-String "evolution" "Z:\agent-os\memory\MEMORY.md"
```

Expected: 2 matches — one in the Reference section, one in the Behavioral rules section.

---

## Task 8: Extend session-reflect Step 5

**Files:**
- Modify: `Z:\agent-os\skills\session-reflect\SKILL.md`

- [ ] **Step 1: Find the Step 5 section**

In `Z:\agent-os\skills\session-reflect\SKILL.md`, locate the `### Step 5 — Write + index` section (currently starting around line 121).

- [ ] **Step 2: Replace the Step 5 numbered list**

Find this text:

```
For each approved candidate:

1. **Write the file** to its target location with the full frontmatter + body
2. **Update `Z:\agent-os\memory\MEMORY.md`** by adding the new entry under the correct section (`Behavioral rules`, `Active projects`, `Ideas`, or `Top-level`)
3. **Append, don't overwrite**, when the target is an existing file like `feedback/anti_patterns.md`, `ideas/_index.md`, or `user.md`
```

Replace with:

```
For each approved candidate:

0. **Append an evolution entry** to `Z:\agent-os\forge\evolution.jsonl` before writing the file. Use the inline Python snippet from [[evolution_log_convention]] or the Write tool to append directly. Infer strategy from the candidate category:

   | candidate category | strategy |
   |---|---|
   | Behavioral correction (you said "no / don't") | `repair` |
   | Confirmed approach (you said "yes, that was right") | `harden` |
   | New skill candidate | `innovate` |
   | New project brief | `innovate` |
   | Project state update | `calibrate` |
   | Identity fact about you | `document` |
   | Anti-pattern / presentation rejection | `repair` |

   The entry is shown alongside the candidate in the proposal step (Step 4) so you can correct the strategy before anything is written. `asset` = the path relative to `Z:\agent-os\` (e.g. `feedback/my_rule.md`). `session` = first 8 chars of the current session ID from brain context.

1. **Write the file** to its target location with the full frontmatter + body
2. **Update `Z:\agent-os\memory\MEMORY.md`** by adding the new entry under the correct section (`Behavioral rules`, `Active projects`, `Ideas`, or `Top-level`)
3. **Append, don't overwrite**, when the target is an existing file like `feedback/anti_patterns.md`, `ideas/_index.md`, or `user.md`
```

- [ ] **Step 3: Verify the edit looks right**

```powershell
Select-String "evolution" "Z:\agent-os\skills\session-reflect\SKILL.md"
```

Expected: at least 2 matches referencing `evolution.jsonl` and `evolution_log_convention`.

---

## Task 9: Sync session-reflect to both Claude profiles

**Files:**
- Modify: `C:\Users\<USERNAME>\.claude-<profile>\skills\session-reflect\SKILL.md`
- Modify: `C:\Users\<USERNAME>\.claude\skills\session-reflect\SKILL.md`

Per [[parallel_subscriptions]], all three copies must be identical.

- [ ] **Step 1: Copy canonical to <YourOrg> profile**

```powershell
Copy-Item "Z:\agent-os\skills\session-reflect\SKILL.md" "C:\Users\<USERNAME>\.claude-<profile>\skills\session-reflect\SKILL.md" -Force
```

- [ ] **Step 2: Copy canonical to personal profile**

```powershell
Copy-Item "Z:\agent-os\skills\session-reflect\SKILL.md" "C:\Users\<USERNAME>\.claude\skills\session-reflect\SKILL.md" -Force
```

- [ ] **Step 3: Verify all three are identical**

```powershell
$a = Get-FileHash "Z:\agent-os\skills\session-reflect\SKILL.md"
$b = Get-FileHash "C:\Users\<USERNAME>\.claude-<profile>\skills\session-reflect\SKILL.md"
$c = Get-FileHash "C:\Users\<USERNAME>\.claude\skills\session-reflect\SKILL.md"
if ($a.Hash -eq $b.Hash -and $b.Hash -eq $c.Hash) { "PASS: all three identical" } else { "FAIL: hash mismatch" }
```

Expected: `PASS: all three identical`

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `forge/evolution.jsonl` append-only file | Task 4 |
| Schema: ts, strategy, asset, what, why, session | Tasks 2–3 (evolution.py) |
| Strategies: repair/harden/innovate/calibrate/document | Tasks 2–3 |
| session-reflect Step 5 extension | Task 8 |
| Skill-Forge log on report write | Task 5 |
| `feedback/evolution_log_convention.md` standing rule | Task 6 |
| MEMORY.md reference line | Task 7 |
| Both profile syncs for session-reflect | Task 9 |

**Placeholder scan:** No TBDs. All code is complete. Step 5 in Task 5 requires reading the file first — intentional (line numbers vary).

**Type consistency:** `append_event()` signature is identical in the test file (Task 2) and the implementation (Task 3). Config constant `EVOLUTION_LOG` defined in Task 1, used in Tasks 4 and 5.
