# Claude Code Identity — agent-harness

> **BOOTSTRAP — this file is the entry point Claude Code auto-loads every session.**
> Fill in the sections marked [BOOTSTRAP] before your first real session.
> The source of truth for everything lives in `memory/` — this file is a pointer + standing rules.

## Minimum-viable orientation

- **Name:** [BOOTSTRAP: your name]
- **Email:** [BOOTSTRAP: your email]
- **Environment:** [BOOTSTRAP: your OS, shell, drive setup]

## Where things live

- **`memory/`** — source of truth for identity, persona, rules, project briefs
  - `MEMORY.md` — canonical index; **start here**
  - `user.md` — who you are
  - `soul.md` — how Claude talks to you
  - `sol.md` — Claude instance identity (optional)
  - `frame.md` — shared operating framework (optional)
  - `feedback/` — standing behavioral rules
  - `projects/` — active project briefs
  - `ideas/` — pre-project concepts
- **`claude-brain/`** — persistent transcript history; search via MCP tools
- **`skills/`** — custom Claude Code skills
- **`bin/`** — automation scripts and scheduled-task registrars
- **`forge/`** — machine-readable operational logs (skill usage, evolution trail)

## Standing rules (always in scope)

### 1. Never commit or push without explicit permission

Never run `git commit`, `git push`, `git add`, or any version-control mutation unless explicitly asked **in the current session**. Read-only git is fine. When in doubt, ask.

### 2. Memory routing

Write identity-level facts (who you are, standing rules, project context) to `memory/` — not to the Claude Code harness's per-project auto-memory directory. The harness default is per-directory; this system is global.

### 3. [BOOTSTRAP: add your own standing rules here]

---

## Getting started

1. Fill out `memory/user.md` (bootstrap questions are inside)
2. Fill out `memory/soul.md`
3. Optionally fill out `memory/sol.md` and `memory/frame.md`
4. Run `claude-brain`'s `brain-setup.py` to register transcript hooks
5. Add your first project brief in `memory/projects/`
6. Install skills into your Claude profile(s) via the `skills/` directory
7. (Optional) Schedule background agents cross-platform: `python bin/scheduler/install.py --apply`

Tip: the fastest path is just to open the repo in Claude Code and say "onboard me" (see `ONBOARDING.md`).

Full setup guide: `docs/REHYDRATE.md`
