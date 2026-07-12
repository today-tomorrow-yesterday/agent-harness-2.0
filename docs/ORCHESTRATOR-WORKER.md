# Orchestrator / Worker across two subscriptions

If you hold both a Claude subscription and a ChatGPT (Codex) subscription, you can
run them as **two seats of one system**: Claude Code as the *orchestrator* (holds
the plan, decomposes work, verifies results), Codex as the *worker* (executes
bounded tasks headlessly via `codex exec`). Both seats read this repo's `memory/`
as their shared source of truth, so a standing rule written once is visible to both.

Field-tested pattern — everything below came from live runs, not theory.

## The role split

- **Orchestrator (Claude Code):** top-level plan, task decomposition, choosing what
  to delegate, coordinating, synthesizing results, and — always — verification.
- **Worker (Codex `exec`):** delegated research, coding, analysis, artifact
  creation within an explicit scope. The worker may flag risks or a better route;
  worker does not mean passive. Material strategic forks go back to the
  orchestrator (or to you).
- **You:** own direction and irreversible decisions.

## When to delegate

Delegate when **the work is much bigger than its spec AND the output is cheap to
verify** (artifacts on disk, self-tests). Keep tasks that need the orchestrator's
loaded conversation context, or where writing the spec ≈ doing the work.

The worker seat is an **optimization, never a dependency** — every delegated task
keeps a fallback assignee (the orchestrator or a subagent). If the worker seat is
down or rate-limited, the task loses minutes, not the plan.

## The work-order format

Write briefs as files (keep an audit trail, e.g. `tmp/worker-briefs/`), with five
sections — vagueness in any of them is where delegation fails:

1. **Objective** — one sentence, what "done" produces.
2. **Context you need** — exact paths, invocation patterns to copy, runtimes to
   expect, environmental quirks. Point at reference files rather than describing.
3. **Steps** — numbered; step 1 is ALWAYS "create the work dir and start a log
   file immediately, append after every step."
4. **Constraints** — the write-surface fence (one directory), what must not be
   touched, retry limits ("one sensible retry, then stop and report"), no git.
5. **Done means** — the artifacts that must exist + the report file.

## Hard-won field notes

- **Write files early and incrementally.** A killed/crashed run must leave
  salvageable evidence. This single rule has rescued entire work orders.
- **A crashed dispatcher ≠ a failed task.** The `codex` CLI can die (observed:
  Rust OOM ~40s in) while a long-running child process it launched survives and
  completes. Before declaring a dispatch failed, check the work product on disk.
- **On-disk artifacts are the source of truth**, not the dispatcher's exit code
  or streamed output.
- **Verification never delegates.** Check worker handoffs like you'd check any
  generated output. The orchestrator renders/runs/diffs the result itself.
- **A discrepancy flag on inputs should block, not improvise.** If the brief says
  "use file X" and X doesn't exist, the right worker behavior is stop-and-report;
  say so explicitly in the constraints if the input matters.
- **Windows `codex exec` stability** (as of mid-2026): bare `codex exec` works;
  `--full-auto` has hung indefinitely; `--sandbox danger-full-access` has crashed
  mid-run (child survived). Treat the CLI as fragile: fence the write surface,
  demand incremental logs, trust the disk.
- **Give real tasks 15+ minute leashes** — session startup alone can eat minutes.

## Effort routing (don't run everything at max tier)

Cranking model tier/effort past what a task needs produces *worse* output for
*more* budget. On the Claude seat, route per-subagent via the Agent tool's
`model`/`effort` params (cheap scout → workhorse → frontier for hard synthesis).
On the Codex seat there's no per-task override — the routing decision is
delegation granularity itself: whether to hand the whole task over at all.
Reframe "cost" as session/rate-window budget, not dollars — both seats are
flat-rate subscriptions.
