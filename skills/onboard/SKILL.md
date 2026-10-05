---
name: onboard
description: Use when setting up agent-harness on a new machine for the first time — installs dependencies, initializes the brain, wires the MCP + hooks, and interviews the user to fill in their own memory. Cross-platform (macOS / Linux / Windows). Triggers - "onboard me", "set this up", "first-time setup", "/onboard".
---

# Onboarding a new machine

Goal: take a freshly cloned `agent-harness` and leave the user with a working,
personalized Claude Code OS — memory that knows them, a searchable brain, and
session capture — on whatever OS they're on. **The mechanical install is done by
`claude-brain/scripts/brain-setup.py` (cross-platform, idempotent); your job is
to drive it, then conduct the identity interview and verify.**

Do the steps in order. After each, confirm success before moving on. If a step
fails, stop and tell the user the exact error — don't guess past it.

## 1. Preflight

- Detect OS: `python3 -c "import platform; print(platform.system())"` (use
  `python` if `python3` is absent — Windows often only has `python`).
- Confirm a Python **3.10+** interpreter and `git` are available
  (`shutil.which` / `--version`). If missing, print the OS-correct install hint
  and stop:
  - macOS: `brew install python git`
  - Debian/Ubuntu: `sudo apt install python3 python3-pip git`
  - Windows: `winget install Python.Python.3.12 Git.Git`
- Confirm we're running inside Claude Code with an active subscription (this
  flow assumes the repo is open in Claude Code).

## 2. Install dependencies

```
python3 -m pip install -r claude-brain/requirements.txt
```

Tell the user `sentence-transformers` lazily downloads a ~80 MB model on first
semantic search (keyword search works immediately without it).

## 3. Run the core installer

```
python3 claude-brain/scripts/brain-setup.py
```

This creates the SQLite DB + directories, registers the **brain-server MCP**
(into `~/.claude.json`), registers the **6 session hooks**
(SessionStart / UserPromptSubmit / Stop / SessionEnd / PreCompact / PostCompact,
into `settings.json`), and seeds the brain. It is interactive (asks before
writing to each profile) and idempotent — answer its prompts; re-running is safe.

> Do NOT hand-edit `~/.claude.json` or `settings.json` for the brain — let
> brain-setup.py own that. `bin/configure_claude.py` is only for registering
> *extra* MCP servers later (e.g. gbrain in the optional advanced setup).

## 4. Identity interview (fill their memory)

The `memory/` files ship as **BOOTSTRAP templates**. Walk them with the user and
write each in *their own words*, then delete that file's BOOTSTRAP block:

1. `memory/user.md` — who they are, role, projects, north star.
2. `memory/soul.md` — how they want Claude to talk to them.
3. `memory/sol.md` (optional) — a name/identity for their Claude instance.
4. `memory/frame.md` (optional) — their operating philosophy.
5. `memory/feedback/*.md` — standing behavioral rules (start with the example).
6. `memory/projects/*.md` — one brief per active project.
7. `memory/goals.md` (optional) — their current goals, which switch on the weekly Goal Loop
   once the file is filled in and its BOOTSTRAP block deleted (`/goal-review` walks it).

Ask the embedded bootstrap questions **one at a time** (don't dump all at once).
Keep answers in their voice; don't impose yours. Finally update `memory/MEMORY.md`
so it indexes whatever they created.

(Power-user alternative: `python3 claude-brain/scripts/brain-setup.py
--questionnaire` imports a filled questionnaire instead of a live interview.)

## 5. Verify

- Restart the Claude Code session (or note that the brain MCP + hooks come live
  next session) so the MCP connects.
- Probe the brain: run a keyword search via the brain tools and confirm a result
  comes back.
- Confirm `CLAUDE.md` + `memory/` load (ask Claude "who am I?" — it should answer
  from their new `user.md`).

## 6. Summary

Print a short "you're set up" recap: what's now active (memory, searchable brain,
session capture), then offer the next steps.

**Recommended, and worth doing now** — turn on the skill-shape guard:

```
python bin/register_hook.py skill-shape-guard
```

Skills fail *silently*: get the shape wrong and nothing errors, the skill just never loads. One
shipped in this repo unloadable because of an invisible byte-order mark. The guard refuses a
malformed skill at write time and prints the correct path. It fails **open**, so a guard bug can
never block their work, and `HARNESS_HOOKS_DISABLED=1` turns it off. See `ONBOARDING.md`.

**Optional, separate opt-in setups they can ask for later** — **scheduled agents** (weekly
planner / daily brief / security watcher) and **gbrain** (a local knowledge brain over their own
docs).
