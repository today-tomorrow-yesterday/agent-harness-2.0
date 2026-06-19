"""Cross-platform, idempotent, BOM-free registrar for *extra* MCP servers in the
Claude Code config (~/.claude.json).

Scope: this registers ADDITIONAL stdio MCP servers (e.g. gbrain) that the core
installer does not. `claude-brain/scripts/brain-setup.py` already owns the
brain-server MCP registration AND all hook registration (hooks live in
settings.json) — do not duplicate those here.

A UTF-8 BOM breaks JSON parsers, so writes are always BOM-free
(encoding="utf-8"); reads tolerate a pre-existing BOM (encoding="utf-8-sig").

CLI:
    python bin/configure_claude.py add-mcp --name gbrain \
        --command bun --arg /path/to/gbrain/src/cli.ts --arg serve \
        --env OLLAMA_HOST=http://localhost:11434 [--dry-run]

Config location: $CLAUDE_CONFIG_PATH if set, else ~/.claude.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def locate_config() -> Path:
    """Resolve the Claude Code config path (env override wins, else ~/.claude.json)."""
    override = os.environ.get("CLAUDE_CONFIG_PATH")
    if override:
        return Path(override)
    return Path.home() / ".claude.json"


def read_config(path: Path) -> dict:
    """Read JSON config; tolerate a pre-existing BOM; empty/missing -> {}."""
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8-sig")
    return json.loads(text) if text.strip() else {}


def write_config(path: Path, data: dict) -> None:
    """Write JSON config as UTF-8 (no BOM) with a trailing newline."""
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def add_mcp_server(
    config: dict, name: str, command: str, args: list[str], env: dict | None = None
) -> dict:
    """Idempotently upsert an stdio MCP server entry keyed by name."""
    servers = config.setdefault("mcpServers", {})
    entry: dict = {"type": "stdio", "command": command, "args": list(args)}
    if env:
        entry["env"] = dict(env)
    servers[name] = entry
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Register an extra MCP server in the Claude Code config."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add-mcp", help="Register an MCP server")
    p.add_argument("--name", required=True)
    p.add_argument("--command", required=True)
    p.add_argument("--arg", action="append", default=[], dest="args")
    p.add_argument("--env", action="append", default=[], help="KEY=VALUE")
    p.add_argument("--dry-run", action="store_true")

    ns = parser.parse_args(argv)
    path = locate_config()
    config = read_config(path)

    if ns.cmd == "add-mcp":
        env = dict(kv.split("=", 1) for kv in ns.env)
        add_mcp_server(config, ns.name, ns.command, ns.args, env)

    if ns.dry_run:
        print(json.dumps(config, indent=2))
        return 0

    write_config(path, config)
    print(f"Updated {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
