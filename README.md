# agent-harness 🧠

A portable Claude Code OS — persistent memory, skills, scheduled agents, and a self-improving loop, running entirely on your Claude subscription. No API key. No per-token billing. No starting from scratch every session.

> **Claude remembers you. The system gets smarter the more you use it.**

---

## Get started

**Use this template** (or clone), open the folder in **Claude Code**, and say **"onboard me"** (or run **`/onboard`**). Claude detects your OS, installs dependencies, sets up the brain, and interviews you to fill in your own memory. Works on macOS, Linux, and Windows.

Full steps + prerequisites: **[ONBOARDING.md](ONBOARDING.md)**.

---

## What it is

Three runtime layers stacked together:

| Layer | Where | What it does |
|---|---|---|
| 🪪 **Identity + rules** | `CLAUDE.md` (auto-loaded by Claude Code) | Who you are, how Claude talks to you, standing rules |
| 📚 **Source-of-truth markdown** | `memory/` | Project briefs, behavioral rules, persona, ideas |
| 🔍 **Conversation history** | `claude-brain/` (SQLite + MCP) | Every session searchable — semantically and by keyword |

Plus:

- ⚡ **Skills** (`skills/`) — 20 reusable slash commands: setup (`/onboard`, `/goal-review`, `/session-reflect`), research and vetting (`/research-swarm`, `/repo-vet`, `/repo-steal`), working discipline (`/fable-discipline`, `/git-verified-agent-orchestration`), design (`/visual-explainer`, `/ux-psychology`, `/page-clone`), upkeep (`/skill-authoring`, `/skill-canary`, `/sync-agent-tools`, `/safety-review`), plus the `/domain-*` suite. When to use each: [`docs/skills.md`](docs/skills.md)
- 🔑 **Agent keyring** (`bin/api.py` + gitignored `bin/secrets/keyring.env`) — call your keyed APIs (YouTube, Gemini, Sketchfab, ...) from any session; keys are injected at request time and **redacted from every output**, so credentials never touch a transcript. `bin/gen_image.py` rides on it for image generation with reference-conditioning.
- 🤖 **Scheduled agents** (`bin/scheduler/`) — weekly planner, security watcher, brain-embed, daily digest, scheduled **cross-platform** (cron / launchd / Task Scheduler) — running while you sleep
- 🛟 **Safety harness** (`bin/runner/`, `bin/execution/`) — kill-switch (STOP file), action/cost ceilings, an audit DB, and a default-deny approval gate wrapping any autonomous action
- 🪝 **Safety hooks** (`bin/hooks/`) — block destructive shell and git commands, pause outward or irreversible actions during unattended runs, gate frontend edits behind design skills, and surface the right skill for a prompt. Off until you enable them: `python bin/register_hook.py --all`. Details: [`docs/hooks.md`](docs/hooks.md)
- 🩺 **Health checks** (`bin/self_loop.py`, `bin/conformance_check.py`, `bin/fleet_status.py`, ...) — the install checks itself: jobs that exited 0 but failed, outcomes that stopped updating, scheduler drift, rule contradictions. A check that cannot read its source says "unknown", never "pass". Details: [`docs/health.md`](docs/health.md)
- 🎯 **Goal loop** (`bin/goal_loop/`, `memory/goals.md`) — weekly progress, questions and next steps for your goals, plus idea seeds. Off until you fill in `memory/goals.md`. Details: [`docs/goal-loop.md`](docs/goal-loop.md)
- 🔒 **security-ops** (`security-ops/`, Windows) — optional read-only host-security monitor + one-time hardening + an on-demand `security-analyst` subagent over a vetted skill library
- 🔄 **Skill-Forge** (`bin/skill_forge/`) — self-improving loop: mines your transcripts → scores skills → proposes improvements
- 📈 **Learning scorecard** (`bin/learning_scorecard.py`) — five weekly numbers that check whether the harness is actually getting better: repeat corrections, correction rate, goals moved, skill hit rate, job error rate. No model calls; leads the weekly briefing
- 📋 **Evolution trail** (`forge/evolution.jsonl`) — append-only changelog of every change to the system

---

## What makes it different

**It compounds.** Every correction you give Claude, every confirmed good approach, every new project brief — all of it gets captured and stays captured. Session 100 is smarter than session 1 because the system learned from sessions 1–99.

**It's yours.** SQLite, Windows Scheduled Tasks, local markdown files. Zero cloud dependencies, zero vendor lock-in. Your data lives on your machine.

