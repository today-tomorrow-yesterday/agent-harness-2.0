# Skill-Forge Phase 0 (Signal Validator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only `skill-refiner` that scores every existing skill from the claude-brain transcript history (frequency + LLM-judged `helped/hurt/neutral/inapplicable` verdict) and writes a weekly report — plus an eval harness that measures the judge's precision against a hand-labeled sample. **No skill is modified.** This phase exists to prove the signal is trustworthy before any autonomy is enabled in later phases.

**Architecture:** A small importable Python package `bin/skill_forge/` holds focused, unit-tested units (brain query, skill inventory, LLM judge, scoring, report). A flat CLI entrypoint `bin/skill-refiner.py` wires them, matching the existing farmer-script convention. The LLM judge takes an injected `invoke_fn` so all logic is testable without calling Claude. A separate `bin/skill-forge-eval.py` measures judge precision (the Phase-1 unlock gate).

**Tech Stack:** Python 3 (stdlib `sqlite3`, `argparse`, `subprocess`, `pathlib`), `pytest` for tests, `claude -p` headless via the user's subscription (pattern copied verbatim from `bin/weekly-planner.py`).

---

## Conventions for this plan

- **No git.** `Z:\agent-os\` is intentionally **not** a git repo (`no_github_remote_for_agent_os`; agent-os isn't versioned). So there are **no commit steps**. Each task ends with a **Checkpoint**: run the full test suite green. Reversibility of the *product* (skills) is handled by Phase 2's filesystem snapshots, not by versioning this code.
- **Run tests from** `Z:\agent-os\bin\` so `pytest` discovers `skill_forge/` and `tests/`. Install pytest once: `python -m pip install pytest`.
- **Phase 0 is read-only.** The refiner never writes to `skills/`, never installs, never quarantines. It only writes `forge/report-latest.md` and appends to `skill-forge.log`.
- **All file paths are Windows absolute paths**, matching the existing farmers.

## File structure

```
Z:\agent-os\bin\
  skill_forge\                  ← NEW package (importable, unit-tested)
    __init__.py
    config.py                   ← paths + thresholds (Nmin, tau, window sizes)
    skills_inventory.py         ← enumerate skills from SKILL.md frontmatter
    brain_query.py              ← query brain DB: find invocations + after-windows
    judge.py                    ← build rubric prompt, parse verdict, classify (DI on invoke_fn)
    scoring.py                  ← contribution score + action classification (report-only)
    report.py                   ← render forge/report-latest.md
  skill-refiner.py              ← NEW CLI entrypoint (score-only mode)
  skill-forge-eval.py           ← NEW precision harness (Phase-1 unlock gate)
  tests\                        ← NEW pytest suite
    conftest.py                 ← temp brain DB fixture + sample skills dir
    test_skills_inventory.py
    test_brain_query.py
    test_judge.py
    test_scoring.py
    test_report.py
Z:\agent-os\forge\
  report-latest.md              ← written by skill-refiner (created at runtime)
  eval\
    labels.sample.jsonl         ← NEW hand-labeled gold set for the eval harness
Z:\agent-os\skill-forge.log     ← append-only log (created at runtime)
```

---

### Task 1: Scaffold package, config, and test fixtures

**Files:**
- Create: `Z:\agent-os\bin\skill_forge\__init__.py`
- Create: `Z:\agent-os\bin\skill_forge\config.py`
- Create: `Z:\agent-os\bin\tests\conftest.py`

- [ ] **Step 1: Create the package marker**

`Z:\agent-os\bin\skill_forge\__init__.py`:
```python
"""Skill-Forge — self-improving skills loop. Phase 0: read-only signal validator."""
```

- [ ] **Step 2: Write config.py**

`Z:\agent-os\bin\skill_forge\config.py`:
```python
"""Skill-Forge configuration: paths and lifecycle thresholds.

Threshold provenance: Library Drift (arxiv 2605.19576) — contribution score,
evidence floor Nmin=100, retirement tau=0.10, bounded active-cap. Phase 0 only
COMPUTES these; it never acts on them.
"""
from __future__ import annotations
from pathlib import Path

AGENT_OS = Path(r"Z:\agent-os")
BRAIN_DB = AGENT_OS / "claude-brain" / "claude-brain.db"
SKILLS_DIR = AGENT_OS / "skills"          # canonical source skills (you-authored)
FORGE_DIR = AGENT_OS / "forge"
REPORT_PATH = FORGE_DIR / "report-latest.md"
LOG_PATH = AGENT_OS / "skill-forge.log"

# Lifecycle thresholds (computed in Phase 0, acted on in Phase 2+)
N_MIN = 100          # evidence floor: trials required before retire/revise is eligible
TAU = 0.10           # retirement threshold: retire when contribution <= -TAU
ACTIVE_CAP = 25      # bounded active-cap for Forge-minted skills (not enforced in P0)

