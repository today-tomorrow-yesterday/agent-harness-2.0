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

## Recommended: turn on the skill-shape guard

Skills fail *silently*. Get the shape wrong — a bare `.md` instead of a directory, a missing
frontmatter block, a byte-order mark ahead of the `---` — and nothing errors. The skill simply
never loads, and you find out weeks later when invoking it does nothing. This has happened in this
repo: one skill shipped unloadable because of an invisible BOM.

One command registers a hook that refuses a malformed skill at the moment it is written, and tells
you the exact path to use instead:

```
python bin/register_hook.py skill-shape-guard
```

Anything already on disk is covered by the matching test:

```
python -m pytest bin/tests/test_skill_conformance.py -q
python bin/skill_policy.py          # prints the contract + audits your skills
```

The guard fails **open** — if it ever errors it allows the write rather than blocking your work —
and `HARNESS_HOOKS_DISABLED=1` turns it off. See the `skill-authoring` skill for the full contract.

## Manual fallback

If you'd rather run the installer yourself instead of the guided flow:

```
python3 -m pip install -r claude-brain/requirements.txt
python3 claude-brain/scripts/brain-setup.py
```

Then fill in the `memory/*.md` BOOTSTRAP templates by hand. See
[`docs/REHYDRATE.md`](docs/REHYDRATE.md) for the detailed manual steps.
