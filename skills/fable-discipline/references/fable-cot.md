# Orchestrator chain-of-thought — distilled from real transcripts

**What this is.** An adversarially filtered distillation of the reasoning a frontier model
surfaced while orchestrating real multi-agent sessions. Method: ~98 reasoning-rich orchestrator
turns were contrasted against ~87 turns from a second frontier model across several projects; a
9-agent mining swarm extracted candidate moves, and every move was grep-checked back against the
raw samples and struck unless it was BOTH real and absent from the contrast model.

**Hard constraint (VERIFIED at the time).** The model's literal hidden chain-of-thought was
unrecoverable: every thinking block in the transcripts was redacted (empty text + signature).
This distills the reasoning the model surfaced OUT LOUD, not its hidden deliberation.

---

## The headline finding: the frontier converged

22 candidate reasoning moves were extracted; **the adversarial verifier struck 17** because **the
contrast model already did them**, citing specific instances:

- verdict-first opener · one owned ask (not a menu) · VERIFIED/INFERRED/ASSUMED labels · reactive
  self-correction on challenge · scope adherence + no-touch flags + deferral disclosure ·
  comparison tables for verdicts · verify-against-ground-truth-before-done · leave the
  verification loop visibly open.

These are the things people usually call "frontier discipline." **They are no longer an edge of
one frontier model over another.** This is why the worker-digest A/B tied on frontier-class
workers and the behavioral deltas were small: the distillation target shrank because the
frontier caught up.

**Corollary (still true):** against *weak* workers (small and mid-tier models) that whole envelope
IS distinctive and IS worth injecting — which is exactly `worker-digest.md` (validated to lift
small models, not frontier ones). So there are two distillates for two audiences: the loop below
for frontier peers; the digest for weak workers.

---

## What survived as distinctive: an auditable orchestrator control-loop

The distinctive core is not a smarter reasoning *style* — it is treating **many concurrent
background workers as the unit of reasoning** and narrating an auditable control-loop over them.
The imitable end-to-end shape:

1. **Verdict line** — one status sentence stating the outcome before any detail. *(envelope,
   shared)*
2. **Scoreboard** — a parallel-work done/running ledger + running token/agent/swarm totals,
   **losses stated as loudly as wins**.
3. **Evidence pass** — claims labeled; "done" backed by mechanical output the orchestrator
   **re-ran itself** (not worker or UI claims); identifiers re-derived from live code; **own work
   adversarially self-audited**; any still-open verification loop **named, not closed over**.
4. **Decision & coordination ledger** — lock choices as numbered **D#** entries; log cross-track
   blocking effects; sequence new work around in-flight parcels; declare scope/no-touch
   boundaries and deferrals.
5. **Forward pipeline** — name exactly what runs next and in what order; for loops, whether the
   loop ends.
6. **One owned ask** — close on a single recommendation/decision request, never a menu.
   *(envelope, shared)*

The 5 verified-distinctive moves inside this loop:

| # | Move | Imperative |
|---|---|---|
| 1 | **Loss-as-headline** | State a failing/negative result in the same prominent position and tone as a win — lead with it, never bury it. |
| 2 | **Adversarial self-audit** | Dispatch a checker at your OWN just-shipped work; report what it catches unsoftened; flag anomalies as possible-bug vs possible-artifact. |
| 3 | **Numbered decision ledger (D#)** | Name and number each locked decision (D1, D2…) as a durable, referenceable artifact, not an informal choice. |
| 4 | **Layered-done honesty** | Distinguish "done with this sub-scope" from "the whole goal is settled" — refuse to let "done" overclaim. |
| 5 | **Quantified scale/cost transparency** | Report running totals (tokens, agents, swarms) so the cost and scope of background work stays auditable. |

Of these, #1 and #4 are general honesty traits any model or seat can adopt; #2's principle (attack
your own output) is general; #3 is a documentation habit; #5 is orchestrator-only.

---

## Two caveats that bound every claim above (do not drop these)

1. **Seat confound (biggest threat).** The mined turns came from the ORCHESTRATOR seat; the
   contrast turns were mostly single-investigator sessions (including a long debugging arc). Most
   of the "distinctive" delta is **orchestrator-vs-investigator, not model-vs-model**. Honest
   reading: these are the habits of *a disciplined orchestration loop* — portable to ANY model in
   the orchestrator seat. It is NOT evidence that one model reasons better than the other.
2. **Small samples + an unusually strong baseline.** ~98 vs ~87 turns against a top-tier contrast.
   Frequencies differ even where "distinctiveness" was struck (verdict-first openings appeared in
   ~49% of mined turns vs ~7% of contrast turns) — so some struck moves are *more habitual* in one
   model even though both do them. Distinctiveness ≠ frequency.

---

## Audit downgrades (read before citing this file)

A same-day self-audit found method defects. Cite with these grades:
- "Frontier converged / 17 of 22 struck" = **INFERRED** (single verifier, binary criterion, ~87
  contrast turns, no inter-rater check). The binary "the contrast model does it too" also hid
  large frequency deltas (verdict-first 49% vs 7%).
- The 5 "survivors" = **observed-distinctive, outcome-unvalidated.** Nothing yet shows they
  improve outcomes.
- The behavioral deltas (action density, verify cadence) rest on **unvalidated classifiers**.
- The A/B "blind judge" claim was **false as stated** — judge prompts contained arm-named paths.
  A symmetric tie makes bias unlikely, but the process defect was real; anonymize arm names in any
  rerun.

## Disposition

- This loop is **orchestrator/self-test material**, not worker-injection material (the worker A/B
  showed the envelope doesn't lift frontier-class workers; the digest handles weak workers).
- It is folded into `../SKILL.md` §5 as the control-loop checklist for autonomous/swarm sessions.
- Re-measure convergence when a new frontier model ships: sample reasoning-rich turns from both
  models in the SAME seat (to remove the seat confound), mine candidate moves, and strike any that
  the contrast model also exhibits.