# Signal-extraction window
LOOKBACK_DAYS = 90   # how far back to scan transcripts for invocations
AFTER_WINDOW = 6     # messages after an invocation the judge inspects for outcome

VERDICTS = ("helped", "hurt", "neutral", "inapplicable")
```

- [ ] **Step 3: Write the pytest fixtures (temp brain DB + sample skills dir)**

`Z:\agent-os\bin\tests\conftest.py`:
```python
"""Shared pytest fixtures: an in-memory-on-disk brain DB and a sample skills dir."""
from __future__ import annotations
import sqlite3
import pytest


@pytest.fixture
def brain_conn():
    """A sqlite connection seeded with the transcripts table subset we query."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE transcripts ("
        " id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,"
        " content TEXT, timestamp TEXT)"
    )
    rows = [
        # session s1: clone-route invoked, then user thanks (helped)
        (1, "s1", "user", "<command-name>clone-route</command-name>", "2026-05-01T10:00:00Z"),
        (2, "s1", "assistant", "Routed 3 folders.", "2026-05-01T10:01:00Z"),
        (3, "s1", "user", "perfect, thanks", "2026-05-01T10:02:00Z"),
        # session s2: clone-route invoked, then user corrects (hurt)
        (4, "s2", "user", "<command-name>clone-route</command-name>", "2026-05-02T11:00:00Z"),
        (5, "s2", "assistant", "Routed to expert joey.", "2026-05-02T11:01:00Z"),
        (6, "s2", "user", "no that's wrong, it should go to kallaway", "2026-05-02T11:02:00Z"),
        # session s3: an unrelated skill, never our target
        (7, "s3", "user", "<command-name>watch</command-name>", "2026-05-03T12:00:00Z"),
        (8, "s3", "assistant", "Watched the video.", "2026-05-03T12:01:00Z"),
    ]
    conn.executemany(
        "INSERT INTO transcripts (id, session_id, role, content, timestamp)"
        " VALUES (?,?,?,?,?)", rows)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def sample_skills_dir(tmp_path):
    """A skills/ dir with two SKILL.md files (one you-authored, one Forge-minted)."""
    sd = tmp_path / "skills"
    (sd / "clone-route").mkdir(parents=True)
    (sd / "clone-route" / "SKILL.md").write_text(
        "---\nname: clone-route\ndescription: Route inbox content into wiki.\n---\n\nBody.",
        encoding="utf-8")
    (sd / "compose-shorts").mkdir(parents=True)
    (sd / "compose-shorts" / "SKILL.md").write_text(
        "---\nname: compose-shorts\ndescription: Compose short clips.\n"
        "origin: skill-forge\n---\n\nBody.",
        encoding="utf-8")
    return sd
```

- [ ] **Step 4: Verify pytest collects the (empty) suite**

Run: `python -m pytest Z:\agent-os\bin\tests -q`
Expected: `no tests ran` (exit 5) — confirms collection works and conftest imports cleanly.

- [ ] **Step 5: Checkpoint** — fixtures import without error (Step 4 shows no import traceback).

---

### Task 2: Skill inventory (parse SKILL.md frontmatter)

**Files:**
- Create: `Z:\agent-os\bin\skill_forge\skills_inventory.py`
- Test: `Z:\agent-os\bin\tests\test_skills_inventory.py`

- [ ] **Step 1: Write the failing test**

`Z:\agent-os\bin\tests\test_skills_inventory.py`:
```python
from skill_forge.skills_inventory import list_skills


def test_lists_both_skills_with_names_and_origin(sample_skills_dir):
    skills = list_skills(sample_skills_dir)
    by_name = {s["name"]: s for s in skills}
    assert set(by_name) == {"clone-route", "compose-shorts"}
    assert by_name["clone-route"]["origin"] == "authored"
    assert by_name["compose-shorts"]["origin"] == "skill-forge"
    assert by_name["clone-route"]["description"].startswith("Route inbox")
    assert by_name["clone-route"]["path"].endswith("SKILL.md")


def test_empty_dir_returns_empty(tmp_path):
    assert list_skills(tmp_path / "nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skills_inventory.py -v` (from `Z:\agent-os\bin`)
Expected: FAIL — `ModuleNotFoundError: No module named 'skill_forge.skills_inventory'`

- [ ] **Step 3: Write the implementation**

`Z:\agent-os\bin\skill_forge\skills_inventory.py`:
```python
"""Enumerate skills from their SKILL.md frontmatter."""
from __future__ import annotations
import re
from pathlib import Path

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def list_skills(skills_dir: Path) -> list[dict]:
    """Return [{name, description, origin, path}] for each <skill>/SKILL.md.

    origin: 'skill-forge' if the frontmatter declares it, else 'authored'.
    """
    skills_dir = Path(skills_dir)
    if not skills_dir.exists():
        return []
    out: list[dict] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            fm = _parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        name = fm.get("name") or skill_md.parent.name
        out.append({
            "name": name,
            "description": fm.get("description", ""),
            "origin": "skill-forge" if fm.get("origin") == "skill-forge" else "authored",
            "path": str(skill_md),
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_skills_inventory.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Checkpoint** — `python -m pytest tests -q` green.

---

### Task 3: Brain query — find skill invocations

**Files:**
- Create: `Z:\agent-os\bin\skill_forge\brain_query.py`
- Test: `Z:\agent-os\bin\tests\test_brain_query.py`

- [ ] **Step 1: Write the failing test**

`Z:\agent-os\bin\tests\test_brain_query.py`:
```python
from skill_forge.brain_query import find_invocations


def test_finds_command_name_invocations(brain_conn):
    inv = find_invocations(brain_conn, "clone-route", since="2026-01-01T00:00:00Z")
    sessions = sorted(i["session_id"] for i in inv)
    assert sessions == ["s1", "s2"]            # not s3 (that was 'watch')
    assert all("timestamp" in i and "id" in i for i in inv)


def test_respects_since_cutoff(brain_conn):
    inv = find_invocations(brain_conn, "clone-route", since="2026-05-02T00:00:00Z")
    assert [i["session_id"] for i in inv] == ["s2"]   # s1 was 2026-05-01


def test_unknown_skill_returns_empty(brain_conn):
    assert find_invocations(brain_conn, "does-not-exist", since="2026-01-01T00:00:00Z") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_brain_query.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skill_forge.brain_query'`

- [ ] **Step 3: Write the implementation**

`Z:\agent-os\bin\skill_forge\brain_query.py`:
```python
"""Query the claude-brain transcript DB for skill invocations and their outcomes.

