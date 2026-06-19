# Optional: gbrain — a local knowledge brain over your docs

[gbrain](https://github.com/garrytan/gbrain) is a **third-party** local knowledge
brain: semantic + keyword search over your own markdown/code, plus a code graph
(`code_def` / `code_callers` / `code_blast`). It runs **locally** on Ollama
embeddings — no API key. agent-harness can wire it in as an **optional** power-up;
it's not bundled (it's someone else's project) and it's heavier than the core, so
it's opt-in.

## Set it up

```bash
python bin/gbrain_setup.py            # check deps + preview (safe, no changes)
python bin/gbrain_setup.py --apply    # clone gbrain, bun install, pull model, wire MCP
```

This clones gbrain to `~/.gbrain-tool` (override with `--dir`), pulls the
`nomic-embed-text` model, and registers gbrain's MCP server in your Claude Code
config via `bin/configure_claude.py`. Restart Claude Code afterwards.

**Prerequisites** (the script detects + gives you the OS-specific install command):
`git`, [`bun`](https://bun.sh), and [Ollama](https://ollama.com).

## Ingest your content

```bash
# markdown / prose:
bun ~/.gbrain-tool/src/cli.ts import <your-docs-dir>

# build the code graph over a repo:
bun ~/.gbrain-tool/src/cli.ts sync --source <id> --strategy code
```

Point it at *your* notes/projects/code — never bundle private content into the repo.

## Gotchas (carried from production use)

- **PGLite is single-writer.** Only one `gbrain serve` can hold the DB at a time.
  A Claude session's MCP holds the lock, so a bulk import/sync run while a session
  is open will block — **run bulk imports when no Claude session is up.**
- **`import` ≠ `sync --strategy code`.** `import` ingests markdown; the code graph
  is built by `sync --strategy code`. Plain import silently skips code files.
- **Never write gbrain's config with a UTF-8 BOM** — it breaks the JSON parser.
- **Schedule it** (e.g. a daily code-graph refresh) via `bin/scheduler` — but mind
  the single-writer lock; pick a window when no session runs.
