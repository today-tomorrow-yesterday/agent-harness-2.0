---
name: safety-review
description: "Review and clear the safety review queue -- outward-facing commands (sending email, external POST/PUT, publishing, deploying) that the safety-queue hook paused during an unattended run because no human was present to approve them. Modes: list, approve <id>, deny <id>, clear. Triggers on: safety queue, safety review, review the safety queue, paused actions"
---

# Safety Review -- the "ask a human and wait" review desk

The companion to `bin/hooks/safety-queue.py`. That hook runs during **unattended** runs
(`HARNESS_UNATTENDED=1`). When a command is a narrow tier-2 action -- outward-facing, or
irreversible to someone other than the operator -- it QUEUES a request, denies that attempt, and
tells the model to move on. This skill is how the user works the resulting queue.

## What is (and is not) in the queue

- **In scope (tier 2, paused for a human):** sending email or messages, external
  POST/PUT/PATCH/DELETE to a non-localhost host, publishing packages (npm/PyPI/crates/gems),
  container registry pushes, public GitHub releases/PRs/issues/gists, production deploys.
- **Not here (tier 1, hard-denied by `pre-tool-guard.py`):** `rm -rf` of a root, force-push,
  `git commit`/`git push` in unattended mode, `DROP TABLE`, `curl | sh`. Those are blocked, not
  queued -- a review flow cannot approve them headless. If the user wants one, they run it.
- **Not here (allowed):** ordinary file reads/writes, plain GETs and downloads, localhost traffic.

## Files and the one way to change them

Paths are relative to the repository root. `HARNESS_SAFETY_DIR` overrides the directory.

- `forge/safety/queue.json` -- JSON array of PENDING records
  `{id, ts, status, label, reason, command, cwd, session_id}`.
- `forge/safety/history.json` -- append-only event log (`queued` / `approved` / `denied` /
  `cleared`).
- `forge/safety/.lock` -- held for every read-modify-write of the two files above.
- Denials also add a standing line to `memory/feedback/safety_denials.md` so the lesson sticks.

**Never edit `queue.json` or `history.json` by hand.** Unattended sessions may be appending to
them at the same moment; a hand edit that does not hold the lock silently drops their entries.
Every change goes through the review CLI, which takes the same lock as the hook:

```
python bin/hooks/safety-queue.py list
python bin/hooks/safety-queue.py approve <id>
python bin/hooks/safety-queue.py deny <id> --reason "<one line>"
python bin/hooks/safety-queue.py clear
```

`approve` and `deny` print the removed record as JSON (exit 1 and `not found` if the id is not
pending); `list` prints the pending records as JSON.

## Modes

Parse the arguments (or the user's phrasing) into a mode. Default to **list** when empty.

### `list` (default)

Run `list`. If it returns `[]`, say so plainly. Otherwise print each pending request as a compact
block -- the id and the human reason first, then the exact command:

```
[HIGH]   q_4ce3aee47e  --  publishing a package to a registry
   cmd:  npm publish --access public
   when: 2026-01-19T14:47Z   cwd: /path/to/project   session: sess-abc1
```

Severity by class: HIGH = publish / deploy / release; MEDIUM = sending email or messages;
LOW = external HTTP write. End with the one ask: `approve <id> / deny <id> / clear`.

### `approve <id>`

1. Run `approve <id>`. If it reports `not found`, say so and stop.
2. Report the exact command from the printed record, fenced and paste-ready, and state clearly
   that **approval is not auto-run**. The hook already denied the original attempt and this skill
   does NOT re-execute it. The user runs it themselves, or re-runs the job attended. That keeps the
   invariant: nothing outward-facing fires without a person present.

### `deny <id>`

1. If no reason was given, ask for a one-line one ("why deny -- so it is not proposed again?").
2. Run `deny <id> --reason "<reason>"`. If it reports `not found`, say so and stop.
3. Append a dated bullet to `memory/feedback/safety_denials.md` (create it with frontmatter
   `name: safety_denials`, `description: actions the user denied from the safety queue`,
   `type: feedback` if absent):
   `- <date> -- DENIED: <reason>. Command class: <label>. Do not propose again. (<id>)`
   If this created the file, add it to the `feedback/` section of `memory/MEMORY.md`.
4. Report: `Denied <id> -- logged; will not propose again.`

### `clear`

Confirm first (show the pending count from `list`). On yes, run `clear` and report how many were
cleared. `clear` is **not** approval -- cleared items are dropped, not run.

## Invariants

- **Only the CLI changes the queue.** It holds the lock and writes atomically.
- **History is append-only.** Every state change leaves a trail.
- **Never auto-execute a queued command.** This desk records decisions; humans run outward actions.
- **Never edit `settings.json` here.** Registering or removing the hook is done with
  `python bin/register_hook.py safety-queue` (see `docs/hooks.md`), as a separate, reviewed step.