Detection (Phase 0): a transcript row whose content contains
`<command-name>SKILL</command-name>` (slash-invocation form) OR the literal
`"skill": "SKILL"` / `Skill(SKILL)` shapes the Skill tool can serialize to.
The command-name form is the reliable signal; the others are best-effort and
their recall is a calibration target measured in Task 11.
"""
from __future__ import annotations
import sqlite3


def find_invocations(conn: sqlite3.Connection, skill_name: str, since: str) -> list[dict]:
    """Return [{id, session_id, timestamp}] for each invocation of skill_name
    at or after the ISO timestamp `since`, ordered oldest-first."""
    patterns = [
        f"%<command-name>{skill_name}</command-name>%",
        f"%<command-name>/{skill_name}</command-name>%",
        f'%"skill": "{skill_name}"%',
        f'%"skill":"{skill_name}"%',
    ]
    where = " OR ".join("content LIKE ?" for _ in patterns)
    sql = (
        f"SELECT id, session_id, timestamp FROM transcripts "
        f"WHERE timestamp >= ? AND ({where}) ORDER BY timestamp ASC"
    )
    cur = conn.execute(sql, [since, *patterns])
    return [{"id": r[0], "session_id": r[1], "timestamp": r[2]} for r in cur.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_brain_query.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Checkpoint** — `python -m pytest tests -q` green.

---

### Task 4: Brain query — the outcome window after an invocation

**Files:**
- Modify: `Z:\agent-os\bin\skill_forge\brain_query.py` (add `get_after_window`)
- Test: `Z:\agent-os\bin\tests\test_brain_query.py` (add cases)

- [ ] **Step 1: Write the failing test (append to test_brain_query.py)**

```python
from skill_forge.brain_query import get_after_window


def test_after_window_returns_following_messages_same_session(brain_conn):
    # invocation row id=4 (s2, 11:00); window should be the next msgs in s2
    window = get_after_window(brain_conn, session_id="s2",
                              after_timestamp="2026-05-02T11:00:00Z", limit=6)
    contents = [m["content"] for m in window]
    assert "Routed to expert joey." in contents
    assert "no that's wrong, it should go to kallaway" in contents
    # must not leak rows from other sessions
    assert all(m["role"] in ("user", "assistant") for m in window)


def test_after_window_limit_truncates(brain_conn):
    window = get_after_window(brain_conn, session_id="s1",
                              after_timestamp="2026-05-01T10:00:00Z", limit=1)
    assert len(window) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_brain_query.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_after_window'`

- [ ] **Step 3: Add the implementation to brain_query.py**

```python
def get_after_window(conn: sqlite3.Connection, session_id: str,
                     after_timestamp: str, limit: int) -> list[dict]:
    """Return up to `limit` messages in `session_id` strictly after the given
    timestamp, oldest-first: [{role, content, timestamp}]. This is the evidence
    window the judge reads to decide whether the skill helped or hurt."""
    sql = (
        "SELECT role, content, timestamp FROM transcripts "
        "WHERE session_id = ? AND timestamp > ? "
        "ORDER BY timestamp ASC LIMIT ?"
    )
    cur = conn.execute(sql, [session_id, after_timestamp, limit])
    return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in cur.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_brain_query.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Checkpoint** — `python -m pytest tests -q` green.

---

### Task 5: Judge — prompt builder and verdict parser (pure functions)

**Files:**
- Create: `Z:\agent-os\bin\skill_forge\judge.py`
- Test: `Z:\agent-os\bin\tests\test_judge.py`

- [ ] **Step 1: Write the failing test**

`Z:\agent-os\bin\tests\test_judge.py`:
```python
import pytest
from skill_forge.judge import build_judge_prompt, parse_verdict


def test_prompt_includes_skill_and_window_and_rubric():
    window = [{"role": "assistant", "content": "Did the thing."},
              {"role": "user", "content": "no that's wrong"}]
    p = build_judge_prompt("clone-route", "Route inbox content.", window)
    assert "clone-route" in p
    assert "Route inbox content." in p
    assert "no that's wrong" in p
    # rubric must enumerate the four verdicts and demand a structured last line
    for v in ("helped", "hurt", "neutral", "inapplicable"):
        assert v in p
    assert "VERDICT:" in p


@pytest.mark.parametrize("text,expected", [
    ("reasoning...\nVERDICT: helped", "helped"),
    ("VERDICT: hurt", "hurt"),
    ("VERDICT:neutral", "neutral"),
    ("VERDICT: INAPPLICABLE", "inapplicable"),
    ("some prose with no verdict", "inapplicable"),  # safe default
    ("VERDICT: banana", "inapplicable"),              # unknown -> safe default
])
def test_parse_verdict(text, expected):
    assert parse_verdict(text) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_judge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skill_forge.judge'`

- [ ] **Step 3: Write the implementation**

`Z:\agent-os\bin\skill_forge\judge.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_judge.py -v`
Expected: PASS (7 passed — `test_prompt...` + 6 parametrized `test_parse_verdict`)

- [ ] **Step 5: Checkpoint** — `python -m pytest tests -q` green.

---

### Task 6: Judge — `classify_invocation` with injected invoker

**Files:**
- Modify: `Z:\agent-os\bin\skill_forge\judge.py` (add `classify_invocation`)
- Test: `Z:\agent-os\bin\tests\test_judge.py` (add cases)

- [ ] **Step 1: Write the failing test (append to test_judge.py)**

```python
from skill_forge.judge import classify_invocation


def test_classify_invocation_uses_injected_invoker():
    captured = {}

    def fake_invoke(prompt: str) -> str:
        captured["prompt"] = prompt
        return "looks like a correction.\nVERDICT: hurt"

    window = [{"role": "user", "content": "no that's wrong"}]
    verdict = classify_invocation("clone-route", "Route inbox.", window, invoke_fn=fake_invoke)
    assert verdict == "hurt"
    assert "clone-route" in captured["prompt"]


def test_classify_invocation_handles_invoker_failure():
    def broken_invoke(prompt: str):
        return None                      # simulates claude -p failure
    verdict = classify_invocation("x", "y", [{"role": "user", "content": "z"}],
                                  invoke_fn=broken_invoke)
    assert verdict == "inapplicable"     # never fabricate a hurt/helped on failure
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_judge.py -v`
Expected: FAIL — `ImportError: cannot import name 'classify_invocation'`

- [ ] **Step 3: Add the implementation to judge.py**

```python
def classify_invocation(skill_name: str, skill_description: str,
                        after_window: list[dict], invoke_fn) -> str:
    """Build the rubric prompt, call invoke_fn(prompt)->str, parse the verdict.
    invoke_fn returning None/empty (e.g. claude -p failed) yields 'inapplicable'."""
    prompt = build_judge_prompt(skill_name, skill_description, after_window)
    raw = invoke_fn(prompt)
    if not raw:
        return "inapplicable"
    return parse_verdict(raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_judge.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Checkpoint** — `python -m pytest tests -q` green.

---

### Task 7: Scoring — contribution score and (report-only) action classification

**Files:**
- Create: `Z:\agent-os\bin\skill_forge\scoring.py`
- Test: `Z:\agent-os\bin\tests\test_scoring.py`

- [ ] **Step 1: Write the failing test**

`Z:\agent-os\bin\tests\test_scoring.py`:
```python
import pytest
from skill_forge.scoring import contribution_score, classify_action


@pytest.mark.parametrize("verdicts,expected", [
    (["helped", "helped", "hurt"], pytest.approx((2 - 1) / 3)),     # trials=3
    (["helped", "helped"], pytest.approx(1.0)),
    (["hurt", "hurt"], pytest.approx(-1.0)),
    (["inapplicable", "inapplicable"], 0.0),   # no real trials -> 0
    ([], 0.0),
])
def test_contribution_score(verdicts, expected):
    assert contribution_score(verdicts) == expected


def test_inapplicable_excluded_from_trials():
    # 1 helped, 1 hurt, 5 inapplicable -> trials=2, score=0.0
    verdicts = ["helped", "hurt"] + ["inapplicable"] * 5
    assert contribution_score(verdicts) == pytest.approx(0.0)


def test_classify_action_dead_skill():
    # zero invocations is unambiguous, exempt from the evidence floor
    assert classify_action(trials=0, score=0.0, n_min=100, tau=0.10) == "dead"


def test_classify_action_insufficient_evidence_below_floor():
    # bad score but not enough trials -> must NOT recommend acting
    assert classify_action(trials=10, score=-0.9, n_min=100, tau=0.10) == "insufficient-evidence"


def test_classify_action_retire_when_floor_met_and_below_tau():
    assert classify_action(trials=120, score=-0.5, n_min=100, tau=0.10) == "retire-candidate"


def test_classify_action_healthy():
    assert classify_action(trials=120, score=0.4, n_min=100, tau=0.10) == "healthy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skill_forge.scoring'`

- [ ] **Step 3: Write the implementation**

`Z:\agent-os\bin\skill_forge\scoring.py`:
```python
"""Contribution scoring and (report-only) action classification.

