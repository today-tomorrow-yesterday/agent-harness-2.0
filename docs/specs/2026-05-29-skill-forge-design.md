---
title: Skill-Forge — self-improving skills closed loop
status: design (awaiting you review)
date: 2026-05-29
author: [NAME] + you (brainstorming session)
related:
  - ideas/self_improving_skills.md
  - projects/agent_os.md   ("Hermes comparison & capability roadmap")
  - feedback/calibrate_before_automate.md
  - feedback/ai_does_95_percent_of_production.md
  - feedback/parallel_subscriptions.md
  - feedback/subscription_first_design.md
  - feedback/local_first_architecture.md
  - frame.md  (the load-bearing design question)
---

# Skill-Forge — self-improving skills closed loop

## 1. Purpose

Close agent-os's self-improvement loop at the **skill layer**. Today agent-os
self-improves at the *memory* layer (claude-brain + `session-reflect`), but
skills are still authored manually except for the `session-reflect` skill-
candidate step. Skill-Forge makes [NAME] **mine its own recurring work into new
skills, and measure + maintain the skills it already has** — the one capability
the 2026-05-28 Hermes comparison flagged as genuinely missing, and the one that
*compounds* (every encoded workflow makes the next execution cheaper — the
`ai_does_95_percent_of_production` trajectory).

Against `frame.md`'s load-bearing question — *"does this relax a constraint on
[NAME]'s functional analog of partnership-capable agency?"* — yes: it relaxes the
constraint that [NAME]'s capability set only grows when you hand-authors it.

## 2. Scope

The **full closed loop**: `mine → propose → install → measure → flag →
autonomously refine`. Stages `draft / propose / install` already exist in manual
form (`session-reflect`); this spec adds the two missing pieces — **autonomous
DETECT** (cross-session mining) and **autonomous REFINE** (usage-driven
maintenance) — and wires them into one cycle.

Built and proven in **four phases** (Section 8). "Fully autonomous refine" is
the *destination* (Phase 2–3), not the starting point.

### Out of scope
- A new `PostToolUse` usage-logging hook (evaluated and rejected — see §5).
- Making agent-os a git repo (it deliberately is not; reversibility is
  filesystem-based — see §6).
- Voice, messaging harness, always-on cloud runtime (separate gaps).

## 3. Architecture

Two net-new components, both reading the brain; two existing systems extended.

```
                          SKILL-FORGE  (Z:\agent-os\)

  Skill-Miner  (scheduled, Sun 09:30)         Skill-Refiner (scheduled, Sun 09:45)
  ─ DETECT recurring procedures (brain)       ─ SCORE each installed skill
  ─ DRAFT  SKILL.md candidates                  • frequency/recency (brain)
  ─ writes ► forge/queue/<date>_<slug>/         • correction/abandonment (LLM judgment)
       (proposes only — never installs)        ─ ACT autonomously (Forge-minted skills only):
                  │                               • dead    → snapshot → quarantine
                  │                               • corrected → snapshot → auto-revise → AgentShield
                  ▼                               • healthy → leave
            forge-review                        ─ writes ► skill-forge.log + forge/report-latest.md
   report-latest.md → Slack (notify_slack.py)               │
   + weekly brief; you approves installs,                   ▼
   can --revert any auto-action            install path (extends session-reflect):
                                           approved candidate → scaffold skills/
                                           + both-profile install + AgentShield scan
```

| Component | New? | Job | Builds on |
|---|---|---|---|
| `Skill-Miner` | net-new | weekly: mine brain → draft candidates → queue | Farmer pattern, `claude -p`, parallel readers |
| `Skill-Refiner` | net-new | weekly: score → autonomously revise/quarantine | Farmer pattern, filesystem versioning |
| `forge-review` | extends | surface proposals + auto-action log for approval | Weekly-Planner / `notify_slack.py` |
| install path | extends | approved candidate → both-profile install + scan | `session-reflect`, AgentShield-Watch |