**It uses your subscription.** The `claude -p` headless automation runs on your existing Claude Pro/Team/Max account. No API key setup, no surprise bills.

**It's ~70% portable scaffold.** The architecture is reusable. The memory is yours to fill in. You bring the 30% that makes it specific to your life and work.

---

## What you need to bring

| File | What you fill in |
|---|---|
| `memory/user.md` | Who you are — role, projects, goals, setup |
| `memory/soul.md` | How Claude should talk to you |
| `memory/agent.md` | A name and identity for your Claude instance *(optional)* |
| `memory/frame.md` | Your operating philosophy *(optional)* |
| `memory/feedback/*.md` | Your behavioral rules — corrections and confirmations |
| `memory/projects/*.md` | Your active project briefs |
| `CLAUDE.md` | Your name, email, environment |

Every file has a **BOOTSTRAP** section — answer the questions inside, then write the file in your own words.

---

## Quick start

**Recommended:** open the repo in Claude Code and say **"onboard me"** (or run **`/onboard`**) — see [ONBOARDING.md](ONBOARDING.md). It does all of the below for you, on any OS.

**Manual setup** (cross-platform — `python` on Windows, `python3` on macOS/Linux):

```bash
# 1. Clone, then cd in
git clone <your-fork-url> agent-harness && cd agent-harness

# 2. Install deps + set up claude-brain
#    (creates the DB, registers the brain-server MCP + session hooks)
python3 -m pip install -r claude-brain/requirements.txt
python3 claude-brain/scripts/brain-setup.py

# 3. Fill in memory/user.md, memory/soul.md, ...
#    (answer the BOOTSTRAP questions inside each file)

# 4. Open the folder in Claude Code — you're live
```

Full manual guide: `docs/REHYDRATE.md`

---

## Key capabilities

### 🧠 Persistent memory
`session-reflect` captures corrections, confirmed approaches, and new facts at session end — one skill invocation writes them into `memory/` where they load every future session.

### 🔍 Searchable history
`claude-brain` indexes every conversation into SQLite with FTS5 + semantic embeddings. Ask "what did we decide about X last month?" and get the answer.

### 🛡️ Claude-environment watcher
`bin/security_watch.py` flags unexpected changes to your Claude setup (`~/.claude*/` skills, plugins, agents, settings) so a silently-installed or modified extension gets noticed. Cross-platform; scheduled as the daily `security-watch` job.

### 🔒 security-ops (optional, Windows)
A deeper, host-level layer in `security-ops/` for a machine that runs autonomous agents. A strictly read-only nightly sweep (persistence, posture, self-integrity), a one-time ACL hardening that stops a non-elevated process from tampering its own baseline, and an on-demand `security-analyst` subagent over a vetted cybersecurity-skill library (public, cloned at setup — never bundled). See `security-ops/README.md`.

### 🤖 Scheduled automation
A cross-platform scheduler (`bin/scheduler/`) installs jobs natively per-OS (cron / launchd / Task Scheduler) from one declarative registry (`jobs.py`). Bundled + wired by default:
- **Weekly Planner** (Sunday 9am) — what landed, what's closer to ready, highest-leverage next move → `next-session.md` + optional Slack delivery
- **Security Watch** (daily 8am) — flags unexpected changes to your Claude setup
- **Brain Embed** (daily 5am) — backfills semantic embeddings for the conversation brain
- **Self-Test** (daily 5:30am) — the harness tests itself: full `bin/tests` suite + brain health + gbrain liveness → `self-test-report.md` (verdict surfaced by the digest). Components you haven't set up yet report SKIPPED, so a fresh clone is green out of the box
- **Daily Digest** (daily 7am) — "while you were away" report of what ran autonomously (from the runner audit DB), stamped with the self-test verdict

Add your own by appending a `Job(...)` to `bin/scheduler/jobs.py`, then `python bin/scheduler/install.py --apply`. `bin/tests/test_fleet_integrity.py` guards the registry itself: every job's script must exist and compile, and (once installed on Windows) every task must still be firing within its cadence — the "it silently died three weeks ago" failure mode becomes a red test.

### 🩺 Test-Medic (opt-in) — the trust model
`bin/test_medic.py` closes the loop: when the self-test goes red, one scheduled headless `claude -p` attempt repairs the root cause. **It is shipped disabled** (a commented-out Job in `jobs.py`) because — unlike everything else here — it grants an unattended agent *write access* to your repo. Enable it only after you understand what actually constrains it, which is *not* the model's good intentions:

