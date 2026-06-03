# agent-harness

A portable Claude Code OS — persistent memory, skills, scheduled agents, and a self-improving loop, running entirely on your Claude subscription with no API key required.

Built so Claude Code doesn't start fresh every session.

---

## What it is

Three runtime layers stacked together:

| Layer | Where | What it does |
|---|---|---|
| **Identity + rules** | `CLAUDE.md` (auto-loaded by Claude Code) | Who you are, how Claude talks to you, standing rules |
| **Source-of-truth markdown** | `memory/` | Project briefs, behavioral rules, persona, ideas |
| **Conversation history** | `claude-brain/` (SQLite + MCP) | Every session, searchable semantically + by keyword |

Plus:

- **Skills** (`skills/`) — reusable slash commands: `/session-reflect`, `/persona-architect`
- **Scheduled agents** (`bin/`) — weekly planner, daily brief, AgentShield security watcher
- **Skill-Forge** (`bin/skill_forge/`) — self-improving loop: mines transcripts → scores skills → proposes improvements
- **Evolution trail** (`forge/evolution.jsonl`) — append-only changelog of every system change

---

## What you need to bring

This repo is ~70% portable scaffold. The other ~30% is yours:

| File | What you fill in |
|---|---|
| `memory/user.md` | Who you are |
| `memory/soul.md` | How Claude talks to you |
| `memory/sol.md` | Claude instance name/identity (optional) |
| `memory/frame.md` | Operating philosophy (optional) |
| `memory/feedback/*.md` | Your behavioral rules |
| `memory/projects/*.md` | Your active project briefs |
| `CLAUDE.md` | Your name, email, environment |

Each file has a **BOOTSTRAP** section with questions to answer.

---

## Quick start

```powershell
# 1. Clone
git clone https://github.com/YOUR_USERNAME/agent-harness Z:\agent-harness

# 2. Fill in the bootstrap files
# Start with memory/user.md, then soul.md
# Follow the questions inside each file

# 3. Set up claude-brain (transcript memory)
cd Z:\agent-harness\claude-brain
pip install -r requirements.txt
python scripts/brain-setup.py

# 4. Register MCP server in Claude Code (for both profiles if you have multiple)
CLAUDE_CONFIG_DIR='C:\Users\YOU\.claude' claude mcp add -s user brain-server -- python3 'Z:\agent-harness\claude-brain\mcp\server.py'

# 5. Install skills
# Copy skills/session-reflect/SKILL.md → ~/.claude/skills/session-reflect/SKILL.md

# 6. Open a Claude Code session in Z:\agent-harness and start talking
```

Full setup: `docs/REHYDRATE.md`

---

## Key design decisions

**No API key required.** Everything runs via your Claude Pro/Team/Max subscription. The `claude -p` headless invocations (farmers, weekly-planner) consume subscription rate limits, not per-token billing.

**Local-first.** SQLite, no cloud dependencies, Windows Scheduled Task for automation. Nothing phones home except the Claude CLI.

**Convention over enforcement.** Behavioral rules live in `memory/feedback/` as markdown. Claude reads them — they're not enforced by hooks. This makes them easy to edit and extend.

**Self-improving.** `session-reflect` captures corrections and surprises at session end. Skill-Forge scores skill effectiveness over time. The system gets better by being used.

---

## Architecture

```
agent-harness/
├── CLAUDE.md               ← auto-loaded by Claude Code every session
├── memory/
│   ├── MEMORY.md           ← canonical index
│   ├── user.md             ← who you are [BOOTSTRAP]
│   ├── soul.md             ← how Claude talks to you [BOOTSTRAP]
│   ├── sol.md              ← Claude instance identity [optional]
│   ├── frame.md            ← operating philosophy [optional]
│   ├── feedback/           ← standing behavioral rules
│   ├── projects/           ← active project briefs
│   ├── ideas/              ← pre-project concepts
│   └── archive/            ← superseded files (don't delete)
├── skills/
│   ├── session-reflect/    ← end-of-session memory capture
│   └── persona-architect/  ← AI persona design + consistency path
├── bin/
│   ├── skill_forge/        ← Skill-Forge Python package
│   ├── skill-refiner.py    ← Phase 0 scorer (read-only signal)
│   ├── weekly-planner.py   ← Sunday briefing → next-session.md
│   ├── daily-brief.py      ← Daily digest
│   ├── shield-watch.ps1    ← AgentShield security watcher
│   └── install-*.bat       ← Register Windows Scheduled Tasks
├── forge/
│   ├── skill-usage.jsonl   ← per-invocation skill log [gitignored]
│   └── evolution.jsonl     ← system changelog [gitignored]
├── claude-brain/           ← transcript memory engine (third-party, MIT)
└── docs/
    ├── REHYDRATE.md        ← cross-machine setup guide
    ├── specs/              ← design specs
    └── plans/              ← implementation plans
```

---

## Credits

- `claude-brain` — [mikeadolan/claude-brain](https://github.com/mikeadolan/claude-brain) (MIT) — transcript ingestion, SQLite storage, MCP server, semantic embeddings
- Design inspired by [Hermes Agent](https://github.com/nousresearch/hermes-agent) (same idea, arrived at independently)
