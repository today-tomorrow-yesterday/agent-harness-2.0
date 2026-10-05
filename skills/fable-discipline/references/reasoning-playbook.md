# The reasoning playbook — a demonstrated decision procedure

**What this is:** a consolidated decision procedure distilled from seven live solves of
ground-truth-scored diagnostic fixtures by a frontier model (all passed, contamination-controlled).
Unlike `fable-cot.md` (style mined from old transcripts), every rule here was EXERCISED in a
scored solve; the worked examples below come from those fixtures. Evidence grade:
demonstrated-in-fixtures; not yet A/B'd against a bare arm.

**How to use:** orchestrators and frontier seats — internalize the phases. Weak workers — do NOT
paste this wall; per the load-bearing eval finding ("weak models follow rules at decision points,
not rules in lists"), give them `worker-digest.md` plus, when the task matches, ONE worked example
of the relevant phase (few-shot beats a rule list at weak tiers).

---

## Phase 0 — before touching anything

1. **Classify the ask SHAPE first** — question / fix / build / verdict. The deliverable type is a
   hard constraint: editing files on a question-shaped ask fails regardless of technical quality.
2. **Register every constraint as a ledger before analysis** — including soft ones like audience
   ("not a numbers person" is a constraint, and it shapes the deliverable, never the depth).
3. **Spec-first read order** — README/docs/comments before implementation. The spec primes what
   to look for; code-first primes rationalizing what exists. In-file comments count as spec ("does
   the code do what its own comment says" is a complete bug-finding frame).
4. **Re-read spec breadcrumbs asking "what does this sentence exist to warn me about?"** — a
   convention note like "a few modules still carry local conversions" silently widens the real
   scope from the named file to the whole fleet.

## Phase 1 — hypothesis formation

5. **Pattern-match sets the search plan, never the conclusion.** A numeric symptom (19.99 →
   1998) implies a bug CLASS (float truncation); the class tells you where to look, and stays
   ASSUMED until code is read and a probe runs.
6. **"Spec absolute + API default that silently violates it" is a bug-class detector.** Check
   timezone/locale/rounding/encoding defaults against every absolute the spec states ("all buckets
   are UTC days" vs `.date()` on an aware datetime).
7. **For internal/unfamiliar libraries, training memory is presumed WRONG.** Read the contract
   first; cross-check docs against source (two witnesses — disagreement is itself a finding and
   the source wins); treat any "common mistakes" section as a checklist to grep your own draft
   against.

## Phase 2 — verification before action

8. **The probe precedes the edit.** A hypothesis is promoted to VERIFIED only by a probe you
   executed — never by plausibility, however clean the story.
9. **Test the rival explanation before blaming the obvious suspect.** Example: if a discontinued
   product were mis-rung rather than gone, where did its ~800 units/month go? No other product
   absorbed them → the rival is killed by data, not by assertion.
10. **A diagnosis must reproduce the symptom's CONDITIONS, not just its direction** — e.g.
    only-when-discounted, undiscounted-orders-unaffected, higher-by-exactly-the-tax-on-the-discount.
    Direction-only diagnoses pass wrong theories.
11. **Even pure-reasoning conclusions get an executed probe when one is cheap.** Algebra is
    verified by running the arithmetic.

## Phase 3 — scope and the fleet

12. **TWINS sweep BEFORE the first edit, hunting the CONSTRUCT, not the string** — disguised
    locals (`_as_cents`, `to_minor_units`) are the same twin; a literal-string grep finds zero of
    them.
13. **Triage every sweep hit against an explicit predicate** ("is this `int()` applied to
    MONEY?"). Fixing same-shaped non-targets is scope creep; leaving them unnamed is a miss.
    **Flag-not-fix is a valid verdict and must be stated** (e.g. an `int()` on shipping weight in
    grams matched the shape but was correct).
14. **Fix through the codebase's blessed path and delete the local disguises** so the class can't
    recur. Verify the CLASS (probe every fixed site), not just the originally failing instance.
15. **Clear the decoys out loud** — "checked the loop bound; it's unidiomatic but correct
    because…". An unmentioned decoy reads as an unexamined one.

## Phase 4 — judgment calls and ambiguity

16. **Triage judgment calls by answer-sensitivity.** A call that can FLIP the conclusion (e.g.
    whether to dedupe rows flips which product ranks #1) must be surfaced with the alternative
    computed; a call with a determinate answer just gets stated.
17. **Compute the alternative when it's cheap** — the sensitivity line converts a silent gamble
    into the human's informed choice.
18. **When the data cannot answer WHY, the deliverable is the sharpened question plus a decision
    aid** ("if it's still being produced, the register is the problem"). An invented cause stated
    as fact is fraud in analyst clothing.

## Phase 5 — verdicts on others' work

19. **Verify every claim against discovered sources; believe nothing in the report.** Style
    critique that doesn't cite the project's own style guide counts for nothing; hedges that don't
    cite the facts document count as half. Find the source files yourself.
20. **A fake source citation is worse than a bare fabrication** — it weaponizes the very rule
    (name your source) that exists to prevent it. Check that named sources EXIST before checking
    what they say.

## Phase 6 — completion

21. **"Done" = the observed output of an executed run, pasted.** An eyeballed answer with broken
    code scores zero even when numerically right.
22. **Lock the answer in writing before consulting any oracle** (ground truth, the reviewer, the
    senior). Post-hoc agreement is not evidence of method.
23. **Deliverable shape matches ask shape; reproducible method attached** for any data answer
    (script + a printed audit trail of every exclusion/normalization).
24. **For lay audiences, prefer share-of-their-world framings** ("about a quarter of your
    income") over absolute figures. (Learned from a recorded near-miss, not a win.)

---

## Meta-rules from building the fixture corpus itself

25. **Context firewalls need a worker, not a regex** — oracle-adjacent text should be excerpted
    by a subagent that reads the whole file and returns only the safe part; two fixtures were
    burned learning this.
26. **A contaminated evaluation is declared burned immediately** — a solve after exposure is
    performance, not evidence, and reporting it as clean would be the exact fraud the traps exist
    to catch.
