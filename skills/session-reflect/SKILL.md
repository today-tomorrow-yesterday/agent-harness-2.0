---
name: session-reflect
description: Self-noticing reflection — scans the current session's transcript for moments of correction, surprise, confirmed approaches, or novel standing guidance, drafts candidate memory entries (feedback rules, project facts, identity notes, ideas, anti-patterns), and asks you to approve each one before writing into Z:\agent-os\memory\. The capture layer of the meta-learning loop. Use when you say "what did we learn today", "reflect on this session", "save what's important", "/session-reflect", or whenever you notice corrections piling up unsaved during a conversation.
---

# session-reflect — capture layer for the meta-learning loop

This skill turns the conversation we just had into memory candidates. Claude drafts each candidate; you approve them individually; approved ones get written into `Z:\agent-os\memory\` with the right frontmatter, type, folder placement, and cross-references.

## Why this exists

Memory writes today only happen when you explicitly types "save this." That means corrections, surprises, and confirmed-good approaches evaporate at the end of each session. This skill is **Layer 2 (capture)** of the meta-learning loop documented in [[projects/agent_os]]:

| Layer | What it does | Status before this skill |
|---|---|---|
| 1. Observation | See ourselves working | Partial — brain DB has transcripts |
| **2. Capture** | **Mark "this just happened, worth keeping"** | **None — depended on you typing it** |
| 3. Pattern recognition | Aggregate captures over time | None |
| 4. Hypothesis | Propose new rules / skills | Rules: yes (this skill). **Skills: now proposed here too** (see "Skill candidate" below) |
| 5. Apply + measure | Test the rule, see if it changed behavior | None |
| 6. Codify | Make proven things standing | Strong — memory, skills, feedback |

Claude drafts; you approve; the loop accumulates signal it can later compute on.

## When to invoke

- you say: *"what did we learn today"*, *"reflect on this session"*, *"save what's important from this"*, *"what should I capture"*, *"/session-reflect"*
- Claude proactively offers when 2+ corrections or confirmed-good approaches have accumulated in the current session without being saved
- After a conversation that introduced standing rules, project decisions, or new identity facts
- End of any conversation where the topic had load-bearing implications

**Do NOT invoke** for trivial sessions (one-off lookups, simple bug fixes, "just answer my question" exchanges). The capture overhead isn't worth it for sessions that produced no signal.

## What to look for — candidate categories

| Category | Target | Trigger pattern |
|---|---|---|
| **Behavioral correction** | `feedback/<rule>.md` (new) | you say "no don't do that", "stop doing X", "you're misinterpreting" |
| **Confirmed approach** | `feedback/<rule>.md` (new) | you accepts an unusual choice without pushback, or says "yes that was the right call" |
| **Project state change** | `projects/<project>.md` (append section) or new file | New deadline, scope decision, status shift |
| **Identity fact about you** | `user.md` (append section) | New background, preference, goal, motivation surfaced |
| **Pre-project idea** | `ideas/<slug>.md` (new) + `ideas/_index.md` entry | you mentions a concept worth catalog-capturing |
| **Presentation anti-pattern** | `feedback/anti_patterns.md` (append section) | you rejects a format, style, or layout |
| **Reference pointer** | `feedback/<system>_reference.md` (new) | New external system, dashboard, tool mentioned |
| **Skill candidate** | new `skills/<name>/SKILL.md` (propose-then-scaffold) + install in both profiles | A repeatable multi-step workflow was executed manually 2+ times (this session or recurring), or you say "make this a skill / automate this". The agent-os-native version of Hermes's autonomous skill creation — see [[self_improving_skills]] |

## The reflection process — 5 steps

### Step 1 — Scope

Decide which transcript to reflect on:
- **Default**: the current in-context conversation
- **Past session**: if you say "reflect on yesterday's session" or similar, use brain MCP (`get_recent_sessions`, `get_session`) to pull the named session, then proceed against that text

### Step 2 — Scan for signals

Look for these patterns in the transcript:

🟢 **Explicit corrections** — *"no"*, *"don't"*, *"stop doing X"*, *"you're misinterpreting"*, frustrated pushback
🟢 **Explicit confirmations of non-obvious choices** — *"yes that was right"*, *"good call"*, quiet acceptance of an unusual approach the assistant proposed
🟢 **New facts dropped in conversation** — deadlines, people, project decisions, tools, dollar figures
🟢 **New identity context** — background, family, goals, motivations not yet in `user.md`
🟢 **Repeated frustration on the same theme** — three or more pushbacks on related topics
🟢 **Repeatable workflow done manually** — the same multi-step procedure ran 2+ times (this session, or recurring across sessions per the brain) that could be encoded as a reusable skill. This is the "observe → propose skill" half of the self-improving loop; draft a `SKILL.md` candidate, don't just note it

Reject these as non-candidates:

🔴 **One-off task details** — current bug, current PR, current command
🔴 **Ephemeral state** — "checking X right now", "running the script"
🔴 **Already captured** — check `MEMORY.md` index first; if the rule/fact already exists, skip or propose an *update* (not a new file)

### Step 3 — Draft candidates

For each accepted signal, draft a candidate memory file in full:
- **Filename** — lowercase-kebab-case, descriptive (e.g., `no_github_remote_for_agent_os.md`)
- **Target folder** — per the table above
- **Frontmatter** matching the convention used elsewhere in `Z:\agent-os\memory\`
- **Body** with the rule/fact + **Why** + **How to apply** sections (for feedback type)
- **Cross-references** via `[[wikilinks]]`

Frontmatter shape:

```yaml
---
name: <slug-matching-filename>
description: <one-line summary used for relevance matching in future sessions; be specific>
type: <feedback|project|idea|reference>
---
```

Body shape for `feedback` type (mirroring `feedback/never_commit_without_permission.md`):

```markdown
# <Title>

