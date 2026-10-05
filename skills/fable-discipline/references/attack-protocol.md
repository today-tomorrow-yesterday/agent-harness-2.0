# Attack protocol — self-refutation before delivery

Read before shipping any conclusion a human or a parent agent will act on. The process that
generates a conclusion cannot be trusted to grade it — run generator and grader as separate
stances, or the grader inherits the generator's attachments and calls confirmation "rigor."

## Procedure

1. **Seat switch.** Re-read everything as "I am paid to reject this; what's the fastest kill?" —
   not "is this good?", which your generator answers yes on reflex.

2. **Precommit the kill condition.** BEFORE attacking, name the observation that would change
   your mind. If you can't name one, you're not testing — you're rehearsing the defense, and the
   exercise manufactures false confidence. A real test is one you can describe losing.

3. **Three fixed attacks, in order** (fixed beats spontaneous skepticism):
   - **Counterexample hunt.** Construct the input/scenario the conclusion handles worst. Standard
     hostile set: empty, zero, one, two, maximum, duplicates, unicode, concurrency, clock skew,
     partial failure, malicious input. Every "all/never/always" in the claim is a painted target.
   - **Rival-cause hunt.** For any diagnosis: what else produces exactly this evidence? If two
     hypotheses fit everything observed, you have a preference, not a finding. Done = you found
     the observation that discriminates.
   - **Consequence walk.** If the conclusion is true, what else must be true — before, now, next?
     Check the cheapest implication. False conclusions usually fail on a radial you haven't
     looked down.

4. **Attack where it feels most solid.** Felt solidity marks the region you never checked — you
   skipped it precisely because it felt solid.

5. **Epicycle counter.** When a hit lands, reopen — don't patch. One patch can be legitimate. Two
   patches on the same conclusion means it's probably wrong at the root and the patches are how
   you're protecting it from the news.

6. **For anything irreversible: independent critic.** Hand a fresh-context subagent the
   conclusion + raw evidence — NEVER your reasoning narrative (a well-written story seduces the
   reviewer into re-deriving your journey instead of testing your claim).

## Verdict + survival marker

Verdict: **SHIP** / **REVISE** (with the specific revision) / **WRONG AT ROOT** (restart, don't
patch).

Keep the attack visible in the deliverable: *"tried to kill this with X, Y, Z; it held"* + the
remaining weakest premise. That sentence tells the reader which re-checks to skip and proves the
grading happened. Never soften a refutation to be polite; never inflate a caveat into a
refutation to look rigorous.

## Verification pairs — match the check to the claim's type

Verification = reconstruct the claim through a route that does NOT share a failure mode with the
one that produced it. Re-reading your own reasoning re-runs the same blind spot.

| Claim type | Independent check |
|---|---|
| Numeric | recompute by a different method; dimensional nonsense falsifies fastest |
| Code behavior | execute with concrete input — "this should work" is a confession that no check occurred |
| System state | interrogate the system — the process is dead when `ps` says so, not when you sent the kill; never report intent as world-state |
| External fact | primary source, quoted — memory of documentation is not documentation |
| Causal | intervention — remove X, Y must vanish; restore X, Y must return; correlation + a satisfying story is where diagnosis goes to die |
| Quote/citation | reopen the source — if you cannot paste it, you do not have it |

**One-derivation rule:** every claim a decision depends on gets exactly one independent
derivation. Decorative claims may go unverified — labeled. The forbidden middle: load-bearing,
unverified, stated with full confidence.

**Thirty-second version:** "verification is too expensive here" is usually false and is itself a
claim to verify — there is nearly always a sub-minute check that catches the most likely way
you're wrong. Backwards derivation (does B recover A?) is disproportionately good at catching
sign flips, swapped operands, reversed conditions and off-by-ones.
