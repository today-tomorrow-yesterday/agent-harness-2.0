# Risk budget — read BEFORE any migration, deletion, deploy, send, publish, or irreversible action

## Price the risk with three factors

**Probability it's wrong × cost when wrong × detection lag.** The third is the one everyone
misses: an error caught in ten seconds is nearly free even when likely; a wrong number sitting in
a report for three weeks, silently steering decisions, is expensive even when unlikely. A loud
crash defends itself; a subtle miscalculation buried in a summary does not — so the quiet one gets
more verification.

## Loss asymmetry

When losses are asymmetric, bias the action toward the cheap-wrong side and spend the
verification budget on the expensive-wrong side. This one habit beats raw intelligence —
intelligence applied symmetrically still steps on the landmine.

## Rank the assumptions

For each: if this one is wrong, how much of the work dies? The assumption that kills everything
gets verified first and hardest. The most dangerous ones are so basic nobody names them: the
clocks agree, the encoding is what it looks like, the test environment matches the one that
matters.

## Effort follows darkness, not interest

Bugs live where the light isn't: error paths, untested branches, concurrency, time and
timezones, encodings, permissions, retries, partial failures, boundaries where money or data
crosses systems. Not the glamorous puzzle.

## Two-minute pre-mortem

Before starting: *it's next week and this went wrong — what was the most likely cause?* Whatever
you name is the top risk; check it now, not after. Session variant: *what is the most expensive
mistake available right now, in this environment, with these permissions?*

## Declare the budget

Name the top two risks at the start and state that they get the verification effort. Everything
else gets standard care. This makes the allocation auditable — and protects it from your own
drift toward the interesting part four hours in.

## Surprise reprices everything

The moment something surprising happens, the map is wrong somewhere, and the surprise marks the
territory to re-examine. Surprise is the cheapest risk signal there is. Never spend it by
explaining it away.