<The rule itself, stated plainly in 1–3 sentences>

**Why:** <The reason — often a specific incident or strong preference you stated, with the date>

**How to apply:** <When/where this rule kicks in; how to judge edge cases>

## Cross-references

- [[related_slug_1]]
- [[related_slug_2]]
```

Body shape for `project` updates: append a dated section to the existing `projects/<name>.md` rather than creating a new file, unless the scope is genuinely a new project brief.

### Step 4 — Propose-then-confirm

Present candidates to you via **AskUserQuestion with `multiSelect: true`**. Up to 4 candidates per question (the tool's max); if there are more, batch into two asks.

Question shape:

```
Question: "I noticed <N> capture candidates from this session. Which should I save?"
Header: "Captures"
Options (one per candidate):
  - label: "<proposed filename> — <one-line summary>"
    description: "<target folder + first 1-2 lines of proposed content>"
```

you select which to save. Unselected candidates are discarded silently — that's the whole point. False positives have zero cost beyond the moment of asking.

For each approved candidate, before writing:
- If it would **overwrite an existing file**, follow up: *"`<filename>` already exists. Append, replace, or skip?"*
- If the candidate uses a **new category** (e.g., a `type:` value not seen before), confirm the placement once

### Step 5 — Write + index

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

   Show the inferred strategy alongside the memory candidate in the Step 4 proposal so you can correct it before anything is written. `asset` = path relative to `Z:\agent-os\` (e.g. `feedback/my_rule.md`). `session` = first 8 chars of session ID from brain context.

1. **Write the file** to its target location with the full frontmatter + body
2. **Update `Z:\agent-os\memory\MEMORY.md`** by adding the new entry under the correct section (`Behavioral rules`, `Active projects`, `Ideas`, or `Top-level`)
3. **Append, don't overwrite**, when the target is an existing file like `feedback/anti_patterns.md`, `ideas/_index.md`, or `user.md`

After all writes, report a short summary:

- 🟢 Files written (full paths)
- 🟢 `MEMORY.md` index updated (which sections gained entries)
- 🟡 Cross-references created (note any `[[wikilinks]]` that point to slugs not yet created — that's fine, marks future captures)
- 🚫 Candidates skipped per your selection (just count, no detail needed)

## Frontmatter type values

| `type:` | When to use | Example file |
|---|---|---|
| `feedback` | Standing behavioral rules | `feedback/never_commit_without_permission.md` |
| `project` | Active project briefs | `projects/clone.md` |
| `idea` | Captured concepts pre-project | `ideas/ai_cinematic_content.md` |
| `user` | Identity facts (usually appended to `user.md`, rarely new files) | n/a — section-append |
| `reference` | Pointers to external systems / dashboards / tools | (none yet — pioneer this when needed) |

## Filename conventions

- **lowercase-kebab-case** for slugs (matches existing `feedback/` convention)
- Filename ≡ `name:` in frontmatter ≡ wikilink target — keep all three identical
- Descriptive over abbreviated — `no_github_remote_for_agent_os.md` beats `no_remote.md`

## Cross-references — `[[wikilinks]]`

Use `[[slug]]` syntax (matches the `name:` field in the frontmatter of the target file). Link liberally:

- **Unmatched links are fine** — they mark "this related memory should exist eventually"
- **Reciprocal links** are good — when adding `[[A]]` to B's cross-refs, consider adding `[[B]]` to A's if relevant
- **No link extension** (`[[name]]`, not `[[name.md]]`)

## What this skill does NOT do

- **No auto-commit.** `Z:\agent-os\` is not a git repo by design. Memory writes happen, no commit fires. The auto-commit hook at `Z:\agent-os\bin\hooks\auto-commit.ps1` is scoped to `Z:\Clone\` only.
- **No automatic invocation.** Manual trigger only for now. A future iteration may add a `Stop` hook integration once you has validated the false-positive rate. The brain's existing `Stop` hook owns that lifecycle slot today — coordinate any future automation with the brain hooks, don't compete.
- **No modification of existing memory files without explicit confirmation.** Append-to-existing is acceptable (e.g., `anti_patterns.md`, `user.md`), but ask first when the file already exists and the candidate would change its contents.
- **No broader-brain search by default.** Scope is the current session unless you explicitly names another session ID or date.
- **No git operations** of any kind. Per [[never_commit_without_permission]]. The skill produces files; it does not touch version control.
- **Proposes NEW skills, never silently rewrites existing ones.** When it detects a repeatable workflow (2+ manual runs), it may draft a **new** `skills/<name>/SKILL.md` candidate for your approval — the agent-os-native version of Hermes's autonomous skill creation (see [[self_improving_skills]]). On approval it scaffolds the skill and flags the both-profile install per [[parallel_subscriptions]]. It does NOT edit *existing* `SKILL.md` files without explicit confirmation.

## Reversibility

If a memory file gets written that you doesn't want:

1. **Delete the file**: `rm Z:\agent-os\memory\<folder>\<slug>.md`
2. **Remove the line** from `MEMORY.md` index
3. *Optional*: add the slug to a `feedback_anti_capture_signals.md` so future runs don't propose the same shape (this file doesn't exist yet — pioneer it when needed)

For appended-to files (`anti_patterns.md`, `user.md`, `_index.md`): manually remove the new section via Edit. No automation for this — append-then-rollback is rare enough that manual is fine.

## Parallel-subscription install

Per [[parallel_subscriptions]], this skill must live in three locations:

| Path | Role |
|---|---|
| `Z:\agent-os\skills\session-reflect\SKILL.md` | Canonical (source of truth) |
| `C:\Users\<USERNAME>\.claude-<profile>\skills\session-reflect\SKILL.md` | <profile2> profile install |
| `C:\Users\<USERNAME>\.claude\skills\session-reflect\SKILL.md` | Personal profile install |

All three must hold identical content. When this skill evolves, update all three.

## Cross-references

- [[projects/agent_os]] — meta-learning loop architecture this skill operationalizes (Layer 2)
- [[memory_routing]] — identity-level memory goes to `Z:\agent-os\memory\`, not the harness default
- [[parallel_subscriptions]] — rule for installing this skill in every Claude profile
- [[anti_patterns]] — one of the existing files this skill may append to
- [[never_commit_without_permission]] — why this skill never commits
- `Z:\agent-os\skills\clone-onboard\SKILL.md` — sibling skill following the same propose-then-confirm pattern
- `Z:\agent-os\bin\hooks\auto-commit.ps1` — Clone-scoped commit hook (NOT triggered by this skill's writes)
