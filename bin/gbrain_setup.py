#!/usr/bin/env python3
"""gbrain_setup.py - optional: wire up a local knowledge brain (gbrain) over your docs.

gbrain (github.com/garrytan/gbrain) is a THIRD-PARTY tool — referenced, not bundled.
This helper detects its dependencies, clones it, pulls the local embedding model,
and registers its MCP server in your Claude Code config (via configure_claude.py).
Everything stays local; no API key.

Usage:
    python bin/gbrain_setup.py            # --check: report deps + what would happen (safe)
    python bin/gbrain_setup.py --apply    # clone gbrain, bun install, pull model, wire MCP

Dependencies (installed/instructed): git, bun (bun.sh), Ollama (ollama.com) +
the `nomic-embed-text` model. Heavy-ish; that's why gbrain is opt-in.

Gotchas carried from production use:
  - gbrain's DB (PGLite) is SINGLE-WRITER: only one `gbrain serve` can hold it at
    a time. A Claude session's MCP holds the lock, so a second client / a CLI
    import while a session is open will block. Run bulk imports when no session is up.
  - `gbrain import <dir>` ingests markdown; `gbrain sync --strategy code` builds the
    code graph (code_def/callers/blast). They are different commands.
  - Never write gbrain's config with a BOM (it breaks the JSON parser).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

GBRAIN_REPO = "https://github.com/garrytan/gbrain"
DEFAULT_DIR = Path.home() / ".gbrain-tool"          # where the tool clone lives
OLLAMA_HOST = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"

INSTALL_HINTS = {
    "git":  {"macos": "brew install git", "linux": "sudo apt install git",
             "windows": "winget install Git.Git"},
    "bun":  {"macos": "brew install oven-sh/bun/bun", "linux": "curl -fsSL https://bun.sh/install | bash",
             "windows": "powershell -c \"irm bun.sh/install.ps1 | iex\""},
    "ollama": {"macos": "brew install ollama", "linux": "curl -fsSL https://ollama.com/install.sh | sh",
               "windows": "winget install Ollama.Ollama"},
}


def detect(tool: str) -> bool:
    return shutil.which(tool) is not None


def mcp_args(gbrain_dir: Path) -> list[str]:
    """The configure_claude.py argv to register the gbrain MCP (pure; testable)."""
    cli = str(Path(gbrain_dir) / "src" / "cli.ts")
    return ["add-mcp", "--name", "gbrain", "--command", "bun",
            "--arg", cli, "--arg", "serve", "--env", f"OLLAMA_HOST={OLLAMA_HOST}"]


def _os_name() -> str:
    import platform
    return {"darwin": "macos", "linux": "linux", "windows": "windows"}.get(
        platform.system().lower(), "linux")


def _wire_mcp(gbrain_dir: Path) -> None:
    helper = Path(__file__).resolve().parent / "configure_claude.py"
    subprocess.run([sys.executable, str(helper), *mcp_args(gbrain_dir)], check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Set up the optional gbrain knowledge brain.")
    ap.add_argument("--apply", action="store_true", help="Actually clone/install/wire (default: check only).")
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help="Where to clone gbrain.")
    ns = ap.parse_args(argv)
    gbrain_dir = Path(ns.dir)
    osn = _os_name()

    deps = {t: detect(t) for t in ("git", "bun", "ollama")}
    print("gbrain dependency check:")
    missing = []
    for t, ok in deps.items():
        print(f"  [{'ok' if ok else 'MISSING'}] {t}")
        if not ok:
            missing.append(t)
            print(f"        install: {INSTALL_HINTS[t][osn]}")
    if missing:
        print(f"\nInstall the missing tool(s) above, then re-run. (gbrain dir: {gbrain_dir})")
        return 1

    if not ns.apply:
        print(f"\n--check OK. With --apply I would:")
        print(f"  1. git clone {GBRAIN_REPO} {gbrain_dir}")
        print(f"  2. bun install   (in {gbrain_dir})")
        print(f"  3. ollama pull {EMBED_MODEL}")
        print(f"  4. register the gbrain MCP: python bin/configure_claude.py {' '.join(mcp_args(gbrain_dir))}")
        print(f"\nThen ingest your docs:  bun {gbrain_dir / 'src' / 'cli.ts'} import <your-docs-dir>")
        return 0

    if not gbrain_dir.exists():
        subprocess.run(["git", "clone", GBRAIN_REPO, str(gbrain_dir)], check=True)
    subprocess.run(["bun", "install"], cwd=str(gbrain_dir), check=True)
    subprocess.run(["ollama", "pull", EMBED_MODEL], check=True)
    _wire_mcp(gbrain_dir)
    print(f"\ngbrain wired. Restart Claude Code, then ingest your docs:")
    print(f"  bun {gbrain_dir / 'src' / 'cli.ts'} import <your-docs-dir>")
    print("Remember: PGLite is single-writer — run bulk imports with no Claude session open.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
