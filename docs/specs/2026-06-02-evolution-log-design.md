# Evolution Audit Trail — Design Spec

**Date:** 2026-06-02
**Status:** Approved
**Inspired by:** [EvoMap/evolver](https://github.com/EvoMap/evolver) — the EvolutionEvent audit-trail concept, adapted to agent-os conventions. (The GEP framework itself is not used; only the changelog idea.)

---

## Problem

agent-os memory files record the *current state* of rules, projects, and identity facts, but there is no record of *how things changed over time* — what broke, what was fixed, what drove the decision. After a repair like the `[voice]` ASCII sentinel fix, the feedback file records the rule but not the incident, the date, or the reasoning chain. The brain has transcript history, but it requires natural-language search and doesn't surface structured evolution signal.

---

## Solution

An append-only JSONL file — `Z:\agent-os\forge\evolution.jsonl` — that logs one entry per change to any agent-os asset (memory files, skills, settings). Each entry captures: when, what asset, what changed, why, what strategy drove it, and which session it came from.

This is a **convention**, not an enforced system. Writers follow the convention; there is no validator or hook.

---

## File

```
Z:\agent-os\forge\evolution.jsonl
```

Alongside `skill-usage.jsonl`. Append-only. Never truncated or rewritten — only appended to.

---

## Schema

One JSON object per line:

```json
{
  "ts": "2026-06-02T14:32:00Z",
  "strategy": "repair",
  "asset": "feedback/voice_summary_line.md",
  "what": "Added ASCII [voice] sentinel rule instead of emoji",
  "why": "cp1252 silently drops emoji bytes; voice never fired despite rule existing",
  "session": "e13e1050"
}
```

**Fields:**

| Field | Type | Description |
|---|---|---|
| `ts` | ISO 8601 string | Timestamp of the write |
| `strategy` | enum (see below) | What kind of evolution drove this change |
| `asset` | string | Path relative to `Z:\agent-os\` (e.g. `feedback/rule.md`, `skills/clone-route/SKILL.md`, `settings`) |
| `what` | string | One sentence: what changed |
| `why` | string | One sentence: why — the incident, signal, or reason |
| `session` | string | First 8 chars of the session ID (from brain context or `$CLAUDE_SESSION_ID`) |

---

## Strategies

Adapted from Evolver's preset vocabulary to agent-os semantics:

| strategy | when to use |
|---|---|
| `repair` | Fixing a broken behavior, wrong rule, or incorrect assumption — something was causing harm or failing |
| `harden` | Strengthening a working pattern — adding more explicit guidance, tighter scope, or edge-case coverage to something that already works |
| `innovate` | New capability — new skill, new project brief, new tool, new scheduled agent |
| `calibrate` | Adjusting autonomy level, collaboration balance, or a threshold (e.g. Skill-Forge's evidence floor) |
| `document` | First-time capture of something already happening implicitly — no behavior change, just making the rule explicit |

When in doubt between `repair` and `harden`: if the absence of the rule caused a failure, it's `repair`. If the rule existed but was underspecified, it's `harden`.

---

## Writers

### session-reflect (primary writer)

Step 5 of session-reflect is extended: **before** writing each approved memory/skill file, Claude appends an evolution entry to `forge/evolution.jsonl`.

Strategy is inferred from candidate category:

| session-reflect category | default strategy |
|---|---|
| Behavioral correction (Tre said "no / don't") | `repair` |
| Confirmed approach (Tre said "yes, that was right") | `harden` |
| New skill candidate | `innovate` |
| New project brief | `innovate` |
| Project state update | `calibrate` |
| Identity fact about Tre | `document` |
| Anti-pattern / presentation rejection | `repair` |

Claude picks the strategy; the entry is shown alongside the memory candidate in the approval step so Tre can correct it before it's written.

### Skill-Forge

`bin/skill_forge/` and `bin/skill-refiner.py` append an entry:
- On skill **install** → `innovate`
- On skill **revision** (Forge-minted, Phase 2+) → `harden`
- On skill **quarantine/retirement** → `repair` (something was hurting)

### Direct Claude edits (standing convention)

When Claude writes or edits any file under `Z:\agent-os\memory\` or `Z:\agent-os\skills\` outside of session-reflect (e.g. responding to "update this rule" directly in conversation), it appends an evolution entry **before** making the edit. This is enforced via a feedback rule (`feedback/evolution_log_convention.md`), not a hook.

---

## Reading the log

No dedicated viewer in Phase 1. Use:

```powershell
# last 20 entries, formatted
Get-Content Z:\agent-os\forge\evolution.jsonl -Tail 20 | ForEach-Object { $_ | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"{d['ts'][:10]}  [{d['strategy']:10}]  {d['asset']}\")" }

# all repairs
Get-Content Z:\agent-os\forge\evolution.jsonl | python3 -c "import sys,json; [print(json.dumps(json.loads(l), indent=2)) for l in sys.stdin if json.loads(l)['strategy']=='repair']"
```

Skill-Forge Phase 3+ may add structured queries against this file (e.g. "show all changes to skill X over time").

---

## What this is NOT

- Not a code patcher (like Evolver's full GEP system) — entries are human/LLM-readable logs, not executable patches
- Not enforced by a hook — convention-based; relies on Claude following the standing rule
- Not a replacement for the brain — the brain has full transcript context; this has structured signal optimized for querying
- Not versioned/committed — agent-os is not a git repo; the log is local-only

---

## Integration points

1. **session-reflect** — extend Step 5 (one new sub-step per approved write)
2. **Skill-Forge** — three call sites in `bin/skill_forge/` + `bin/skill-refiner.py`
3. **MEMORY.md** — add a reference line under "Reference — tooling / setup"
4. **feedback/evolution_log_convention.md** — standing rule for direct Claude edits
5. **`Z:\agent-os\skills\_index.md`** — no change needed (this isn't a skill)

---

## Out of scope (Phase 1)

- A dedicated viewer/skill (`/evo-log`)
- Retroactive backfill of past changes
- Automated strategy inference via LLM
- Hook-based automatic capture (loses WHY; deprioritized per design discussion)