Score: c(s) = (helped - hurt) / trials, where trials = helped+hurt+neutral.
'inapplicable' verdicts are excluded from trials (the window didn't show the
skill's outcome). Action classification is ADVISORY in Phase 0 — the refiner
only reports these labels; it never acts. The evidence floor (Nmin) is the
load-bearing guard from Library Drift (arxiv 2605.19576): acting below it
provably harms, so sub-floor skills are 'insufficient-evidence', never retired.
"""
from __future__ import annotations


def contribution_score(verdicts: list[str]) -> float:
    helped = verdicts.count("helped")
    hurt = verdicts.count("hurt")
    neutral = verdicts.count("neutral")
    trials = helped + hurt + neutral
    if trials == 0:
        return 0.0
    return (helped - hurt) / trials


def classify_action(trials: int, score: float, n_min: int, tau: float) -> str:
    """Advisory label (Phase 0 reports only):
      'dead'                  -> 0 invocations (exempt from floor; unambiguous)
      'insufficient-evidence' -> trials < n_min (DO NOT act — below evidence floor)
      'retire-candidate'      -> trials >= n_min AND score <= -tau
      'healthy'               -> trials >= n_min AND score > -tau
    """
    if trials == 0:
        return "dead"
    if trials < n_min:
        return "insufficient-evidence"
    if score <= -tau:
        return "retire-candidate"
    return "healthy"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Checkpoint** — `python -m pytest tests -q` green.

---

### Task 8: Report renderer

**Files:**
- Create: `Z:\agent-os\bin\skill_forge\report.py`
- Test: `Z:\agent-os\bin\tests\test_report.py`

- [ ] **Step 1: Write the failing test**

`Z:\agent-os\bin\tests\test_report.py`:
```python
from skill_forge.report import render_report


def _row(name, origin, trials, score, action, invocations):
    return {"name": name, "origin": origin, "trials": trials, "score": score,
            "action": action, "invocations": invocations}


def test_report_has_header_and_rows_and_is_readonly_labeled():
    rows = [
        _row("clone-route", "authored", 120, -0.50, "retire-candidate", 130),
        _row("watch", "authored", 4, -0.20, "insufficient-evidence", 4),
        _row("compose-shorts", "skill-forge", 0, 0.0, "dead", 0),
    ]
    md = render_report(rows, today="2026-05-30")
    assert "# Skill-Forge report — 2026-05-30" in md
    assert "READ-ONLY" in md                 # Phase 0 must label itself read-only
    assert "clone-route" in md and "retire-candidate" in md
    assert "insufficient-evidence" in md     # the floor guard is visible
    # green-on-top ordering: healthy/dead last, action items first is fine, but
    # the table must contain all three skills
    assert md.count("|") >= 12


def test_empty_report_states_no_skills():
    md = render_report([], today="2026-05-30")
    assert "no skills" in md.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skill_forge.report'`

- [ ] **Step 3: Write the implementation**

`Z:\agent-os\bin\skill_forge\report.py`:
```python
"""Render the weekly Skill-Forge report (Phase 0: read-only)."""
from __future__ import annotations

# Action items surface first (your green-on-top: most-actionable at the top).
_ACTION_ORDER = {"retire-candidate": 0, "insufficient-evidence": 1,
                 "dead": 2, "healthy": 3}


def render_report(rows: list[dict], today: str) -> str:
    head = (f"# Skill-Forge report — {today}\n\n"
            "> **READ-ONLY (Phase 0).** This report scores existing skills to\n"
            "> validate the signal. No skill was modified, installed, or retired.\n\n")
    if not rows:
        return head + "_No skills found to score._\n"
    ordered = sorted(rows, key=lambda r: (_ACTION_ORDER.get(r["action"], 9), -r["trials"]))
    lines = [head,
             "| Skill | Origin | Invocations | Trials | Contribution | Advisory |",
             "|---|---|---|---|---|---|"]
    for r in ordered:
        lines.append(
            f"| {r['name']} | {r['origin']} | {r['invocations']} | {r['trials']} "
            f"| {r['score']:+.2f} | {r['action']} |")
    lines.append("\n_Advisory labels only. Autonomy is enabled in Phase 2, "
                 "gated on the eval-harness precision check (skill-forge-eval.py)._\n")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_report.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Checkpoint** — `python -m pytest tests -q` green.

---

### Task 9: CLI entrypoint `skill-refiner.py` (score-only, with `--skip-claude`)

**Files:**
- Create: `Z:\agent-os\bin\skill-refiner.py`

This wires the units. The real `claude -p` invoker is copied from `weekly-planner.py` (verbatim pattern). A `--skip-claude` flag substitutes a stub invoker that returns `"VERDICT: inapplicable"` so the full pipeline can be exercised offline (and in the next task's smoke test before spending subscription messages).

- [ ] **Step 1: Write the entrypoint**

`Z:\agent-os\bin\skill-refiner.py`:
```python
"""skill-refiner.py — Skill-Forge Phase 0 (read-only signal validator).

Scores every skill in Z:\\agent-os\\skills\\ from claude-brain transcript
history and writes Z:\\agent-os\\forge\\report-latest.md. MODIFIES NOTHING.

Usage:
  python skill-refiner.py                 # full run (uses claude -p judge)
  python skill-refiner.py --skip-claude   # offline: stub judge (pipeline test)
  python skill-refiner.py --lookback-days 30
  python skill-refiner.py --verbose
"""
from __future__ import annotations
import argparse
import datetime as dt
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # find skill_forge package

from skill_forge import config
from skill_forge.skills_inventory import list_skills
from skill_forge.brain_query import find_invocations, get_after_window
from skill_forge.judge import classify_invocation
from skill_forge.scoring import contribution_score, classify_action
from skill_forge.report import render_report


def log(level: str, message: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} [{level}] {message}\n"
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="", file=sys.stderr)


def make_claude_invoker(timeout: int = 180):
    """Return invoke_fn(prompt)->str|None using `claude -p` (no tools, no hooks).
    Pattern copied from weekly-planner.py: subscription auth, fallback model,
    CLAUDE_BRAIN_SKIP_HOOKS so the judge call isn't polluted/recaptured."""
    claude_path = shutil.which("claude") or shutil.which("claude.exe") or shutil.which("claude.cmd")
    if not claude_path:
        log("ERROR", "claude CLI not found")
        return lambda prompt: None

    def invoke(prompt: str):
        env = os.environ.copy()
        env["CLAUDE_BRAIN_SKIP_HOOKS"] = "1"
        try:
            r = subprocess.run(
                [claude_path, "-p", "--no-session-persistence",
                 "--disallowed-tools", "Read Write Edit Bash Glob Grep WebFetch WebSearch",
                 "--fallback-model", "claude-sonnet-4-6"],
                input=prompt, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout, env=env)
        except Exception as e:  # noqa: BLE001 - log + degrade to inapplicable
            log("WARN", f"claude judge invocation failed: {type(e).__name__}: {e}")
            return None
        if r.returncode != 0:
            log("WARN", f"claude judge non-zero: {r.stderr[:300]}")
            return None
        return r.stdout.strip()

    return invoke


def score_skill(conn, skill, since, invoke_fn, verbose=False) -> dict:
    invs = find_invocations(conn, skill["name"], since=since)
    verdicts: list[str] = []
    for inv in invs:
        window = get_after_window(conn, inv["session_id"], inv["timestamp"],
                                  limit=config.AFTER_WINDOW)
        if not window:
            verdicts.append("inapplicable")
            continue
        verdicts.append(classify_invocation(
            skill["name"], skill["description"], window, invoke_fn))
    score = contribution_score(verdicts)
    trials = sum(1 for v in verdicts if v in ("helped", "hurt", "neutral"))
    action = classify_action(trials, score, config.N_MIN, config.TAU)
    if verbose:
        log("INFO", f"  {skill['name']}: invocations={len(invs)} trials={trials} "
                    f"score={score:+.2f} -> {action}")
    return {"name": skill["name"], "origin": skill["origin"],
            "invocations": len(invs), "trials": trials, "score": score, "action": action}


def main() -> int:
    ap = argparse.ArgumentParser(description="Skill-Forge Phase 0 signal validator (read-only).")
    ap.add_argument("--skip-claude", action="store_true",
                    help="Use a stub judge (offline pipeline test).")
    ap.add_argument("--lookback-days", type=int, default=config.LOOKBACK_DAYS)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    log("INFO", f"skill-refiner Phase 0 starting (skip_claude={args.skip_claude}, "
                f"lookback={args.lookback_days}d)")

    if not config.BRAIN_DB.exists():
        log("ERROR", f"brain DB not found: {config.BRAIN_DB}")
        return 1

    since = (dt.datetime.now(dt.timezone.utc)
             - dt.timedelta(days=args.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    skills = list_skills(config.SKILLS_DIR)
    log("INFO", f"scoring {len(skills)} skills since {since}")

    invoke_fn = (lambda prompt: "VERDICT: inapplicable") if args.skip_claude else make_claude_invoker()

    conn = sqlite3.connect(f"file:{config.BRAIN_DB}?mode=ro", uri=True)
    try:
        rows = [score_skill(conn, s, since, invoke_fn, args.verbose) for s in skills]
    finally:
        conn.close()

    today = dt.date.today().isoformat()
    md = render_report(rows, today=today)
    config.REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.REPORT_PATH.write_text(md, encoding="utf-8")
    log("INFO", f"wrote report ({len(md)} chars) -> {config.REPORT_PATH}")

    # Deliver to Slack (no-op if webhook unset) — reuse the existing helper.
    try:
        from notify_slack import post_slack
        post_slack(md, title=f"[NAME] — Skill-Forge report ({today})")
    except Exception as e:  # noqa: BLE001
        log("WARN", f"Slack notify skipped: {type(e).__name__}: {e}")

    log("INFO", "skill-refiner done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the offline pipeline against the real brain (read-only, no subscription spend)**

Run (from `Z:\agent-os\bin`): `python skill-refiner.py --skip-claude --verbose`
Expected: exits 0; logs `scoring N skills`; writes `Z:\agent-os\forge\report-latest.md`. Every skill shows `action=dead` or `insufficient-evidence` (stub judge returns inapplicable → trials=0), proving the wiring and the read-only path without spending any messages.

- [ ] **Step 3: Open the report and sanity-check**

Run: `type Z:\agent-os\forge\report-latest.md`
Expected: the READ-ONLY header + a table listing your real skills (`clone-route`, `session-reflect`, `watch`, etc.) with invocation counts pulled from the brain.

- [ ] **Step 4: Checkpoint** — report file exists and lists real skills; `python -m pytest tests -q` still green.

---

### Task 10: Live smoke test (one real `claude -p` judged run)

**Files:** none (operational validation).

- [ ] **Step 1: Run the real judge against a short lookback**

Run (from `Z:\agent-os\bin`): `python skill-refiner.py --lookback-days 21 --verbose`
Expected: exits 0. For skills with recent invocations, the log shows non-zero `trials` and a real `score`. Subscription cost is bounded (one short `claude -p` call per invocation found in the last 21 days; the log prints how many).

- [ ] **Step 2: Read the report and eyeball 3–5 verdicts against your memory**

Run: `type Z:\agent-os\forge\report-latest.md`
Manually confirm: skills you know you used successfully are not flagged `retire-candidate`; anything flagged is plausibly a real problem. This is a gut-check before the formal precision measurement in Task 11.

- [ ] **Step 3: Checkpoint** — a real judged report exists; no skill files were modified (`git`-free — verify by checking `skills/` mtimes are unchanged, e.g. `dir Z:\agent-os\skills /s /t:w`).

---

### Task 11: Eval harness — measure judge precision (the Phase-1 unlock gate)

**Files:**
- Create: `Z:\agent-os\forge\eval\labels.sample.jsonl`
- Create: `Z:\agent-os\bin\skill-forge-eval.py`

The decision the whole loop hinges on: **is the judge's `hurt` verdict trustworthy enough to ever act on?** Research says implicit-correction detection runs ~55–60% precision in general (arxiv 2507.23158), so we must measure *our* judge on *our* transcripts. Gate: **≥80% precision on the `hurt` class** before Phase 2 autonomy is built.

- [ ] **Step 1: Hand-label a gold sample**

Create `Z:\agent-os\forge\eval\labels.sample.jsonl` — one JSON object per line, each a real outcome window you label by hand. Start with ~30 (aim for ~10 genuine `hurt` cases so precision is measurable). Format:
```json
{"skill": "clone-route", "description": "Route inbox content.", "gold": "hurt", "window": [{"role": "assistant", "content": "Routed to joey."}, {"role": "user", "content": "no, that should be kallaway"}]}
{"skill": "watch", "description": "Watch a video.", "gold": "helped", "window": [{"role": "assistant", "content": "Here's the summary."}, {"role": "user", "content": "great, thanks"}]}
```
(Pull real windows by skimming `forge/report-latest.md` invocation sites, or query the brain directly.)

- [ ] **Step 2: Write the eval harness**

`Z:\agent-os\bin\skill-forge-eval.py`:
```python
"""skill-forge-eval.py — measure the judge's precision on a hand-labeled set.

Phase-1 unlock gate: prints precision/recall for the 'hurt' class. Do NOT build
Phase 2 autonomy until hurt-precision >= 0.80 on a sample with >= ~10 hurt cases.

Usage:
  python skill-forge-eval.py                              # uses claude -p
  python skill-forge-eval.py --labels path\\to\\labels.jsonl
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_forge.judge import classify_invocation
from skill_forge import config

# Reuse the refiner's real invoker.
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "skill_refiner", str(Path(__file__).resolve().parent / "skill-refiner.py"))
_refiner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_refiner)


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure Skill-Forge judge precision.")
    ap.add_argument("--labels", default=str(config.FORGE_DIR / "eval" / "labels.sample.jsonl"))
    args = ap.parse_args()

    path = Path(args.labels)
    if not path.exists():
        print(f"labels file not found: {path}", file=sys.stderr)
        return 1
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases:
        print("no labeled cases", file=sys.stderr)
        return 1

    invoke_fn = _refiner.make_claude_invoker()
    tp = fp = fn = correct = 0
    for c in cases:
        pred = classify_invocation(c["skill"], c.get("description", ""), c["window"], invoke_fn)
        gold = c["gold"]
        if pred == gold:
            correct += 1
        if pred == "hurt" and gold == "hurt":
            tp += 1
        elif pred == "hurt" and gold != "hurt":
            fp += 1
        elif pred != "hurt" and gold == "hurt":
            fn += 1

    hurt_precision = tp / (tp + fp) if (tp + fp) else 0.0
    hurt_recall = tp / (tp + fn) if (tp + fn) else 0.0
    print(f"cases={len(cases)} overall_accuracy={correct/len(cases):.2%}")
    print(f"HURT precision={hurt_precision:.2%} recall={hurt_recall:.2%} (tp={tp} fp={fp} fn={fn})")
    gate = "PASS" if hurt_precision >= 0.80 and (tp + fn) >= 10 else "FAIL"
    print(f"Phase-2 unlock gate (hurt-precision >= 80%, >= 10 hurt cases): {gate}")
    return 0 if gate == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the eval**

Run (from `Z:\agent-os\bin`): `python skill-forge-eval.py`
Expected: prints overall accuracy + `HURT precision/recall` + a `PASS`/`FAIL` gate line. The number itself is the deliverable — it tells us whether Phase 2 autonomy is safe to build, or whether the judge prompt needs iteration first.

- [ ] **Step 4: Record the result in the spec**

Append the measured precision and date to `Z:\agent-os\docs\specs\2026-05-29-skill-forge-design.md` §10 (the "classifier precision target" open question). If `FAIL`, the Phase 1 plan's first task is judge-prompt iteration; if `PASS`, Phase 1 (the Miner) and Phase 2 (scoped autonomy) are cleared to plan.

- [ ] **Step 5: Checkpoint** — `python -m pytest tests -q` green; eval prints a gate verdict.

---

## Phase 0 done — what exists and what's next

**Exists:** a tested, read-only `skill-refiner` that turns brain history into a scored skill report, and a precision number that says whether the `hurt` signal is trustworthy.

**Explicitly deferred to later plans (their own spec→plan cycle):**
- **Phase 1 (Miner):** `skill-miner.py` — mine the brain for recurring ≥2× procedures → draft `forge/queue/` candidates → install path. Scheduled-task registration (`install-skill-forge.bat`) lands here.
- **Phase 2 (Autonomous refine, Forge-minted only):** snapshot → revise/quarantine → AgentShield rollback, rate-limit, cooldown, active-cap enforcement, kill switch.
- **Phase 3 (Expand envelope):** open the protected set using the proven precision data.

Each is gated on the Task 11 precision result.
