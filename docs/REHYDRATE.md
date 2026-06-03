# Rehydrate the agent-os on a new machine

This folder (`Z:\agent-os\` or wherever you put it) is mostly self-contained. To bring it up on a fresh computer, follow this. Total time: under 30 minutes (most of it is the interactive claude-brain setup).

## What carries over

Inside `Z:\agent-os\`:

- `memory/` — every fact, preference, project note, and behavioral rule (markdown, source of truth)
- `skills/` — custom Claude Code skills (when you have them)
- `claude-brain/` — claude-brain runtime + its SQLite DB at `claude-brain/claude-brain.db` (the precious file)
- `Dockerfile`, `compose.yml` — containerization stubs
- `docs/REHYDRATE.md` — this file

Outside the agent-os folder:

- `~/.claude-<profile>\CLAUDE.md` — your identity / persona / rules, auto-loaded every session. **Carry this with you.**

## What does NOT carry over

These live in the OS environment of the new machine:

1. **Claude Code itself** — `npm install -g @anthropic-ai/claude-code` (or the Windows installer / `curl https://claude.ai/install.sh | bash` on macOS/Linux)
2. **Python 3.10+** — needs to be on PATH so `python` resolves
3. **claude-brain Python deps** — `pip install -r claude-brain/requirements.txt` after copying the folder
4. **Hook + MCP registration in `~/.claude\settings.json`** (or `~/.claude-<profile>\settings.json`) — claude-brain's `brain-setup.py` rewrites these

## Rehydrate steps

### 1. Copy the folder

Get the entire `agent-os/` directory onto the new machine. Any method works:
- USB drive
- `robocopy /MIR` from a network share
- Cloud sync (Dropbox/OneDrive/Google Drive) of just this folder — note that the SQLite DB inside `claude-brain/` may need attention if multiple machines write to it concurrently
- Private git repo (recommended for long-term — see "Versioning notes" below)

**Note the new path.** It does NOT have to be `Z:\agent-os\` — anywhere is fine, including `C:\agent-os\`, `D:\tools\agent-os\`, or `/home/me/agent-os/` on Linux.

### 2. Copy your CLAUDE.md

```powershell
# Windows
Copy-Item "<old machine>\Users\<you>\.claude-<profile>\CLAUDE.md" "$env:USERPROFILE\.claude-<profile>\CLAUDE.md"

# macOS / Linux
cp /path/to/old/.claude-<profile>/CLAUDE.md ~/.claude/CLAUDE.md
```

(macOS/Linux use `~/.claude/`. Windows <YourOrg> profile uses `~/.claude-<profile>/`. Adjust per machine.)

### 3. Verify Claude Code is installed

```powershell
claude --version
```

If not, install:
```powershell
# Mac / Linux / WSL
curl -fsSL https://claude.ai/install.sh | bash

# Or via npm anywhere
npm install -g @anthropic-ai/claude-code
```

Then `claude login` to authenticate with your Pro/Max subscription.

### 4. Re-install claude-brain Python deps

```powershell
cd <NEW_AGENT_OS_PATH>\claude-brain
python -m pip install -r requirements.txt
```

This pulls in PyYAML, mcp, sentence-transformers (~80MB model), and numpy. ~5 minutes on a typical connection.

### 5. Re-run brain-setup if hook paths changed

If the agent-os path is different on the new machine, claude-brain's hooks in `~/.claude\settings.json` point at the old path. Either:

**Option A — re-run the interactive setup** (rewrites hooks for the new path):
```powershell
cd <NEW_AGENT_OS_PATH>\claude-brain
python scripts\brain-setup.py
```

Answer the prompts the same way you did the first time. Use the cheat sheet in your original install conversation.

**Option B — hand-edit settings.json** (faster if you know what you're doing): open `~/.claude\settings.json` and rewrite the absolute paths in the `hooks.*.command` entries to point at the new agent-os location.

### 6. Smoke test

Start a new Claude Code session in any directory. Ask:

> "What do you know about me?"

The answer should include your name, role, working preferences, and recent project context — pulled from `~/.claude-<profile>\CLAUDE.md` + claude-brain's recent-summaries injection.

Then ask:

> "Search the brain for our conversation about Hermes."

Claude should call the `search_transcripts` MCP tool and surface relevant past discussions.

If both work, the rehydrate succeeded.

## If something goes wrong

- **CLAUDE.md not loading:** Confirm the file is at `~/.claude\CLAUDE.md` (or `~/.claude-<profile>\CLAUDE.md` for the <YourOrg> profile). Claude Code auto-loads this on session start; if it's not there, no identity context appears.
- **claude-brain hooks not firing:** Check `~/.claude\settings.json` for the `hooks.SessionStart` entries. Confirm the paths point at files that exist on the new machine.
- **MCP tools unavailable:** Run `claude mcp list` — `brain-server` should appear. If not, brain-setup didn't register it; rerun setup or manually `claude mcp add brain-server python <NEW_PATH>\claude-brain\mcp\server.py`.
- **Encoding issues:** If non-ASCII characters in `CLAUDE.md` or memory files render as `?`, set `PYTHONIOENCODING=utf-8` in your environment.

## Versioning notes

If you want git history of how `memory/` and `CLAUDE.md` evolve over time:

```powershell
cd <agent-os path>
git init
echo "claude-brain/" > .gitignore
echo "claude-brain/claude-brain.db" >> .gitignore
echo "claude-brain/logs/" >> .gitignore
git add memory/ skills/ docs/ README.md Dockerfile compose.yml .gitignore
git commit -m "Initial agent-os snapshot"
git remote add origin <your private repo URL>
git push -u origin main
```

The `.gitignore` keeps the SQLite DB and the claude-brain submodule out of your repo. The DB is binary state, not source — you transport it by file copy, not git.

To version `CLAUDE.md` alongside `memory/`, you can symlink it or just copy after edits:

```powershell
Copy-Item "$env:USERPROFILE\.claude-<profile>\CLAUDE.md" "<agent-os path>\CLAUDE.md.snapshot"
```

## Portability principles applied

1. **No absolute paths inside markdown content.** Every `.md` in `memory/` refers to other files by name, never by absolute path.
2. **The only absolute paths on the system are in `~/.claude\settings.json` (claude-brain's hook commands).** Updating that file is the entire rehydrate cost.
3. **The SQLite DB is one file, copyable.** `claude-brain/claude-brain.db` carries with the folder.
4. **No machine-specific state in markdown.** Identity content is portable; what changes per-machine is the hook paths.

If you ever forget how to rehydrate, the answer is in this file. The file always travels with the folder.