1. **Repair contract** (prompt): no VCS mutation, never delete/skip/weaken a test to go green, smallest-diff root-cause fixes, escalate anything needing human judgment (credentials, spend, policy) to `forge/test-medic-escalation.md`.
2. **HEAD verification** (runner): git HEAD is recorded before/after; a moved HEAD flags the report as a hard-rule violation.
3. **Deterministic verdict** (runner): the runner re-runs `self_test.py` itself after the repair — only a green re-run counts as FIXED. The model's claim of success is never trusted.

One attempt per scheduled slot (anti-thrash), rate-limit aware (backs off to the next slot), kill-switch honored (`forge/STOP`). Still-red escalates to you via the report + optional Slack.

### 🛟 Safety harness
`bin/runner/` wraps autonomous runs with a STOP-file kill-switch, per-run action/cost/time ceilings, and an audit DB (`forge/runner.db`) feeding the daily "while you were away" digest. `bin/execution/` gates real-world actions behind a deterministic risk scorer + default-deny policy + durable approval queue + secret-redaction chokepoint. `bin/goal_loop/` runs a weekly goal assessment from your own git/log signals.

### 📈 Skill-Forge self-improvement loop
Phase 0 (live): scores every skill by usage frequency + outcome signal (did Claude's behavior after invoking the skill look like it helped or hurt?). Surfaces the data for your review. Phase 2 (coming): autonomous revision of self-authored skills.

---

## Architecture

```
agent-harness/
├── CLAUDE.md               ← auto-loaded by Claude Code every session
├── memory/
│   ├── MEMORY.md           ← canonical index (update when adding files)
│   ├── user.md             ← who you are [BOOTSTRAP]
│   ├── soul.md             ← how Claude talks to you [BOOTSTRAP]
│   ├── agent.md            ← Claude instance identity [optional]
│   ├── frame.md            ← operating philosophy [optional]
│   ├── feedback/           ← standing behavioral rules
│   ├── projects/           ← active project briefs
│   ├── ideas/              ← pre-project concepts
│   └── archive/            ← superseded files (kept for history)
│   ├── goals.md            ← your goals, read by the weekly goal loop [BOOTSTRAP]
├── skills/                 ← 20 skills; index in skills/_index.md
│   ├── onboard/            ← guided first-time setup (/onboard)
│   └── session-reflect/    ← end-of-session memory capture skill
├── bin/
│   ├── scheduler/          ← cross-platform job scheduler (cron/launchd/schtasks)
│   ├── configure_claude.py ← register extra MCP servers (cross-platform)
│   ├── skill_forge/        ← Skill-Forge Python package
│   ├── weekly-planner.py   ← weekly "what's next" briefing from your memory
│   ├── learning_scorecard.py ← weekly "is it getting better" card (LLM-free)
│   ├── security_watch.py   ← flags unexpected changes to your Claude setup
│   ├── runner/             ← kill-switch + action/cost ceilings + audit DB + digest
│   ├── execution/          ← gated actions: risk + default-deny policy + approval + secrets
│   ├── goal_loop/          ← weekly goal assessment + idea seeds
│   ├── hooks/              ← safety hooks (enable with register_hook.py)
│   ├── harness_common.py   ← shared helpers: outcomes, alerts, locks, scrubbing
│   ├── self_loop.py        ← finds and re-runs failed jobs
│   ├── conformance_check.py ← health assertions for any install
│   └── sync-agent-tools.py ← keep skills + MCP servers in sync across profiles
├── security-ops/           ← optional Windows host-security module [self-contained]
├── forge/
│   ├── skill-usage.jsonl   ← per-invocation skill log [gitignored]
│   └── evolution.jsonl     ← system changelog [gitignored]
├── claude-brain/           ← transcript memory engine (MIT, see credits)
└── docs/
    ├── REHYDRATE.md        ← cross-machine setup guide
    ├── hooks.md            ← what each hook blocks and how to enable it
    ├── health.md           ← what each health check does and how to run it
    ├── goal-loop.md        ← the weekly goal loop and idea seeds
    ├── skills.md           ← when to use each skill
    ├── specs/              ← design specifications
    └── plans/              ← implementation plans
```

---

## Credits

- **`claude-brain`** — [mikeadolan/claude-brain](https://github.com/mikeadolan/claude-brain) (MIT) — transcript ingestion, SQLite storage, MCP server, semantic embeddings. Extended in this fork.
- Design validated against [Hermes Agent](https://github.com/nousresearch/hermes-agent) by Nous Research — same idea, arrived at independently; Hermes proved the architecture pattern.
