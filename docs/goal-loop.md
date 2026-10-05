# The Goal Loop and idea cultivation

Two weekly, mostly LLM-free loops that ride on the weekly briefing
(`bin/weekly-planner.py`). Both are **off until you opt in** and both are safe on a
fresh clone: no goals file, no seedbank, no Slack webhook and no runner database all
mean "nothing to do", never an error.

| Loop | You keep | It does each week | You answer with |
|---|---|---|---|
| Goal Loop | `memory/goals.md` | measures movement per goal, asks up to 4 questions, recommends next actions, runs at most 2 gated web-research fetches | `/goal-review` |
| Idea cultivation | `forge/seedbank.json` | brings back every undecided idea twice a week until you decide | `bin/seeds-cli.py`, or tell Claude |

## Switching the Goal Loop on

`memory/goals.md` ships as a template carrying a `goal-loop:template` marker inside
its BOOTSTRAP block. While the marker is there the planner logs one INFO line and
skips the file entirely — no section, no research, no rewrite. That is how a fresh
clone avoids assessing placeholder goals.

1. Fill in the north star and your goals (or run `/goal-review`, which interviews you).
2. Delete the BOOTSTRAP block, marker included.
3. Check: `python bin/weekly-planner.py --dry-run` logs a non-zero `goal loop` size.

Deleting `memory/goals.md` switches the loop off again.

## goals.md format

```
# North Star
One or two sentences.

# Active Goals
## G1 — A short goal title
- outcome: what is true when this is done
- success_signal: how you would see it moving
- status: on-track
- last_moved: 2026-01-15
- next_step: research the three closest alternatives
- repos: ["my-app"]
- research_notes:
- open_questions: []

Anything else under the heading (checklists, prose) is kept verbatim.
```

Only `## G<number> — Title` headings are goals; any other heading inside a goal is
body text. Text above `# North Star` (frontmatter, notes) is preserved on rewrite.

| Field | Read by | Written by the loop? |
|---|---|---|
| `status` | `stalled` / `blocked` drive the questions; `paused ...` excludes the goal from everything | no |
| `last_moved` | quoted in the "kill it, or what's the ONE next step?" question | no — only you move it, and only on real movement |
| `next_step` | containing `research` selects the goal for a web-research fetch; containing a publish / sign-up / buy / send style verb tags its recommendation `[needs approval]` | no |
| `repos` | git commits in the last 7 days in each listed checkout count as movement. Relative names resolve next to this repo; absolute paths work too | no |
| `research_notes` | — | yes, fenced as untrusted web content |
| `open_questions` | — | yes, but only when the loop generated new questions for that goal; hand-written ones are never wiped by an empty week |

A `status: paused (<reason>)` goal stays in the file untouched. It gets no verdict,
question, research or recommendation, and the section lists paused goals on one line.

## What runs, and under which safety layers

On a live (non-dry) run, after the briefing itself is generated:

1. **Signals** — `goal_loop/signals.py` counts recent commits per goal. Missing data
   counts as no movement; the loop never invents progress.
2. **Assess / question / recommend** — pure functions over the signals.
3. **Research** — at most `RESEARCH_CAP` (2) goals whose `next_step` mentions
   research. Each fetch is a `research_web` action (`claude -p` with only WebSearch +
   WebFetch) that goes through two layers:
   - the **runner** (`bin/runner/run.py`) bounds the batch: kill-switch
     (`forge/STOP`), action ceiling, 30-minute wall clock, every step audit-logged
     to `forge/runner.db`;
   - inside it, the **execution gate** (`bin/execution/execute.py`) scores the
     question's risk and applies `forge/execution_policy.json`. A benign question
     runs; one that reads like a publish, sign-up or payment step **parks for
     approval** and does not run.
4. **Write-back** — open questions and research notes are written to `goals.md`
   atomically, and only if something changed.

Fetched text is **untrusted data**: it is wrapped in `UNTRUSTED WEB CONTENT` fences
with any forged fence markers inside it defanged, and the fence survives truncation.

### Approving a parked research question

```
python -m execution.cli approvals          # run from bin/: list what is waiting
python -m execution.cli approve <id>       # or: reject <id>
```

The next weekly run finds the approval, runs that exact question once and marks the
approval spent. A pending or rejected question is not queued again. Secrets in a
summary are scrubbed before it is stored, and the match compares the scrubbed forms.

## Idea cultivation (seeds)

A seed is an idea you are not ready to make a goal. Plant one:

```
python bin/seeds-cli.py add "idea in one line" "optional detail"
python bin/seeds-cli.py list
```

Every 3.5 days each active seed (`new`, `refining`, `growing`) is due again. The
weekly briefing shows due seeds in a **Seed Review** section, and
`bin/seed-nudge.py` can post the same review to Slack between briefings (schedule it
yourself; `--dry-run` previews). Decide with
`python bin/seeds-cli.py water|refine|letgo|graduate|snooze <id>`:

| Verdict | Status | Comes back? |
|---|---|---|
| water | growing | yes |
| refine | refining | yes |
| snooze | unchanged | yes, after the next interval |
| graduate | graduated | no — it became a goal or project |
| let go | let_go | never |

A nudge that could not be delivered (Slack not configured, or the post failed) does
not count as surfaced, so the seed stays due.

## Slack routing

`bin/notify_slack.py` has two routes. `alerts` (the default) is for things that need
a human; `digest` (daily digest, seed nudges) is routine traffic for a channel you
can mute. Configure the digest channel with `SLACK_WEBHOOK_DIGEST_URL` or
`bin/secrets/slack-webhook-digest.txt`; until it exists, digest messages go to the
main webhook with a `[digest]` title prefix. `HARNESS_SLACK_DRY_RUN=1` (or
`--dry-run`) sends nothing.

## Files

| Path | What |
|---|---|
| `bin/weekly-planner.py` | `run_goal_loop`, `run_seed_review` |
| `bin/goal_loop/` | `goals_io`, `signals`, `assess`, `questions`, `recommend`, `research`, `report`, `seeds` |
| `bin/execution/`, `bin/runner/` | the gate and the bounded runner the research goes through |
| `bin/seeds-cli.py`, `bin/seed-nudge.py` | seed capture / decisions, Slack nudge |
| `skills/goal-review/` | the answer half of the loop |
| `forge/runner.db`, `forge/seedbank.json` | per-machine state, created on first use |
