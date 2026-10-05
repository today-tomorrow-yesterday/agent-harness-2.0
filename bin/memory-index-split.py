#!/usr/bin/env python3
"""memory-index-split.py — turn an oversized memory/MEMORY.md into a small router + section files.

WHY
The memory index is the one file every session is told to read first. Once it grows past what a
single Read returns (a few hundred lines / tens of thousands of tokens), the read truncates and
the tail of the index is never seen — and nothing reports the cut. Entries near the bottom behave
as if they did not exist: an earlier session spent several turns rediscovering a tool by searching
the filesystem when it was indexed all along, just past the truncation point. An index whose job
is discovery must fit inside the window that reads it.

This script splits the index at its `## ` headings: each section moves verbatim into
`memory/_index/<section>.md`, and MEMORY.md becomes a short router that links to them with a
one-line blurb and an entry count each.

THE ONE RULE IT OBEYS: NOTHING IS SUMMARISED, REWRITTEN OR DROPPED
Every line of the original lands in exactly one output file. Before writing, the script
reassembles its outputs and compares them with the original; if a single line is unaccounted for
it REFUSES TO WRITE. After writing, it checks every bullet is still on disk and restores the backup
if any is missing. A lossy refactor of memory is not an acceptable outcome at any token saving.

The single deliberate change: relative links inside the moved sections get one extra `../`,
because the section files live one directory deeper. (Missing this on a first attempt silently
broke every relative link in the moved sections — the "fixed" index pointed at nothing.)

Usage:
    python bin/memory-index-split.py                  # dry run + conservation proof
    python bin/memory-index-split.py --apply
    python bin/memory-index-split.py --memory-dir path/to/memory --apply
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MEMORY = REPO / "memory"
SECTION_DIR = "_index"
ROUTER_MARKER = "## Sections"

# Heading prefix (as written, minus `#`, backticks and asterisks) -> (filename, router blurb).
# Unlisted headings fall back to a slug of the heading with the heading itself as the blurb.
ROUTE = {
    "Top-level":        ("top-level.md",     "identity and the always-on files"),
    "Behavioral rules": ("feedback.md",      "standing rules that apply everywhere"),
    "Feedback":         ("feedback.md",      "standing rules that apply everywhere"),
    "User":             ("user.md",          "who the user is and how they work"),
    "Active projects":  ("projects.md",      "live project briefs"),
    "Projects":         ("projects.md",      "live project briefs"),
    "Ideas":            ("ideas.md",         "concepts that are not yet projects"),
    "Reference":        ("reference.md",     "external tools, benchmarks, stacks"),
    "Archive":          ("archive.md",       "superseded; do not load by default"),
    "When in doubt":    ("when-in-doubt.md", "the tie-breaker rules"),
}

REL_LINK = re.compile(r"\]\((?!https?://|mailto:|#|/)([^)]+)\)")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def heading_title(heading: str) -> str:
    return re.sub(r"[`*]", "", heading[3:]).strip()


def route_for(heading: str, taken: set[str] | None = None) -> tuple[str, str]:
    plain = heading_title(heading)
    fname, blurb = None, plain
    for key, val in ROUTE.items():
        if plain.lower().startswith(key.lower()):
            fname, blurb = val
            break
    if fname is None:
        slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-") or "misc"
        fname = f"{slug}.md"
    # Two headings mapping to one file would overwrite each other: lossy. Disambiguate.
    if taken is not None:
        base, n = fname[:-3], 2
        while fname in taken:
            fname = f"{base}-{n}.md"
            n += 1
        taken.add(fname)
    return fname, blurb


def is_router(text: str) -> bool:
    return f"]({SECTION_DIR}/" in text and ROUTER_MARKER in text


def parse(text: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """(preamble lines, [(heading, body lines)]) — split on `## ` outside fenced code."""
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    cur: list[str] | None = None
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if line.startswith("## ") and not in_fence:
            sections.append((line, []))
            cur = sections[-1][1]
        elif cur is None:
            preamble.append(line)
        else:
            cur.append(line)
    return preamble, sections


def conserved(original: str, preamble: list[str], sections) -> bool:
    reassembled = list(preamble)
    for h, body in sections:
        reassembled.append(h)
        reassembled.extend(body)
    return reassembled == original.splitlines()


def rebase_links(line: str) -> str:
    return REL_LINK.sub(lambda m: "](../" + m.group(1) + ")", line)


def split(text: str) -> tuple[str, dict[str, str], list[tuple[str, int, int]]]:
    """Pure: (router text, {filename: section text}, [(filename, lines, entries)])."""
    preamble, sections = parse(text)
    if not conserved(text, preamble, sections):
        raise ValueError("reassembly does not equal the original")
    files: dict[str, str] = {}
    stats: list[tuple[str, int, int]] = []
    router = list(preamble)
    while router and not router[-1].strip():
        router.pop()
    router += ["", ROUTER_MARKER, "",
               "This index is a ROUTER, kept small on purpose so a single read always reaches the",
               "end. Each section below holds its original entries verbatim; load the one you need.",
               ""]
    taken: set[str] = set()
    for h, body in sections:
        fname, blurb = route_for(h, taken)
        title = heading_title(h)
        entries = sum(1 for b in body if b.lstrip().startswith("- "))
        moved = [rebase_links(b) for b in body]
        files[fname] = "\n".join([f"# {title}", "", *moved]).rstrip() + "\n"
        router.append(f"- [{title}]({SECTION_DIR}/{fname}) — {blurb} · {entries} entries")
        stats.append((fname, len(body), entries))
    router += ["", "> Nothing was summarised or removed when this index was split; every entry",
               "> lives, verbatim, in the section file it is routed to.", ""]
    return "\n".join(router).rstrip() + "\n", files, stats


def bullets_missing(original: str, router: str, files: dict[str, str]) -> list[str]:
    def norm(s: str) -> str:
        return s.replace("](../", "](")
    corpus = norm(router + "".join(files.values()))
    return [line for line in original.splitlines()
            if line.lstrip().startswith("- ") and norm(line.strip()) not in corpus]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Split MEMORY.md into a router + section files.")
    ap.add_argument("--memory-dir", default=str(DEFAULT_MEMORY))
    ap.add_argument("--apply", action="store_true", help="write the files (default: dry run)")
    args = ap.parse_args(argv)

    mem = Path(args.memory_dir).expanduser()
    index = mem / "MEMORY.md"
    if not index.is_file():
        print(f"no index at {index}", file=sys.stderr)
        return 2
    original = index.read_text(encoding="utf-8")

    # IDEMPOTENCY GUARD. After a split, MEMORY.md IS the router; splitting it again would treat
    # the router as the source and shred the index. A destructive no-op is the worst kind.
    if is_router(original):
        print("MEMORY.md is already a router. Nothing to do.")
        print("To re-split, restore MEMORY.md.bak-presplit first.")
        return 0

    try:
        router, files, stats = split(original)
    except ValueError as e:
        print(f"REFUSING: {e}. No files written.", file=sys.stderr)
        return 1

    lines = original.splitlines()
    print(f"original lines : {len(lines)}")
    print(f"sections       : {len(stats)}")
    print("conservation   : EXACT (reassembly == original)\n")
    for fname, n_lines, n_entries in stats:
        print(f"  {fname:<22} {n_lines:>4} lines, {n_entries:>3} entries")
    print(f"\nrouter size    : {len(router)} chars (~{int(len(router) / 3.6):,} tokens), "
          f"{len(router.splitlines())} lines")

    if not args.apply:
        print("\nDRY RUN: nothing written. Re-run with --apply.")
        return 0

    backup = index.with_suffix(".md.bak-presplit")
    shutil.copy2(index, backup)
    sect = mem / SECTION_DIR
    sect.mkdir(parents=True, exist_ok=True)
    for fname, text in files.items():
        (sect / fname).write_text(text, encoding="utf-8", newline="\n")
    index.write_text(router, encoding="utf-8", newline="\n")

    on_disk = {f: (sect / f).read_text(encoding="utf-8") for f in files}
    missing = bullets_missing(original, index.read_text(encoding="utf-8"), on_disk)
    print(f"\nwrote router + {len(files)} section files under {sect}")
    if missing:
        print(f"CONTENT LOST ({len(missing)} bullets): restoring the backup", file=sys.stderr)
        shutil.copy2(backup, index)
        for f in files:
            (sect / f).unlink(missing_ok=True)
        return 1
    print("verified: no entry lost.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
