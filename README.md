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

- ⚡ **Skills** (`skills/`) — reusable slash commands: `/session-reflect`, `/persona-architect`
- 🤖 **Scheduled agents** (`bin/`) — weekly planner, daily digest, AgentShield security watcher — running while you sleep
- 🔄 **Skill-Forge** (`bin/skill_forge/`) — self-improving loop: mines your transcripts → scores skills → proposes improvements
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
| `memory/sol.md` | A name and identity for your Claude instance *(optional)* |
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

### 🛡️ AgentShield security watcher
Polls `~/.claude*/` for skill/plugin/agent file changes every hour. Surfaces findings via Windows Toast notifications. Keeps your Claude environment auditable.

### 🤖 Scheduled automation
Windows Scheduled Tasks drive:
- **Weekly Planner** (Sunday 9am) — what landed, what's closer to ready, highest-leverage next move → `next-session.md` + optional Slack delivery
- **Daily Brief** (7am) — activity digest, inbox pulse, news summary
- **Brain Embed** (5am) — nightly semantic embedding backfill

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
│   ├── sol.md              ← Claude instance identity [optional]
│   ├── frame.md            ← operating philosophy [optional]
│   ├── feedback/           ← standing behavioral rules
│   ├── projects/           ← active project briefs
│   ├── ideas/              ← pre-project concepts
│   └── archive/            ← superseded files (kept for history)
├── skills/
│   ├── session-reflect/    ← end-of-session memory capture skill
│   └── persona-architect/  ← AI persona design + consistency path skill
├── bin/
│   ├── skill_forge/        ← Skill-Forge Python package (44 tests)
│   ├── skill-refiner.py    ← Phase 0 scorer (read-only signal)
│   ├── weekly-planner.py   ← Sunday briefing generator
│   ├── daily-brief.py      ← Daily digest
│   ├── shield-watch.ps1    ← AgentShield security watcher loop
│   └── install-*.bat       ← Register Windows Scheduled Tasks
├── forge/
│   ├── skill-usage.jsonl   ← per-invocation skill log [gitignored]
│   └── evolution.jsonl     ← system changelog [gitignored]
├── claude-brain/           ← transcript memory engine (MIT, see credits)
└── docs/
    ├── REHYDRATE.md        ← cross-machine setup guide
    ├── specs/              ← design specifications
    └── plans/              ← implementation plans
```

---

## Credits

- **`claude-brain`** — [mikeadolan/claude-brain](https://github.com/mikeadolan/claude-brain) (MIT) — transcript ingestion, SQLite storage, MCP server, semantic embeddings. Extended in this fork.
- Design validated against [Hermes Agent](https://github.com/nousresearch/hermes-agent) by Nous Research — same idea, arrived at independently; Hermes proved the architecture pattern.
