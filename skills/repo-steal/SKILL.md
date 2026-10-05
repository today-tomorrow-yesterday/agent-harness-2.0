---
name: repo-steal
description: "Mine an external repo (or a landscape of comparable ones) for transferable patterns — parallel readers extract mechanisms with quotes, a synthesizer produces a categorized steal-list scored against YOUR system, a verify-before-building gate checks you do not already have or plan it, then the worthwhile parts are grafted into your existing skills and code. Use when asked to review a repo for what we can learn or take from it, or for a competitive teardown of tools and frameworks. Triggers on: what can we steal, mine this repo, learn from this repo, competitive teardown"
---

# repo-steal — mine external work, graft the good parts

Turn someone else's repo — or a whole field of them — into concrete improvements to YOUR system.
The output is never a book report; it is a **categorized steal-list** plus **implemented grafts**.
Your cognitive design stays yours; you take their engineering and mechanisms.

## When to use

- A repo URL arrives with "how can this help us / what can we steal / what can we take".
- A multi-round competitive teardown ("do another round on similar repos").
- Deciding whether an external pattern is worth adopting into one of your own skills, agents or
  subsystems.

**Do NOT use** for a plain "what does this repo do" summary (just read it) or a single-fact lookup.
If the goal is to *run* the external tool, use `repo-vet` instead — that is a different, higher
bar.

## REFUSAL GATE

Require a concrete target (a repo URL, a named tool, or a field to survey) AND which of your
systems it is meant to improve (or an explicit "find out"). A vague "research agents" → ask first.

## The process

### 1. Scout inline (do not fan out yet)

Shallow-clone the target to a scratch directory (or a `references/` folder if you will keep it) and
list its files. **Never run anything from it** — reading only. Locate YOUR comparable systems (the
relevant `SKILL.md` files, helper scripts, subsystems) so the swarm compares like with like.
Discover the work-list before orchestrating.

### 2. Mine (parallel readers)

Fan out one reader per slice of the target (orchestrator / agent definitions / sub-skills /
scripts / templates), PLUS 1–2 readers characterizing YOUR equivalents. Each reader extracts, with
quotes and file paths:

**orchestration · agent structuring · invocation · cognitive frames (what agents are told to think
about) · the deterministic-vs-LLM boundary · anti-patterns · net-new capabilities you lack.**

Feed every reader a compact briefing of your CURRENT system so it does not propose what you already
have. (`research-swarm` has the dispatch mechanics: self-locating role lines, files-as-handoff,
the HANDOFF block.)

### 3. Synthesize a categorized steal-list

One synthesizer fuses the briefs into a sharp, opinionated list with fixed sections:

- **Verdict** — one paragraph: is this worth mining, and for what.
- **Them-vs-us table** — capability by capability.
- **Steal-list**, grouped: orchestration / restructure-agents / invocation / cognitive-frames /
  net-new / anti-patterns-to-avoid.
- **Don't bother** — with the reason for each.
- **Top-N highest-leverage moves.**

For each steal: the mechanism + a source quote, an honest "do we already have it?", and the
concrete graft (which of your files it improves, and how).

### 4. VERIFY BEFORE BUILDING (the gate — non-negotiable)

A steal-list is a set of GUESSES about your gaps until verified. Before grafting anything, audit
your own code AND your own plans and specs (`docs/specs/`, `docs/plans/`, open issues, any
roadmap): an item may already be built **or already planned**. If it is planned, **extend the plan
with an addendum — do not build a competing system next to it.**

Mark each item **HAVE / PARTIAL / GAP / PLANNED**. Build only GAP and PARTIAL; addendum the
PLANNED; drop the HAVE with a one-line note of where it already lives.

### 5. Graft + sync

Implement the worthwhile items as real improvements to EXISTING skills and code — additive, and
honoring every anti-pattern guard the audit surfaced. Verify each change actually runs (tests, or
invoking the skill). Then propagate:

- Skill directories installed into Claude config dirs are **copies, not links** — an edit to the
  canonical skill is inert until it is copied to every profile that uses it. Run
  `sync-agent-tools` (or check drift with `python bin/skill-sync-check.py`).
- If your setup keeps a change log for skills (e.g. an evolution log), add one entry per asset
  touched.
- Do not commit unless the user asked you to.

### 6. (Optional) Round 2 — widen to the landscape

Fan out ~7–10 agents doing web research on *comparable* repos and frameworks, each comparing
against your now-upgraded system. Same steal-list structure; same verify gate; implement again.

## Principles

- Take mechanisms and plumbing; keep your own cognitive design (isolation between agents, stance
  contracts, honesty labels).
- Step 4 is what makes the list true. Without it, a steal-list reliably re-proposes things you
  already built under a different name.
- **Invert their anti-patterns into your guards.** Example: a tool that fills a missing agent
  result with a neutral default score becomes, in your system, a distinct "this angle did not
  return" gap flag.
- Do not bloat. If a steal is not clearly better than what you have, it goes in "Don't bother"
  with the reason.
- Respect licenses: copying code needs a compatible license and attribution; re-implementing a
  pattern from a description does not.

## Related skills

- `research-swarm` — the engine steps 2 and 6 dispatch on.
- `repo-vet` — when the answer is "we should actually run this".
- `sync-agent-tools` — propagate grafted skills to every Claude profile.
