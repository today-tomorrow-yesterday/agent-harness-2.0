#!/usr/bin/env python3
"""add_project.py — manage the project taxonomy.

Auto-onboarding (Phase 4, 2026-05-28) gives new workspaces a deterministic
prefix the moment Claude Code first writes a session there. This script is
for the cases where you want to override that — pinning a curated pattern
to a chosen prefix, or renaming an auto-prefix to something better.

Subcommands:

  list
      Show the current taxonomy: jsonl_project_mapping (curated), all rows in
      project_registry (curated + auto-onboarded), and the transcript-count
      distribution. Read-only.

  add <PATTERN> <PREFIX> <LABEL>
      Add a curated pattern to config.yaml and immediately backfill any
      transcripts whose source_file contains PATTERN. Registers the prefix.
      Idempotent — updating an existing pattern is fine.

  rename <OLD_PREFIX> <NEW_PREFIX> [--label "..."] [--pattern "..."]
      Rename a prefix everywhere it appears. Updates transcripts, sys_sessions,
      tool_results, facts (with safe merge on UNIQUE(project, category, key)
      collisions), decisions, and project_registry. If --pattern is supplied,
      also adds a config.yaml entry pinning that pattern to the new prefix.

Usage examples:
  python scripts/add_project.py list
  python scripts/add_project.py add "Z--MyNewProject" mnp "My New Project"
  python scripts/add_project.py rename npf np --label "New Project" --pattern "Z--NewProject"
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import pathlib
import re
import sqlite3
import sys

# Force UTF-8 stdout on Windows — the script uses arrow glyphs (->) that older
# code-pages can't encode. Same pattern as brain_health.py.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import yaml

ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)

from lib.project_detect import RESERVED_PREFIXES  # noqa: E402


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config() -> tuple[dict, str]:
    config_path = os.path.join(ROOT, "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f), config_path


def save_config(config: dict, config_path: str) -> None:
    """Atomic write: write to a sibling .tmp and rename."""
    tmp = config_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, config_path)


def connect_db(config: dict) -> sqlite3.Connection:
    db_path = config["storage"]["local_db_path"]
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def cmd_list(args) -> int:
    config, _ = load_config()
    mappings = config.get("jsonl_project_mapping", {}) or {}
    conn = connect_db(config)
    try:
        print("=== Curated jsonl_project_mapping (config.yaml) ===")
        if not mappings:
            print("  (empty)")
        else:
            for pat, prefix in sorted(mappings.items(), key=lambda x: -len(x[0])):
                print(f"  {pat:>28s}  →  {prefix}")

        print("\n=== project_registry ===")
        for r in conn.execute(
            "SELECT prefix, folder_name, label, status FROM project_registry ORDER BY prefix"
        ).fetchall():
            stat = f" [{r['status']}]" if r["status"] and r["status"] != "active" else ""
            print(f"  {r['prefix']:>6s}  {r['folder_name']:>22s}  {r['label']}{stat}")

        print("\n=== Distribution (transcripts) ===")
        for r in conn.execute(
            "SELECT project, COUNT(*) c FROM transcripts GROUP BY project ORDER BY c DESC"
        ).fetchall():
            print(f"  {r['project']:>6s}  {r['c']:>8,}")
    finally:
        conn.close()
    return 0


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

def cmd_add(args) -> int:
    pattern = args.pattern
    prefix = args.prefix
    label = args.label

    if prefix in RESERVED_PREFIXES:
        print(f"ERROR: '{prefix}' is reserved. Pick a different prefix.", file=sys.stderr)
        return 1

    config, config_path = load_config()
    mappings = config.setdefault("jsonl_project_mapping", {}) or {}

    # If the pattern already exists, allow re-pointing it.
    existing_prefix = mappings.get(pattern)
    if existing_prefix and existing_prefix != prefix:
        print(f"NOTE: pattern '{pattern}' was '{existing_prefix}'; re-pointing to '{prefix}'.")
    mappings[pattern] = prefix

    # Also add a projects: entry if missing.
    projects = config.setdefault("projects", [])
    if not any(p.get("prefix") == prefix for p in projects):
        projects.append({"folder_name": _slug(label), "prefix": prefix, "label": label})

    save_config(config, config_path)
    print(f"config.yaml updated: '{pattern}' → '{prefix}'")

    # Backfill in the DB.
    conn = connect_db(config)
    try:
        n_tx = conn.execute(
            "UPDATE transcripts SET project = ? "
            "WHERE source_file LIKE ? COLLATE NOCASE",
            (prefix, f"%{pattern}%"),
        ).rowcount
        print(f"Re-classified {n_tx:,} transcripts to '{prefix}'.")

        _cascade_session_aggregates(conn)

        conn.execute(
            """INSERT INTO project_registry
               (folder_name, prefix, label, registered_at, status, health)
               VALUES (?, ?, ?, ?, 'active', 'green')
               ON CONFLICT(folder_name) DO UPDATE SET
                   prefix = excluded.prefix,
                   label  = excluded.label,
                   status = 'active'""",
            (_slug(label), prefix, label, _now()),
        )
        conn.commit()
        print(f"project_registry: '{prefix}' / '{label}' registered.")
    finally:
        conn.close()
    return 0


def _slug(label: str) -> str:
    """Compress a label into a folder_name-style slug."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", label.lower()).strip("-")
    return s or "untitled"


