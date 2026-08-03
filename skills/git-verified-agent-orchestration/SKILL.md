---
name: git-verified-agent-orchestration
description: "Delegate work to multiple AI subagents without trusting their self-reports, by making every unit of work a real git commit that is independently verified and separately reviewed before the next subagent starts. Triggers on: orchestrate subagents, verify agent work, swarm of agents, delegate to subagents, agent orchestration"
---

**Use when:** delegating work to multiple AI agents (code, research, or anything that produces a checkable file) and you need to trust the result without personally reviewing every step.

**Don't use when:** the task is small enough that eyeballing the result yourself is faster than setting this up. This has real fixed overhead per task. Pay it when the risk of an unnoticed wrong result is real, not by default.

## The core principle

An agent's self-report is a claim. A real artifact (a commit, a file, a citation) is evidence. Never act on the first when the second is available.

This isn't about agents being untrustworthy on purpose. It's that "done" and "claims to be done" are indistinguishable in a transcript, and the only way to tell them apart is to check something outside the agent's own words.

## Prerequisite

Any shared, versioned file store works. A git repo is the obvious default since almost every team already has one, and it tracks *any* file, not just code. Research findings, config, documentation, anything written to a file can go through this loop. If there's genuinely nothing to write to a file, this pattern doesn't apply; find or create an artifact first.

## The mechanism

**Setup.** One shared repo (or a fresh throwaway one if the work is disposable), one branch, checked out into its own isolated working copy. Nothing on the main line is touched until everything below is verified.

**The per-subagent loop, one at a time, never in parallel:**

1. Orchestrator records the current commit hash (`BASE`) before dispatching anything.
2. Orchestrator dispatches ONE subagent with ONLY its own narrow task. Not the full goal, not other subagents' context. It has nothing to wander into.
3. Subagent does the work and commits. The commit is the deliverable, not the subagent's description of it.
4. Orchestrator computes the diff `BASE..HEAD` and independently re-verifies it: re-runs whatever check applies (tests, re-fetching a cited source, re-computing a result). Never just the subagent's claim.
5. A separate reviewer subagent, explicitly told not to trust the implementer's self-report either, checks that same commit range against the original requirement.
6. Only if that's clean does `BASE` become `HEAD`, and the next subagent gets dispatched.

**Fixes are new commits, never rewrites.** No amending, no force-pushing. The full history of what was tried, what was wrong, and what fixed it stays permanently inspectable. Nothing gets summarized away.

**The final pass reviews everything at once.** After every individual commit has passed its own review, one more review runs over the *entire* accumulated diff, first commit to last, as a single change. This is the step that earns the framework's cost: problems that only exist at the seam between two individually-correct pieces are invisible to any review scoped to one commit at a time. Only a whole-diff review catches them.

**Merge only after all of it is green.**

## Verify the thing, not a proxy for it

The orchestrator's re-verification has to test what a user would actually do with the output, not just that the output exists and is wired up correctly.

Real failure, 2026-08-02: a generated landing page was confirmed saved and correctly registered, and the check stopped there. Every link on the page 404'd. Both the orchestrator and the reviewer had verified the artifact's *wiring* and neither clicked a link. The lesson generalizes: "the artifact exists and points at the right place" is a proxy. "The artifact does its job when used" is the actual check.

## Why this beats a flat swarm

A flat swarm (fire N agents at a goal, collect N reports, done) has no ground-truth layer. Every claim is trusted at face value, and scope isn't structurally enforced: an agent holding the full goal can decide, on its own, to do a piece it wasn't assigned.

This framework removes both failure modes by construction, not by asking agents to behave better:

- No claim is trusted without a real artifact to check it against
- No agent sees more than its own task, so there's nothing to drift into
- Every fix is additive and re-reviewed, so history is a real audit trail, not a rewritten story
- The whole is reviewed, not just the parts. The only way to catch defects that live between pieces instead of inside any one of them

## Checklist

- [ ] Isolated workspace before any subagent touches anything
- [ ] One subagent at a time, narrow task only, no shared context between them
- [ ] Subagent output is a real committed artifact, not a status message
- [ ] Orchestrator independently re-verifies before trusting any "done"
- [ ] Verification exercises the artifact the way a user would, not just its existence
- [ ] A separate reviewer subagent checks the same artifact, told not to trust the self-report
- [ ] Fixes are new commits, never rewrites
- [ ] One final review over the whole accumulated result before it ships

## Prior art

The code-specific version of this pattern exists as Claude Code skills (`subagent-driven-development`, `using-git-worktrees`, `finishing-a-development-branch`). This skill is the tool-agnostic synthesis of the core loop, usable regardless of harness and applicable beyond code.
