---
name: research-swarm
description: "Answer a broad, multi-angle research question fast and honestly — decompose it into non-overlapping sub-questions, dispatch parallel background research agents, dedupe their sources with a deterministic ledger, verify load-bearing claims in isolation, then synthesize ONE source-cited, confidence-flagged report with its coverage gaps named. Use when a decision needs evidence from several distinct angles, not a single search. Triggers on: deep research, research swarm, multi-agent research, look into thoroughly"
---

# research-swarm — parallel deep research + synthesis

Turn one big question into a fleet of parallel researchers, then fuse their findings into a single
honest report. The pattern has been run repeatedly on market, tooling and competitor questions; the
guards below each exist because the unguarded version failed in a specific way.

## When to use

- A strategic or research question with several distinct angles ("how should we build X", "what is
  the best Y", "who are the players in Z").
- The user asks for "deep research", "multi-agent", "a swarm", "look into this thoroughly".
- A decision needs evidence + sources + honest confidence, not a single opinion.

**Do NOT use** for a single-fact lookup, something one search answers, or a trivial question.

## REFUSAL GATE (run first)

Do not burn 6–8 background agents on a vague prompt. Require, or ask for: a **specific question +
what a good answer looks like** (the decision it feeds, and the scope / region / budget if
relevant). Underspecified ("research X") → ask 2–3 narrowing questions first, then swarm.

## MODE: quick · standard · verify

- **quick** — a SINGLE research agent, no fan-out, for a question with one real angle. The named
  cheap path; reach for it before the swarm.
- **standard** — the full parallel swarm below (default for genuinely multi-angle questions).
- **verify** — standard + the mandatory step 3c, for decisions that hinge on specific facts.

## The process

### 0. Shared context build (dedupe the I/O)

If every agent will hit the same core source (one company, one repo, one doc set), the
orchestrator fetches it **once** up front and injects the shared briefing into each sub-agent's
prompt, so they spend their budget on their *own* angle instead of re-fetching the same page.
Pure I/O dedup — it costs nothing cognitively. Skip when the sub-questions hit disjoint sources.

### 1. Decompose

Break the question into **4–8 NON-OVERLAPPING sub-questions**, each a distinct angle (for a
product: pricing, delivery/stack, acquisition, economics/legal). Each becomes one agent.
Non-overlap is what makes parallel worth it — overlapping agents return the same five links.

### 2. Dispatch (parallel, background)

Launch one subagent per sub-question (a general-purpose agent with web search + fetch, run in the
background). Each prompt MUST demand:

- **Self-locating role line:** "You are sub-question N of M; the others cover [X, Y, Z]; stay in
  your lane, do not duplicate theirs."
- **Real sources:** web search + fetch, not model memory.
- **Cite sources + flag confidence per claim** (HIGH/MED/LOW); separate hype from evidence;
  triangulate — no single source is gospel.
- **Net-new only:** name what we already have and tell it to exclude that.
- **Files as handoff:** write full findings to `docs/research/_swarm/<topic>/agent-<k>.md` and
  return only a **digest** — top claims + per-claim confidence + a list of `{url, claim}` citations +
  the file path + any gap flag. The synthesizer reads digests and opens a full file only to
  adjudicate a conflict. Passing 6–8 full reports through one context both hits the token ceiling
  and distorts the findings like a game of telephone.
- **The worker contract:** prepend `skills/fable-discipline/references/worker-digest.md` verbatim
  (read it at dispatch time — point at it, never inline a fork of it) and tell each agent "your
  digest will be checked against your cited sources."
- **The HANDOFF block** (below) as the end of its final message — the agent's last message IS the
  result.

**Optional critic layer:** for a strategy decision, also dispatch 1–3 critic agents to attack a
concrete STRAWMAN answer (each with a different lens, e.g. cost, risk, the user's perspective).
Critics attacking something concrete produce sharper objections than critics asked to "review".

Fire-and-forget: tell the user it is running, end the turn; you are notified as each agent lands.

#### Required HANDOFF block (every worker)

```
TLDR: <=1 line, the answer
FINDINGS: <bullets>
EVIDENCE: <source refs / file:line — not bare claims>
WHAT_I_DID_NOT_CHECK: <the blind spots — REQUIRED, never empty on a non-trivial task>
OPEN_QUESTIONS: <what a next wave should chase>
CONFIDENCE: high|med|low + why
```

Read the TLDRs first, bodies on demand. An empty `WHAT_I_DID_NOT_CHECK` on a complex sub-question
is itself a red flag. A worker that returns without the block is redispatched once, then dropped —
never silently accepted. That is how "deep" decays into "expensive shallow".

### 3. Hold for quorum (one stall must not sink the run)

Give a brief status per arrival. Synthesize when the **quorum** lands (e.g. ≥80% of agents, or all
but one stalled past a reasonable wait) — not strictly all, so one hung agent cannot block the
report. A missing angle is **named explicitly as a gap** ("the pricing angle did not return") —
never silently dropped, never papered over with neutral filler.

### 3a. Source ledger (deterministic, before synthesis)

Collect every `{url, claim, agent}` from the digests and run the ledger shipped in this skill:

```bash
python <skill-dir>/source-ledger.py --input citations.json     # or pipe JSON on stdin
python <skill-dir>/source-ledger.py --demo                      # see the output shape
```

Input: `{"citations": [{"url": "...", "agent": "a1", "claim": "..."}, ...]}`. It canonicalizes URLs
(strips tracking params, `www.`, fragments, trailing slashes), **dedupes across agents**, and tags
each domain with a coarse reliability tier (primary / reputable / tertiary / unknown — edit
`TIER_RULES` for your field). Three agents citing one syndicated article through three URLs
collapse to *one* source, flagged in `multi_agent_sources` as an echo — one confirmation, not
three. **Independence = `distinct_sources`, never the raw citation count.** Zero model calls.

A tier is a prior on the SOURCE, never a verification of the CLAIM — that is step 3c's job.

### 3b. Reflect → gap refill (bounded, optional)

A cheap supervisor pass reads the gap flags, every worker's `WHAT_I_DID_NOT_CHECK` /
`OPEN_QUESTIONS`, and the ledger's thin or unknown-tier angles, and emits **0–N follow-up
sub-questions**, capped at **one extra wave** (two waves total). Skip it when the first wave is
well sourced. Never let this loop trigger itself without that external signal.

### 3c. Spot-verify load-bearing claims (mandatory in `verify` mode, recommended always)

- **Per agent:** re-fetch ONE load-bearing URL from each digest and check the quoted claim actually
  appears there. A fabricated or unsupported load-bearing claim disqualifies that agent's digest —
  redispatch or drop it, never average it in. Agents armed with a good worker contract have still
  been measured fabricating whole results; verification is orchestrator-side, always.
- **Factored verification (verify mode):** extract the top-N load-bearing data claims, write one
  verification question for each, and answer it in a **fresh isolated agent that never sees the
  draft** (a verifier that sees the draft repeats its hallucinations — the factored
  Chain-of-Verification discipline). It re-fetches the cited URLs and returns SUPPORTED / PARTIAL /
  UNSUPPORTED / DEAD-LINK. **Mechanically downgrade** any data claim that is not SUPPORTED to an
  assumption. Published audits of deep-research tools have found a few percent up to roughly an
  eighth of cited URLs fabricated or dead; this turns honesty labels from self-declarations into
  checked facts.

### 4. Synthesize

Fuse into ONE report:

- Lead with what **converges** across agents (independent agreement is the strongest signal — and
  "independent" is what the ledger measured, not what the agents claimed).
- Dedupe; rank by evidence; **carry the confidence flags and sources through** — name the source
  of truth for each key claim and how reliable it is.
- Keep the honest caveats: what is hype, what is unverified.
- **Data-density meter**, separate from the conclusions: how many sub-questions came back with
  HIGH-confidence sourced evidence vs thin or missing ("5/6 angles well sourced; pricing thin").
- **Coverage gaps section:** every worker's `WHAT_I_DID_NOT_CHECK` + `OPEN_QUESTIONS`, deduped.
  Report "seeded N sub-questions; workers surfaced M new ones; closed K". If M = 0 on a complex
  topic, flag the run as likely shallow — a plan that never outgrew its seed was under-explored.
- Write it to `docs/research/<topic>.md` so it persists; give the user a short summary that leads
  with the answer.
- End with a recommendation + the ONE genuine decision left for the user (a preference or value
  call — not a data question you could have answered yourself).

## Governing rule: external-signal-only self-critique

Intrinsic self-correction — a model grading its own output with no new information — measurably
degrades results (Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet"). So no
reflect, verify or refill stage here may be the sole judge of its own correctness. Every loop is
triggered by an external signal: a gap flag, a ledger thin spot, a verification mismatch.

## Notes

- Concurrency: ~6–8 background agents at once is a sensible ceiling for one session.
- Token care: agents return distilled digests; big page snapshots stay inside the agents.
- Optional telemetry: append one JSON line per dispatch to `forge/dispatch-ledger.jsonl`
  (`{ts, topic, agent, sub_question, verified: true|false}`) if you want to measure which agents'
  digests survive verification over time.
- Lineage: the shared-context build, quorum, data-density meter and quick escape hatch come from
  the sequential-discovery → parallel-map → reduce pattern in open-source sales-research agent
  kits; files-as-handoff from Anthropic's published multi-agent research system; the source ledger
  from STORM-style research pipelines; bounded reflect → refill from LangChain's
  open_deep_research; factored verification from Chain-of-Verification.

## Related skills

- `fable-discipline` — the claim-labelling contract and the worker digest injected in step 2.
- `repo-steal` — uses this engine to mine a field of comparable repos.