def _cascade_session_aggregates(conn: sqlite3.Connection) -> None:
    """After re-classifying transcripts, propagate project to sys_sessions,
    tool_results, facts, decisions. Uses the most-common-project per session."""
    conn.execute(
        """UPDATE sys_sessions
              SET project = (
                  SELECT t.project FROM transcripts t
                  WHERE t.session_id = sys_sessions.session_id
                  GROUP BY t.project ORDER BY COUNT(*) DESC LIMIT 1
              )
            WHERE EXISTS (SELECT 1 FROM transcripts t
                          WHERE t.session_id = sys_sessions.session_id)"""
    )
    conn.execute(
        """UPDATE tool_results
              SET project = (SELECT project FROM sys_sessions
                             WHERE session_id = tool_results.session_id)
            WHERE EXISTS (SELECT 1 FROM sys_sessions
                          WHERE session_id = tool_results.session_id)"""
    )


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

def cmd_rename(args) -> int:
    old = args.old
    new = args.new
    if new in RESERVED_PREFIXES:
        print(f"ERROR: '{new}' is reserved.", file=sys.stderr)
        return 1
    if old == new:
        print("Nothing to do — old and new prefixes are the same.")
        return 0

    config, config_path = load_config()
    conn = connect_db(config)

    try:
        # Sanity check: does `old` actually exist anywhere?
        c_tx = conn.execute("SELECT COUNT(*) FROM transcripts WHERE project = ?", (old,)).fetchone()[0]
        c_reg = conn.execute("SELECT COUNT(*) FROM project_registry WHERE prefix = ?", (old,)).fetchone()[0]
        if c_tx == 0 and c_reg == 0:
            print(f"WARNING: no transcripts or registry rows use '{old}'. Nothing to rename.", file=sys.stderr)
            return 1

        # Resolve fact collisions BEFORE the UPDATE — facts has UNIQUE(project, category, key).
        # Strategy: where (old, cat, key) and (new, cat, key) both exist, keep the newer
        # (by updated_at) and delete the loser.
        merged_facts = conn.execute(
            """SELECT f_old.id AS old_id, f_old.updated_at AS old_ts,
                      f_new.id AS new_id, f_new.updated_at AS new_ts,
                      f_old.category, f_old.key
                 FROM facts f_old
                 JOIN facts f_new
                   ON f_new.project = ?
                  AND f_new.category = f_old.category
                  AND f_new.key      = f_old.key
                WHERE f_old.project = ?""",
            (new, old),
        ).fetchall()
        for r in merged_facts:
            old_id, old_ts, new_id, new_ts = r["old_id"], r["old_ts"] or "", r["new_id"], r["new_ts"] or ""
            loser_id = old_id if old_ts <= new_ts else new_id
            # Free the loser slot before the bulk UPDATE collides.
            conn.execute("DELETE FROM facts WHERE id = ?", (loser_id,))
        if merged_facts:
            print(f"Merged {len(merged_facts)} colliding facts (kept newer per (category, key)).")

        # Same merge logic for decisions on UNIQUE(project, decision_number).
        merged_dec = conn.execute(
            """SELECT d_old.id AS old_id, d_old.created_at AS old_ts,
                      d_new.id AS new_id, d_new.created_at AS new_ts
                 FROM decisions d_old
                 JOIN decisions d_new
                   ON d_new.project = ?
                  AND d_new.decision_number = d_old.decision_number
                WHERE d_old.project = ?""",
            (new, old),
        ).fetchall()
        for r in merged_dec:
            old_id, old_ts, new_id, new_ts = r["old_id"], r["old_ts"] or "", r["new_id"], r["new_ts"] or ""
            loser_id = old_id if old_ts <= new_ts else new_id
            conn.execute("DELETE FROM decisions WHERE id = ?", (loser_id,))
        if merged_dec:
            print(f"Merged {len(merged_dec)} colliding decisions (kept newer per decision_number).")

        # Bulk update everything.
        targets = [
            ("transcripts",      "UPDATE transcripts      SET project = ? WHERE project = ?"),
            ("sys_sessions",     "UPDATE sys_sessions     SET project = ? WHERE project = ?"),
            ("tool_results",     "UPDATE tool_results     SET project = ? WHERE project = ?"),
            ("facts",            "UPDATE facts            SET project = ? WHERE project = ?"),
            ("decisions",        "UPDATE decisions        SET project = ? WHERE project = ?"),
            ("project_registry", "UPDATE project_registry SET prefix  = ? WHERE prefix  = ?"),
        ]
        for name, sql in targets:
            n = conn.execute(sql, (new, old)).rowcount
            print(f"  {name:>18s}: {n:>5d} row(s) updated")

        # Optional: update label on the registry row + add a config.yaml pattern.
        if args.label:
            conn.execute(
                "UPDATE project_registry SET label = ?, status = 'active' WHERE prefix = ?",
                (args.label, new),
            )
        if args.pattern:
            mappings = config.setdefault("jsonl_project_mapping", {}) or {}
            mappings[args.pattern] = new
            save_config(config, config_path)
            print(f"config.yaml: pinned pattern '{args.pattern}' → '{new}'")

        conn.commit()
        print(f"Renamed '{old}' → '{new}' across all tables.")
    finally:
        conn.close()
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="add_project",
        description="Manage the claude-brain project taxonomy (curated patterns + auto-onboarded prefixes).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Show current taxonomy")

    p_add = sub.add_parser("add", help="Add a curated pattern (or update an existing one)")
    p_add.add_argument("pattern", help="Substring to match in JSONL source paths, e.g. 'Z--MyProject'")
    p_add.add_argument("prefix",  help="Short prefix, 2-4 chars, e.g. 'mp'")
    p_add.add_argument("label",   help="Human-readable label, e.g. 'My Project'")

    p_ren = sub.add_parser("rename", help="Rename an existing prefix everywhere it appears")
    p_ren.add_argument("old", help="Current prefix")
    p_ren.add_argument("new", help="New prefix")
    p_ren.add_argument("--label", help="Updated label (optional)")
    p_ren.add_argument("--pattern", help="If supplied, also pin this pattern → new prefix in config.yaml")

    args = parser.parse_args()
    return {"list": cmd_list, "add": cmd_add, "rename": cmd_rename}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
