# Validate Phase 1 — fresh-machine smoke test

Goal: confirm the **guided onboarding** works end-to-end on a real machine
(especially **macOS / Linux**, since it was authored on Windows). ~15 minutes.
Report results back with the ✅/❌ checklist at the bottom.

## Prerequisites
- **Claude Code** installed + signed in (active Claude subscription).
- **Python 3.10+** and **git** on PATH (`python3 --version`, `git --version`).
- Access to the repo (your teammate added you as a collaborator, or gave you a copy).

## Steps
1. **Clone + open**
   ```bash
   git clone <repo-url> agent-harness && cd agent-harness
   ```
   Open the folder in Claude Code.

2. **Run onboarding** — tell Claude: **"onboard me"** (or run `/onboard`).
   Expect Claude to, in order:
   - detect your OS + check Python/git,
   - `pip install -r claude-brain/requirements.txt`,
   - run `python3 claude-brain/scripts/brain-setup.py` (creates the DB, registers
     the brain-server MCP + 6 hooks — answer its prompts),
   - interview you to fill `memory/user.md`, `memory/soul.md`, etc.,
   - verify + summarize.

3. **Restart the Claude Code session** (so the MCP + hooks come live).

4. **Verify it works:**
   - Ask Claude **"who am I?"** → it should answer from your new `memory/user.md`.
   - Ask it to **search the brain** for a word from this session → a result returns.
   - Run the test suite from the repo root: `python3 -m pytest -q` → all pass.

## Report back (paste this filled in)
```
OS + version:            __________
Python version:          __________
[ ] /onboard ran without manual fixes
[ ] brain-setup.py completed (DB + MCP + hooks registered)
[ ] memory interview wrote my files
[ ] after restart: "who am I?" answered from memory
[ ] brain search returned a result
[ ] pytest: ___ passed
Any errors / rough edges (paste exact text):
__________________________________________
```
