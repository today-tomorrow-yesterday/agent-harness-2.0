---
name: sync-agent-tools
description: "Keep MCP servers, skills and a shared instructions file identical across every Claude Code profile (and Codex / Gemini CLI seats) from one manifest — validate every skill first, then apply with bin/sync-agent-tools.py, and detect drift read-only with bin/skill-sync-check.py. Use when a new MCP server or skill must reach every profile, when onboarding a second profile or subscription, or when sessions behave differently for no visible reason. Triggers on: sync the tools, push this everywhere, skill drift, every profile"
---

# sync-agent-tools — one manifest, every seat

Installed skills are **copies**, and no agent CLI supports "include this file" for MCP-server
config. So with two Claude profiles (two subscriptions, or work + personal), or Claude plus Codex
or Gemini CLI, everything drifts: a skill fixed in one profile is still broken in the other, a
server added to one is missing from the next, a rules file edited in one copy is stale in the
rest. Nothing errors. You notice when the same request behaves differently in two sessions.

This skill fixes that with one manifest and two programs that ship in this repo:

| Program | Does | Writes? |
|---|---|---|
| `bin/sync-agent-tools.py` | validates every managed skill, then applies the manifest to every enabled seat | yes |
| `bin/skill-sync-check.py` | reports drift between profiles and against the repo's `skills/` | never |

Prerequisites: Python 3.10+, PyYAML (`pip install PyYAML`) for a `.yaml` manifest, and the
`claude` CLI on PATH for Claude Code seats (used for `claude mcp add`).

## First-time setup

1. Copy `config/agent-tools.example.yaml` to `config/agent-tools.yaml` (keep that copy out of
   version control — it describes your machine).
2. Edit `seats:` — one entry per Claude config dir (`~/.claude`, plus e.g. `~/.claude-work` if you
   launch a second profile with `CLAUDE_CONFIG_DIR`), and optionally Codex / Gemini. Set
   `enabled: false` for anything you do not run.
3. List the `mcp_servers:` and `skills:` that must be everywhere. Secrets go in your environment,
   referenced as `${VAR}` — never inline.
4. Preview, then apply:

```bash
python bin/sync-agent-tools.py --dry-run
python bin/sync-agent-tools.py
python bin/skill-sync-check.py          # should now report in sync
```

## When to invoke

- After adding or editing a skill or MCP server that every profile should have.
- After editing a skill in this repo — the profile copies are inert until synced.
- Onboarding a new seat: add it under `seats:`, dry-run, apply.
- When a session is missing a skill or tool another session has: run `skill-sync-check.py` first.

## What it does per seat kind

| Kind | MCP servers | Skills |
|---|---|---|
| `claude-code` | `claude mcp remove` + `claude mcp add -s user`, scoped with `CLAUDE_CONFIG_DIR` | mirrored to `<config_dir>/skills/<name>/` |
| `codex` | a marked, managed `[mcp_servers.*]` block in `config.toml`; everything outside the markers is preserved | mirrored + an `agents/openai.yaml` sidecar from `codex_meta` |
| `gemini` | the named entries in `settings.json` → `mcpServers`; other keys preserved | mirrored to `skills_dir` |

Skills are mirrored as **whole directories** — `references/`, templates and helper scripts travel
with `SKILL.md`. (Copying only `SKILL.md` is a classic bug: the skill loads, then points at
reference files that are not there.) Files deleted from the source are removed from the copies;
`node_modules/`, caches and `.bak` files are never copied or removed.

## The gate (why a sync can refuse)

Before touching any seat, every managed skill is checked: `SKILL.md` must pass the repo's skill
contract (`bin/skill_policy.py` — BOM-free frontmatter, `name` equal to the directory, a
`description`) and every `.py` helper inside the skill must compile. One failure aborts the whole
sync with nothing written — shipping a broken skill to four seats at once is worse than shipping
nothing. `--no-gate` bypasses it for emergencies only.

## Optional: one shared instructions file

The `contract:` section renders one file you edit (say `memory/AGENTS.md`) into every seat's
user-level instruction file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, ...) with a per-seat
header and a sha256 stamp. It is a rendered copy rather than a reference because user-scope
instruction files have not reliably expanded `@path` imports and symlinks need elevated rights on
Windows. The previous file is kept as `*.bak-contract`. Re-render alone with `--contract-only`.

## Flags

```bash
python bin/sync-agent-tools.py --dry-run            # report, write nothing
python bin/sync-agent-tools.py --seat claude-work   # one seat
python bin/sync-agent-tools.py --contract-only      # only the shared instructions file
python bin/sync-agent-tools.py --manifest other.yaml
python bin/skill-sync-check.py --json
python bin/skill-sync-check.py --profile a=~/.claude/skills --profile b=~/.claude-work/skills
```

`skill-sync-check.py` exits 0 when in sync, 1 on drift, 2 when a profile directory is missing. It
reports, in order of consequence: skills authored in `skills/` but installed in **no** profile
(unreachable — a profile-vs-profile diff can never see these), installed copies that differ from
the source, skills present in only some profiles, and skills that differ between profiles. Record
deliberate exceptions under `not_installed_by_design:` in the manifest, each with a reason.

## What this does NOT do

- Touch servers or skills that are not named in the manifest.
- Restart running sessions — Claude Code, Codex and Gemini pick up changes at the next session
  start.
- Decide which accounts belong in a global manifest. Everything in it reaches every seat; keep a
  server that is credentialed to an account some seats must not reach (e.g. a work account on a
  personal profile) out of it and configure that one locally.
