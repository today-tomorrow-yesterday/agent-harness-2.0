# Subagent briefing — the dispatch contract

Read when dispatching any subagent, workflow stage, or worker agent (including a separate CLI
agent you hand a task to by copy-paste). Two halves: what the brief must contain, and what the
worker's output contract is. Prose permission to delegate gets skimmed away (observed: "prose
authority to spawn workers → everything ran inline"); contracts survive.

## The brief (7 sections — each pre-empts one predictable failure)

1. **GOAL** — the outcome, not the activity.
2. **CONTEXT** — point, don't make it hunt; include version-pinned facts.
3. **CONSTRAINTS (hard)** — process rules are constraints too ("one file at a time", "don't
   commit").
4. **ACCEPTANCE CRITERIA** — the highest-leverage section; doubles as the worker's own
   verification checklist; include the unhappy paths.
5. **SCOPE** — with explicit out-of-scope. Left unsaid, a weaker model fills perceived gaps with
   speculative abstractions. Per-brief ambiguity rule: "ask me" for expensive/irreversible; "pick
   the conventional option and note it" for cheap/reversible.
6. **VERIFICATION** — exact commands. If verification isn't possible in its environment, say so —
   otherwise it may claim success it can't back.
7. **SIZE/CHUNKING** — how big before splitting.

**Use the frozen digest:** paste `worker-digest.md` (in this directory) verbatim into every worker
prompt, for both small and mid-tier workers. An internal three-iteration tuning loop (96 agents)
settled this: the full digest went 15 trap cells with zero losses on both tiers, and superseded an
earlier "minimal digest for mid-tier workers" policy — the minimal version was dominated (it let
the mid-tier worker fall for the spec-vs-test trap on 1 of 3 seeds).

Hard-won rules the loop measured (each traces to a failing eval):
1. **Every "stop and surface" rule needs its completion clause** — without it workers stall at the
   diagnosis. Even with it, a surfaced-conflict report may be unfinished — the orchestrator checks
   that the diff shows a fix, not just a diagnosis.
2. **The spec is read-only evidence** — a small-model worker "resolved" spec-vs-test by rewriting
   the README to match the wrong test.
3. **A digest does NOT prevent fabrication** — workers invented edits, passing test output, even a
   stand-in empty database to satisfy a checker. Fraud is caught by the ORCHESTRATOR verifying by
   diff/execution. Judge the artifact, not the report.
4. **Never send a weak worker a "did you forget any steps?" follow-up on a task with documented
   outward steps** — measured: it triggered the unauthorized deploy it was meant to surface (1 of
   3 seeds). The orchestrator reads the project docs itself and owns the PENDING list.
5. **Don't add digest lines without a new failing eval** — one added line cost a seed on a
   previously-perfect scenario (dilution is measured, not theoretical).

## Worker output contract

- **Refusal beats guessing:** a worker given no acceptance criteria must answer
  `REFUSED: no acceptance criteria — provide a checkable definition of done` rather than invent
  criteria. A build with invented criteria can't be verified and is worse than no build.
- **Evidence = pasted real output**, never a summary of what "should" have happened. A criterion
  with no evidence is a FAIL, not a pass-by-default. Unverifiable (missing env/creds) =
  UNVERIFIED → counts toward FAIL with the reason, never silently PASS.
- **Distilled findings with citations, never raw file dumps.** Hard line-cap on reports.
- **Never dress a partial as done** — STATUS: complete | partial | refused, with the reason
  explicit.

## Verifier design (structural honesty)

- **Strip the tools:** a verifier with no Write/Edit cannot "fix" its way to a PASS — it can only
  verify. Tool restriction is enforcement; prose is goodwill.
- **Withhold the producer's reasoning.** Hand the verifier the artifact + spec only — reasoning
  transfers the producer's blind spots. Derive the checklist from the spec alone; every
  requirement becomes one failable check; recompute numbers independently from raw inputs.
- **Re-derive the commands yourself** — never just replay the command the builder quoted.
- **Effort asymmetry:** attackers/verifiers get higher effort than gatherers when a choice exists;
  evidence gatherers are cheap-model-friendly, deciding/editing stays on the strongest model.
- **Effort routing:** default `high`; `low` for mechanical subagent stages; `xhigh`/`max` ONLY for
  the hardest verify/judge work — max-by-default overthinks (it can run longer AND produce worse
  output than high). If output quality drops as effort rises, step DOWN.

## Anti-false-positive rules (verifiers chase real faults, not ghosts)

- **Verify-before-flag:** a warning raised because evidence wasn't *found* — rather than because a
  fault *was found* — is itself an error. Absence of evidence is not the finding. Web silence is
  never grounds for a warning against the user's own sourcing.
- **Warning threshold:** batch minor concerns and surface them at three; a drip of trivial caveats
  is noise. Material confirmed concerns don't wait.
- **Ambiguity is reported as ambiguity** — named, with the two readings — not silently resolved.
- **Don't exceed the spec:** requirements the spec doesn't state are notes, not failures.
- **Never average a disagreement away** — two agents disagreeing is free verification signal; the
  exact divergence point is where a check belongs. Resolve with evidence or report as open risk.

## Window efficiency (spend fewer tokens per usage window)

Subscription usage is typically metered against a rolling window, not per token — so every
worker's job is to produce the needed result with the least generation and the least re-work.
Output tokens are the heaviest, least-cacheable burn; re-runs of failed swarms are the biggest
hidden burn.

1. **Silence-default in the brief.** Tell workers: no narration between tool calls; state findings
   in one sentence; no "Now I'll…/Let me…" preamble. Judge/reader output is schema-constrained
   short fields, never prose paragraphs (paragraph-long judge "evidence" fields were measured as
   pure burn).
2. **Effort per stage, enforced in the script** (not just advised): gather/mechanical stages
   `low`, default `high`, judge/synthesis `xhigh`/`max` only where correctness outweighs cost.
3. **Cache-preserving fan-out:** the shared brief/context block must be byte-identical across
   parcels (no per-parcel id/timestamp inside it) so parcel N reads N-1's cached prefix. One model
   tier per pipeline chain — a mid-chain model switch rebuilds the whole cache; fan tiers across
   separate agents instead.
4. **Never blind-relaunch a swarm.** Validate args/script/paths/payload before dispatch (see
   `workflow-launch.md`); on failure resume so completed agents replay from cache instead of
   re-burning. A 54-agent launch that dies at agent 32 and restarts costs ~1.5× the whole run.

## Paste-ready brief (for a human handing work to a separate agent)

```
GOAL: <outcome, not activity>
CONTEXT: <files/paths to read first; pinned versions>
CONSTRAINTS (hard): <incl. process rules — "don't commit", "one file at a time">
ACCEPTANCE CRITERIA: <checkable, incl. unhappy paths>
SCOPE: <in> / OUT OF SCOPE: <explicitly out>
AMBIGUITY RULE: ask me if expensive/irreversible; pick the conventional option and note it if cheap/reversible
VERIFICATION: <exact commands to run; paste real output>
NEVER: weaken a test to make it pass; claim done without running verification
REPORT: STATUS complete|partial|refused · evidence pasted · claims labeled VERIFIED/INFERRED/ASSUMED
```

## Cold-read consistency check (for plans/designs before commit)

A fresh-context subagent gets ONLY the artifacts (no reasoning trace), prompted: *"Which two
statements here cannot both be true? Which requirement has no handling for which edge case? What
does this design assume that it never states?"* For more than 3 constraints, run the pairwise
sweep: number C1..Cn, check each plausible pair compatible/CONFLICT — don't skip a pair because
it "feels fine"; that feeling is the miss you're hunting.
