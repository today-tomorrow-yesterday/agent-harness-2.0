"""project_detect.py — project-prefix resolution + auto-onboarding.

The flow:
  1. Try explicit patterns from `config.yaml::jsonl_project_mapping` (longest-first,
     case-insensitive substring match against the JSONL source path AND the cwd).
  2. If no pattern matches, derive a clean 2-4 char prefix deterministically
     from the encoded workspace folder (e.g. `Z--NewProjectFoo` → `npf`).
  3. The caller is responsible for INSERTing into `project_registry` (with
     status='auto-onboarded') so the prefix appears in `get_status` and the
     auto-onboard surface in `brain_health.py`.

Deterministic by design — the same path always yields the same prefix, so two
concurrent hook spawns never disagree.

Renaming an auto-prefix to a curated one: `scripts/add_project.py rename ...`.
"""
from __future__ import annotations

import re
from typing import Iterable

# Prefixes the resolver will never auto-assign (reserved for the curated
# taxonomy and for clearly-uncategorizable fallbacks).
RESERVED_PREFIXES: set[str] = {"oth", "gen", "unk"}

# Leading drive-code in Claude Code's encoded folder names: 'X--', 'C--', 'Z--'.
# Single uppercase letter (drive letter) followed by '--' (':' → '-', '\' → '-').
_DRIVE_RE = re.compile(r"^[A-Z]--")

# Find a `/projects/<workspace>/` segment in a normalized path.
_WORKSPACE_RE = re.compile(r"/projects/([^/]+)/")

# Split CamelCase into kebab-case for tokenization
# (`NewProjectFoo` → ['new','project','foo']).
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")


def extract_workspace(source_file: str | None) -> str | None:
    """Return the encoded workspace folder name from a JSONL `source_file`.

    `C:\\Users\\trerh\\.claude-udig\\projects\\X--SES-Legacy\\<uuid>.jsonl`
        → `'X--SES-Legacy'`
    Sub-agent paths still resolve to the parent workspace.
    Returns None if the path doesn't look like a Claude Code projects path.
    """
    if not source_file:
        return None
    norm = source_file.replace("\\", "/")
    m = _WORKSPACE_RE.search(norm)
    return m.group(1) if m else None


def encoded_to_tokens(encoded: str) -> list[str]:
    """Tokenize an encoded workspace name for prefix derivation.

    Strips the leading drive code, splits on hyphens AND underscores, further
    splits each part on CamelCase boundaries, lowercases everything. Pure-digit
    tokens are preserved (don't filter `223` from `SES-223-MM-template`) but
    de-prioritized when picking initials.
    """
    s = _DRIVE_RE.sub("", encoded or "")
    # Split on hyphens AND underscores in one pass.
    parts = re.split(r"[-_]+", s)
    tokens: list[str] = []
    for p in parts:
        for sub in _CAMEL_BOUNDARY_RE.split(p):
            sub = sub.strip().lower()
            if sub:
                tokens.append(sub)
    return tokens


def auto_prefix(encoded: str, taken: Iterable[str]) -> str:
    """Derive a stable 2-4 char prefix from an encoded workspace folder.

    Strategy:
      - 0 tokens (just a drive code or empty) → 'unk'
      - 1 token → first 3 chars of that token
      - 2+ tokens → first letter of up to four non-numeric tokens
    Collisions with `taken` or `RESERVED_PREFIXES` resolve by appending a digit.
    """
    taken_set: set[str] = set(taken) | RESERVED_PREFIXES

    tokens = encoded_to_tokens(encoded)
    if not tokens:
        base = "unk"
    elif len(tokens) == 1:
        base = tokens[0][:3] or "unk"
    else:
        # Prefer non-digit tokens for initials. If all are digits, fall back
        # to the first 3 chars of the joined name.
        letter_tokens = [t for t in tokens if not t.isdigit()]
        if letter_tokens:
            base = "".join(t[0] for t in letter_tokens[:4])
        else:
            base = ("".join(tokens))[:3] or "unk"

    if base in taken_set:
        i = 2
        while f"{base}{i}" in taken_set:
            i += 1
        return f"{base}{i}"
    return base


def resolve_project(
    jsonl_path: str,
    cwd: str | None,
    mappings: dict | list[tuple[str, str]],
    taken_prefixes: Iterable[str] = (),
) -> tuple[str, str, str | None]:
    """Resolve a JSONL source path to (prefix, source, workspace).

    Args:
      jsonl_path: full path to the JSONL file (source_file).
      cwd: working directory from the JSONL data (live writer path); may be None.
      mappings: `jsonl_project_mapping` dict from config.yaml, OR an already-sorted list.
      taken_prefixes: prefixes already in use (e.g. all values of mappings + any
        existing project_registry rows). Used only when auto-deriving.

    Returns a tuple:
      prefix:    str — the resolved prefix (always present).
      source:    'config' | 'auto' | 'fallback' — where the prefix came from.
      workspace: str | None — the encoded workspace folder name (None if not extractable;
                 used by the caller to write the project_registry row when source == 'auto').
    """
    # Normalize mappings to a longest-first list of (pattern, prefix).
    if isinstance(mappings, dict):
        sorted_mappings = sorted(mappings.items(), key=lambda x: len(x[0]), reverse=True)
    else:
        sorted_mappings = sorted(list(mappings), key=lambda x: len(x[0]), reverse=True)

    norm_path = (jsonl_path or "").replace("\\", "/").lower()
    for pattern, prefix in sorted_mappings:
        if pattern.lower() in norm_path:
            return prefix, "config", None

    if cwd:
        norm_cwd = cwd.replace("\\", "/").lower()
        for pattern, prefix in sorted_mappings:
            if pattern.lower() in norm_cwd:
                return prefix, "config", None

    # No explicit pattern matched — auto-derive.
    ws = extract_workspace(jsonl_path)
    if ws:
        all_taken = set(taken_prefixes) | {p for _, p in sorted_mappings}
        return auto_prefix(ws, all_taken), "auto", ws

    return "oth", "fallback", None


def ensure_registry_row(conn, prefix: str, workspace: str | None,
                        status: str = "auto-onboarded") -> None:
    """Idempotent INSERT into project_registry for an auto-onboarded workspace.

    folder_name is the encoded workspace name (e.g. 'Z--NewProjectFoo') so a
    single curated prefix (like 'ses') can still cover multiple encoded
    workspaces (X--SES, X--SES-Legacy, X--SES-223-MM-template, ...) without
    primary-key collision.

    Safe to call on every write — no-op when the row already exists.
    """
    import datetime as _dt
    if not workspace:
        return
    label = f"Auto-onboarded: {workspace}"
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        conn.execute(
            """INSERT OR IGNORE INTO project_registry
               (folder_name, prefix, label, registered_at, status, health)
               VALUES (?, ?, ?, ?, ?, 'green')""",
            (workspace, prefix, label, now, status),
        )
    except Exception:
        # Don't let a registry write failure break the live transcript write.
        pass
