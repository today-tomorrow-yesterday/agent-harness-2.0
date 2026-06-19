# Onboarding — set up agent-harness on your machine

A portable Claude Code OS: persistent memory, a searchable conversation brain,
skills, and (optionally) scheduled agents — all running on **your** Claude
subscription, on macOS, Linux, or Windows.

## Prerequisites

- **Claude Code** installed and signed in (an active Claude subscription).
- **Python 3.10+** and **git** on your PATH.
  - macOS: `brew install python git`
  - Debian/Ubuntu: `sudo apt install python3 python3-pip git`
  - Windows: `winget install Python.Python.3.12 Git.Git`

## Get set up (the easy way)

1. Get the code — either **"Use this template"** on GitHub, or:
   ```
   git clone <your-fork-url> agent-harness
   cd agent-harness
   ```
2. **Open the folder in Claude Code.**
3. Say: **"onboard me"** (or run **`/onboard`**).

Claude will detect your OS, install dependencies, initialize the brain, wire up
the MCP + session hooks, and interview you to fill in your own `memory/` — then
verify everything works. Answer the ~6 identity questions in your own words.

## What you'll have when it's done

- **Memory that knows you** — Claude loads your `CLAUDE.md` + `memory/` every session.
- **A searchable brain** — every conversation captured, searchable by keyword and meaning.
- **Skills** — reusable slash commands.
- Two optional power-ups you can ask Claude to set up later: **scheduled agents**
  (weekly planner / daily brief / security watcher) and **gbrain** (a local
  knowledge brain over your own docs).

## Manual fallback

If you'd rather run the installer yourself instead of the guided flow:

```
python3 -m pip install -r claude-brain/requirements.txt
python3 claude-brain/scripts/brain-setup.py
```

Then fill in the `memory/*.md` BOOTSTRAP templates by hand. See
[`docs/REHYDRATE.md`](docs/REHYDRATE.md) for the detailed manual steps.