**Boundaries (each unit one job):** Miner only *proposes* (writes a queue,
never installs). Refiner only touches *existing* skills (revise/quarantine,
never creates). Install is the *only* path that adds a skill, and it is always
human-approved.

## 4. File layout

All under `Z:\agent-os\`, matching existing `bin/` + scheduled-task + log
conventions.

```
bin\
  skill-miner.py / .ps1        DETECT + DRAFT  (wrapper mirrors farmer-youtube.ps1)
  skill-refiner.py / .ps1      SCORE + autonomous ACT
  skill-forge-state.json       seen-procedures, last-scored, cooldowns, KILL SWITCH
  install-skill-forge.bat      registers both Scheduled Tasks
  uninstall-skill-forge.bat
forge\
  queue\<date>_<slug>\         candidate: SKILL.md + rationale.md + evidence.md
  versions\<skill>\<ts>\       pre-change snapshot (revert source)
  quarantine\<skill>\          retired skills (moved, not deleted)
  report-latest.md             newest weekly forge report
skill-forge.log                append-only action log (matches farmer logs)
skills\                        existing source skills (location unchanged)
```

## 5. The usage-signal mechanism

The Refiner's signal substrate is **the brain** (claude-brain). No new hook.

| Signal | Hard/soft | Derivation |
|---|---|---|
| frequency / recency | hard | count skill invocations in the brain over the window (Skill-tool calls + `<command-name>` slash lines) |
| attribution verdict | soft | LLM-judgment (`claude -p`) reads the transcript window *after* each invocation and labels it `helped / hurt / neutral / inapplicable` (per Library Drift, arxiv 2605.19576) |
| correction type | soft | finer classification of `hurt` verdicts using the implicit-feedback taxonomy (arxiv 2507.23158): `rephrasing / make-aware-no-correction / make-aware-with-correction / ask-clarification` |

**Contribution score** (per skill): `ĉ(s) = (helped − hurt) / trials`. Combined
with frequency (value) and recency (staleness).

**Signal-noise reality (researched):** LLM classification of implicit
correction signals is **noisy** — ~81% accuracy on easy cases but only ~42% on
hard ones; three-way precision 55–60% (arxiv 2507.23158). A single verdict is
therefore *not* actionable. This is why the **evidence floor** (§6) is
non-negotiable: only act once enough trials accumulate for the noise to average
out. It is also why Phase 0 (read-only signal validation) must run long enough
to measure our own classifier's precision before any autonomy is enabled.

**Judge-bias mitigation:** [NAME] scoring skills [NAME] authored is a textbook
self-preference-bias risk (NeurIPS 2024; RAND 2026 — *no judge is uniformly
reliable*). Mitigations: score against a **structured rubric** (not free-form),
and prefer a *different* model snapshot as judge than the one that drafted the
skill where practical.

**Why a `PostToolUse` usage-logger hook IS required (reversed 2026-05-30, empirically):**
The original design assumed the brain captures skill invocations queryably. **Phase 0
disproved this.** The built `skill-refiner` ran its SQL `LIKE` detection against the
real brain DB and found ~0 invocations for heavily-used custom skills (e.g.
`clone-route`). Direct inspection confirmed why:
- `<command-name>…</command-name>` in `transcripts.content` only captures **typed
  slash commands** — overwhelmingly built-ins (`/theme`, `/model`); a custom skill
  appears this way only on the rare occasion it's typed as `/skill` (e.g. exactly
  one `/session-reflect` hit in all history).
- The **dominant invocation path** — you asks in natural language → [NAME] calls the
  **Skill tool** — is **not stored in `transcripts.content` in any of the four
  detection forms.** The brain captures *discussion of* skills, not *structured
  invocations of* them.

**Consequence:** brain-derived frequency is unreliable for custom skills. A
`PostToolUse` hook matching the `Skill` tool, appending one JSONL line per
invocation, is the reliable source — installed in **both profiles**
(`parallel_subscriptions`). Caveat: the hook is **forward-only** (captures from
install-date onward, not history), so the contribution-score evidence floor
(`Nₘᵢₙ`) accumulates *after* install rather than from existing transcripts. The
brain still serves the **correction/abandonment** half of the signal (the judge
reads the after-window around whatever invocations we can locate); the hook
serves the **frequency** half.

**Frequency needs BOTH sources combined (refined 2026-05-30):** the hook captures
only **Skill-tool** invocations (Claude-initiated). It misses two real usage
paths, so frequency must union the hook with the brain's `<command-name>` signal,
and even then has a known blind spot:
- **Typed slash commands** (`/clone-route`) → captured by the brain's
  `<command-name>` lines, not the hook. Union both sources.
- **Scheduled farmers** → a hard blind spot. `farmer-route.py` etc. do NOT invoke
  the `clone-route` Skill; they replicate the logic via a `claude -p` procedural
  prompt. So the daily/weekly automated routing of the roster generates **zero**
  skill invocations in either source. This usage is real but uncounted. A skill
  known to be farmer-driven must be flagged so it is never scored as low-use
  (feeds the §6 maturity gate, condition (c)).

**Alignment with how you actually works (2026-05-30):** you interacts by
describing intent in natural language, never via slash commands — so [NAME] invokes
skills through the **Skill tool**. That makes the hook (Skill-tool capture) the
*primary, correctly-aligned* frequency source, and the brain `<command-name>`
union a minor backstop. The deeper end-state this points to: **intention-driven
routing** — NL intent → the system auto-selects/fires skills via pre/post hooks,
needing no manual trigger from you. Skill-Forge is the self-learning organ of
that larger system. See [[complementary_division_of_labor]].

## 6. Autonomy & safety model

Invariant for every autonomous action: **snapshot → act → scan → log →
auto-rollback on failure.**

agent-os is intentionally **not a git repo**, so reversibility is
filesystem-based (snapshots + quarantine), not `git revert`.

| Guardrail | Rule |
|---|---|
| **Evidence floor** 🔴 | Never autonomously revise/retire a skill until it has `trials ≥ Nₘᵢₙ` invocations (start `Nₘᵢₙ = 100` per Library Drift; tune down only if our brain volume can't reach it, accepting more risk). Retire when `trials ≥ Nₘᵢₙ AND ĉ(s) ≤ −0.10`. **Acting on thin evidence is proven to harm more than it helps** (arxiv 2605.19576, ablation A4). |
| **Maturity gate** 🔴 | **0 tracked invocations is `no-data`, NOT a retire signal** (corrected 2026-05-30). The tracking hook is forward-only and warm-started 2026-05-30; a heavily-used skill (e.g. `clone-route` serving a 40-creator roster) reads as zero until usage accumulates. A skill may be quarantined for non-use ONLY when ALL hold: (a) the tracking window has matured (≥ a configured warm-up, target ~2–4 weeks), (b) it still has 0 invocations across **both** signal sources (hook + brain `<command-name>`), AND (c) it is not a known scheduled/farmer-driven skill (those never invoke the Skill tool — see §5). Until (a), `no-data` is purely informational. |
| **Bounded active-cap** | Hard cap on concurrently-active Forge-minted skills (start C ≈ 25–50). When a new install would exceed it, evict the lowest-contribution skill to quarantine. Prevents library drift via unbounded growth (the second load-bearing mechanism). |
| **Circuit breaker** | Halt all autonomous action + alert if `hurt` verdicts exceed 30% of the library, or the library is collapsing (mass-retirement run). Global brake above per-skill limits. |
| **Protected set** | Phase 1–2 autonomous revise/retire applies **only to Forge-minted skills**. Hand-authored skills get *proposals*, not auto-edits, until calibration is proven (opened in Phase 3). |
| **Snapshot-before-act** | Copy current skill → `forge/versions/<skill>/<ts>/` before any mutation. The report prints the exact revert command per action. |
| **Quarantine, never delete** | Retire = move to `forge/quarantine/` + uninstall from both profiles. Fully reversible. |
| **AgentShield gate** | Every auto-revise re-scans; a NEW high/critical finding auto-rolls-back the change and downgrades it to a proposal. |
| **Revise = regenerate, not patch** | When auto-revising, prefer regenerating the skill cleanly over patching it against the specific noisy correction (targeted negative-feedback patching underperformed clean regeneration — arxiv 2507.23158). |
| **Rate limit** | Max 3 autonomous actions per weekly run; excess become proposals. |
| **Cooldown** | A skill auto-touched this week is ineligible next week (anti-thrash). |
| **Kill switch** | `skill-forge-state.json → autonomous_refine_enabled: false` → score-and-report only, no changes, without disabling the Scheduled Task. |

> **Evidence-floor caveat for a personal system:** Library Drift's `Nₘᵢₙ=100`
> comes from a high-throughput coding benchmark. A personal agent may never log
> 100 invocations of a niche skill. Resolve in planning: either (a) lower the
> floor and widen the cooldown, accepting higher false-positive risk, or (b)
> keep the floor high so rarely-used skills simply never auto-retire (they just
> sit until a human reviews them) — the conservative default.

**Revert UX:** `python3 bin\skill-refiner.py --revert <skill> [<ts>]` restores the
latest (or a specific) snapshot and reinstalls in both profiles.

## 7. Data flow (weekly, Sunday)

Piggybacks the existing Sunday cadence (Weekly-Planner is 09:00).

1. **Skill-Miner** (09:30): `claude -p` fans out parallel readers over the week's
   brain transcripts → clusters procedures done manually **≥2 times** that no
   existing skill covers and aren't already queued (dedupe via
   `skill-forge-state.json`) → drafts `SKILL.md` + `rationale.md` + `evidence.md`
   into `forge/queue/<date>_<slug>/`.
2. **Skill-Refiner** (09:45): for each installed skill → pull invocations from
   brain → LLM-judgment classification → score → act (per §6) → append to
   `skill-forge.log` + `forge/report-latest.md`.
3. **forge-review**: `report-latest.md` (new proposals **+** autonomous actions
   taken) posts to Slack via `notify_slack.py` and feeds the weekly brief.
4. **Install path**: you approves a queued candidate → scaffold into `skills/` +
   both profiles (`parallel_subscriptions`) + AgentShield scan.

## 8. Phased build order

Each phase ships independently and proves a hypothesis before the next
(`calibrate_before_automate` as a build sequence; "no elaborate hallucinations of
progress").

| Phase | Builds | Proves | Autonomy |
|---|---|---|---|
| **0 — Signal** | `skill-refiner.py` in score-only mode + brain-query + LLM-judgment + weekly report | frequency + correction classification matches reality | none (read-only) |
| **1 — Miner** | `skill-miner.py` (parallel brain mining → `forge/queue/`) + Slack/brief wiring + install path | proposed candidates are good (low false-positive) | propose-only |
| **2 — Autonomous refine** | flip switch for **Forge-minted skills only** (snapshot + rate-limit + AgentShield rollback) | autonomy is safe & reversible on low-stakes skills | auto, scoped |
| **3 — Expand envelope** | open the protected set using proven data | graduated trust | auto, broad |

## 9. Constraints honored

- **subscription-first** — all `claude -p` calls run on your subscription; no API key.
- **local-first** — brain (SQLite) + filesystem + Windows Scheduled Tasks; no cloud.
- **parallel_subscriptions** — installs/quarantines apply to both profiles.
- **no_github_remote_for_agent_os** — reversibility is filesystem, not remote git.
- **calibrate_before_automate** — autonomy is phased and scoped, with kill switch.
- **AgentShield-Watch** — remains the mandatory security gate on every skill change.

## 10. Open questions for implementation (resolve in writing-plans)

- **Evidence floor for a low-throughput personal system** — adopt `Nₘᵢₙ=100`
  (conservative: rare skills never auto-retire, await human review) or lower it
  and accept more false positives? (See §6 caveat.) Leaning conservative.
- **Active-cap value** — start C at 25 or 50? Begins binding only once the Forge
  has minted that many skills, so it's not urgent for Phase 0–1.
- **Classifier precision target** — what `helped/hurt` precision must Phase 0
  demonstrate (measured against a hand-labeled sample of [NAME]'s own transcripts)
  before Phase 2 autonomy is unlocked? Proposed gate: ≥80% on the `hurt` class.
- Whether Miner parallel-readers use the Workflow tool or plain `claude -p`
  fan-out. (Note: the Workflow harness failed on this machine on 2026-05-30 with
  a StructuredOutput error — favor plain `claude -p` fan-out until that's fixed.)
- `forge/report-latest.md` format (reuse Weekly-Planner's brief template?).
- How install path reuses `session-reflect`'s scaffolding code (shared module vs. copy).

## Build log

**2026-05-30 — Phase 0 + 0.5 built.**
- Phase 0 package (`bin/skill_forge/`: config, skills_inventory, brain_query, judge,
  scoring, report) + `bin/skill-refiner.py` + 28 tests. Read-only pipeline runs.
- **Empirical finding (load-bearing):** the brain does NOT capture Skill-tool
  invocations queryably — the refiner found ~0 invocations for heavily-used custom
  skills. Detail folded into §5. This reversed the "no hook" decision.
- **Phase 0.5 — usage-logger hook (net-new, unplanned, forced by the finding):**
  `bin/skill-usage-logger.py` (PostToolUse hook, matcher `Skill`) + `usage_logger.py`
  (BOM-tolerant payload parse) + `usage_log.py` (frequency reader) + 10 more tests
  (38 total). Wired into BOTH profiles' `settings.json`. Captures `{ts, skill, args,
  session_id, cwd}` per invocation to `forge/skill-usage.jsonl`. **Forward-only** —
  activates on next session restart; signal accumulates from there.
- **Next:** (a) restart a session to activate the hook; (b) let invocations
  accumulate; (c) wire `usage_log.read_invocations` into `skill-refiner`'s
  `score_skill` (small change, pointless until data exists); (d) Task 10 live judged
  run + Task 11 precision eval once there's signal.

## 11. Research findings folded in (2026-05-30)

Direct web research (the deep-research workflow failed on a harness error;
searches + fetches run manually). Key sources and what each contributed:

| Source | Contribution |
|---|---|
| [Library Drift in Self-Evolving LLM Skill Libraries](https://arxiv.org/html/2605.19576) (2026) | The blueprint. Contribution score `ĉ(s)`, evidence floor `Nₘᵢₙ=100`, retirement `τ=0.10`, the **bounded active-cap** (the guardrail we were missing), `helped/hurt/neutral/inapplicable` attribution verdicts, circuit breakers (halt at >30% hurt / <50% engagement), and the load-bearing warning that *acting on insufficient evidence actively harms*. |
| [Implicit User Feedback in Human-LLM Dialogues](https://arxiv.org/abs/2507.23158) (2025) | Quantified the correction-signal noise (81%/42% accuracy easy/hard; 55–60% precision), the 5-way feedback taxonomy, and that clean regeneration can beat patching against noisy feedback. Justifies the evidence floor + long Phase 0. |
| [Voyager](https://arxiv.org/abs/2305.16291) (2023) | Canonical skill-library agent; removing self-verification → buggy skills accumulate. Validates AgentShield-as-gate. |
| [Position Bias in LLM-as-a-Judge](https://arxiv.org/abs/2406.07791) · [bias survey](https://llm-judge-bias.github.io/) | Self-preference / verbosity / position bias; no judge uniformly reliable. → structured rubric + different judge model than author. |
| [ADAS](https://www.llmwatch.com/p/automated-design-of-agentic-systems) · [Gödel Agent](https://arxiv.org/html/2410.04444v1) | Frontier of self-modifying meta-agents; confirms "self-created artifacts first" is the conservative correct entry point. |
