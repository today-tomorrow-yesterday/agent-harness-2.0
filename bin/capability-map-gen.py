#!/usr/bin/env python3
"""capability-map-gen.py -- generate the skill-discovery map from this repo's own skills/.

WHY. A hand-written list of "when the user says X, suggest skill Y" covers a few skills on the
day it is written and falls further behind every time a skill is added -- a hand-maintained
index of a growing system is a drift generator by construction. This harvests the skills
themselves, mines trigger phrases from each skill's NAME and from any explicit trigger clause in
its frontmatter description ("Triggers on: ...", "Use when: ..."), and writes a Python module
that bin/hooks/capability-gate.py imports. Adding a skill adds its triggers on the next
regeneration -- no edit here.

PRECISION OVER RECALL. A discovery hint that fires on small talk gets muted, and muting is
invisible, which is worse than silence. So:
  * only the name and DECLARED trigger clauses are mined, never free description prose (an
    earlier version mined bigrams from whole descriptions and fired on "what time is it")
  * short fragments of compound names ("review" from safety-review) and words shared by 3+
    skills are pruned as ordinary vocabulary
  * a phrase claimed by exactly one skill -> a direct hint; by 2-4 skills -> one hint naming all
    of them; by 5+ -> dropped as generic
  * sort keys are TOTAL (they end with the phrase itself), so output never depends on
    PYTHONHASHSEED -- a generated file that churns without an input change makes its diffs
    meaningless
  * nothing is capped silently: discarded declared triggers are printed under [capped]

Skills switched off in settings.json (skillOverrides) are filtered at RUNTIME by the hook, not
here, so the generated file depends only on what is in the repo and is identical on every machine.

Usage:
    python bin/capability-map-gen.py            # report what it would emit
    python bin/capability-map-gen.py --write    # write bin/hooks/capability_map_generated.py
    python bin/capability-map-gen.py --check    # exit 1 if the committed map is stale
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path

BIN = Path(__file__).resolve().parent
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

OUT = BIN / "hooks" / "capability_map_generated.py"

GENERIC_MIN_SKILLS = 3   # a single-word trigger is kept only if fewer skills mention it
FRAGMENT_MIN_LEN = 9     # a compound-name fragment shorter than this is an ordinary word
                         # ("register" from domain-register; "authoring" survives)
MIN_TOKEN = 4            # a 3-letter token is almost never distinctive
MAX_PER_SKILL = 6        # so one verbose description cannot dominate the map
AMBIG_MAX = 4            # claimed by more skills than this -> generic, dropped
MESSAGE_MAX = 200

DROPPED: list[tuple[str, list[str], list[str]]] = []          # (skill, discarded, kept)
DROPPED_GENERIC: list[tuple[str, str, int]] = []

STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "when", "use",
    "using", "used", "your", "you", "our", "are", "was", "not", "any", "all",
    "can", "will", "how", "what", "which", "them", "they", "have", "has", "its",
    "it's", "one", "two", "new", "old", "get", "set", "run", "runs", "make",
    "makes", "made", "add", "adds", "also", "each", "every", "per", "via",
    "then", "than", "but", "out", "off", "own", "onto", "over", "under",
    "skill", "skills", "tool", "tools", "agent", "agents", "claude", "user",
    "file", "files", "content", "create", "created", "build", "building",
    "generate", "generated", "write", "writes", "read", "reads", "work",
    "works", "need", "needs", "want", "wants", "like", "just", "only", "more",
    "most", "some", "other", "same", "such", "before", "after", "based",
    "including", "includes", "across", "between", "about", "against", "full",
    "single", "multi", "one-off", "e.g", "i.e", "etc",
}

FRAGMENT = re.compile(r'[()\[\]<>"]|^-|-$')   # a sliced-out sentence piece, not a trigger

TRIGGER_CLAUSE = re.compile(
    r"(?:triggers?\s+on|triggers?\s*-|trigger\s+words?|fires?\s+on|actions?|use\s+when|invoke\s+when)"
    r"\s*:?\s*([^.]{4,240})",
    re.IGNORECASE,
)


def rank_key(p: str) -> tuple:
    """Bigrams first, then longer phrases, then alphabetical -- a TOTAL order."""
    return (" " not in p, -len(p), p)


def frontmatter(md: str) -> dict:
    """Parse the leading --- block. Deliberately minimal: top-level `key: value` only."""
    md = md.replace("\r\n", "\n").lstrip("﻿")
    if not md.startswith("---"):
        return {}
    end = md.find("\n---", 3)
    if end == -1:
        return {}
    out = {}
    for line in md[3:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def phrases(name: str, description: str) -> set[str]:
    """Candidate triggers from the skill NAME and any explicit trigger clause."""
    out: set[str] = set()
    parts = [p for p in re.split(r"[-_]", name.lower()) if p]
    if len(parts) > 1:
        out.add(" ".join(parts))          # "skill authoring"
    for p in parts:
        if len(p) >= MIN_TOKEN and p not in STOP:
            out.add(p)                    # "authoring"

    for m in TRIGGER_CLAUSE.finditer(description or ""):
        for raw in re.split(r"[,;/]| or | and ", m.group(1)):
            t = raw.strip().strip("\"'`*()[]").lower()
            t = re.sub(r"\s+", " ", t)
            if not (MIN_TOKEN <= len(t) <= 40):
                continue
            if t in STOP or all(w in STOP for w in t.split()):
                continue
            if len(t.split()) > 4:
                continue
            if FRAGMENT.search(t):
                continue
            out.add(t)
    return out


def prune_generic(per_skill: dict[str, set[str]], skills: list[dict],
                  min_skills: int = GENERIC_MIN_SKILLS,
                  fragment_min_len: int = FRAGMENT_MIN_LEN) -> list[tuple[str, str, int]]:
    """Drop single-word triggers that are ordinary vocabulary, not a skill's signature.

    "safety-review" yields "safety" and "review" -- everyday words, so the hint would fire on
    "review our nightly runs". Two tests, either drops:
      1. a SHORT fragment of a compound name (< fragment_min_len letters)
      2. a single token mentioned by `min_skills` or more skills
    A skill's own full name is never pruned (it is what a user types). Bigrams are never pruned.
    """
    texts = {sk["name"]: f'{sk["name"]} {sk["description"] or ""}'.lower().replace("-", " ")
             for sk in skills}
    dropped: list[tuple[str, str, int]] = []
    for name in sorted(per_skill):
        ps = per_skill[name]
        own = name.lower().replace("-", " ").replace("_", " ")
        parts = set(re.split(r"[-_]", name.lower()))
        for ph in sorted(ps):
            if " " in ph or ph == own or ph == name.lower():
                continue
            if ph in parts and len(parts) > 1 and len(ph) < fragment_min_len:
                ps.discard(ph)
                dropped.append((name, ph, 0))
                continue
            n = sum(1 for t in texts.values() if re.search(rf"\b{re.escape(ph)}\b", t))
            if n >= min_skills:
                ps.discard(ph)
                dropped.append((name, ph, n))
    return dropped


def first_sentence(desc: str) -> str:
    d = re.sub(r"\s+", " ", desc or "").strip()
    m = re.match(r"(.+?[.!?])(\s|$)", d)
    s = m.group(1) if m else d
    if len(s) > MESSAGE_MAX:
        s = s[:MESSAGE_MAX - 3].rsplit(" ", 1)[0] + "..."
    return s


def harvest_skills(roots=None) -> list[dict]:
    import skill_policy
    skills = []
    for root in (roots if roots is not None else skill_policy.owned_skill_roots()):
        root = Path(root)
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir(), key=lambda p: p.name):
            f = d / "SKILL.md"
            if d.is_dir() and not d.name.startswith("_") and f.is_file():
                fm = frontmatter(f.read_text(encoding="utf-8", errors="replace"))
                skills.append({"name": fm.get("name") or d.name,
                               "description": fm.get("description", "")})
    return skills


def _alts(ranked: list[str]) -> str:
    return "|".join(re.escape(p).replace(r"\ ", r"[\s-]+") for p in ranked)


def build(roots=None) -> dict:
    DROPPED.clear()
    skills = harvest_skills(roots)
    per_skill = {s["name"]: phrases(s["name"], s["description"]) for s in skills}
    DROPPED_GENERIC[:] = prune_generic(per_skill, skills)
    claims: Counter[str] = Counter()
    for ps in per_skill.values():
        claims.update(ps)

    entries = []
    # Band 1: a phrase only one skill claims -> a direct hint for that skill.
    for s in skills:
        uniq = sorted((p for p in per_skill[s["name"]] if claims[p] == 1), key=rank_key)
        if not uniq:
            continue
        ranked = uniq[:MAX_PER_SKILL]
        if len(uniq) > MAX_PER_SKILL:
            DROPPED.append((s["name"], uniq[MAX_PER_SKILL:], ranked))
        msg = f'/{s["name"]}'
        if first_sentence(s["description"]):
            msg += f' -- {first_sentence(s["description"])}'
        entries.append({"id": s["name"], "skills": [s["name"]],
                        "pattern": rf"\b(?:{_alts(ranked)})\b", "message": msg,
                        "triggers": ranked})

    # Band 2: a phrase 2..AMBIG_MAX skills claim -> one hint naming every candidate, so a
    # natural word routes to a short menu instead of to silence.
    contested: dict[str, list[str]] = {}
    for name in sorted(per_skill):
        for p in per_skill[name]:
            if 2 <= claims[p] <= AMBIG_MAX:
                contested.setdefault(p, []).append(name)
    by_group: dict[tuple[str, ...], list[str]] = {}
    for phrase, owners in contested.items():
        by_group.setdefault(tuple(sorted(owners)), []).append(phrase)
    for owners, ps in sorted(by_group.items()):
        ordered = sorted(ps, key=rank_key)
        ranked = ordered[:MAX_PER_SKILL]
        if len(ordered) > MAX_PER_SKILL:
            DROPPED.append(("+".join(owners), ordered[MAX_PER_SKILL:], ranked))
        entries.append({"id": "+".join(owners), "skills": list(owners),
                        "pattern": rf"\b(?:{_alts(ranked)})\b",
                        "message": ("Several skills cover this -- pick deliberately: "
                                    + ", ".join(f"/{o}" for o in owners)),
                        "triggers": ranked})

    return {"entries": entries, "skills_seen": len(skills),
            "dropped_generic": sum(1 for c in claims.values() if c > AMBIG_MAX)}


HEADER = '''"""capability_map_generated.py -- GENERATED by bin/capability-map-gen.py. Do not hand-edit.

Regenerate after adding, renaming or re-describing a skill:
    python bin/capability-map-gen.py --write

Built only from this repo's skills/ frontmatter, so it is identical on every machine.
Consumed by bin/hooks/capability-gate.py (UserPromptSubmit skill hints).
"""

# (id, skills, pattern, message)
GENERATED_CAPABILITY_MAP = [
'''


def render(b: dict) -> str:
    lines = [HEADER]
    for e in b["entries"]:
        lines.append(f"    ({e['id']!r}, {tuple(e['skills'])!r},\n"
                     f"     {e['pattern']!r},\n"
                     f"     {e['message']!r}),\n")
    lines.append("]\n")
    return "".join(lines)


def load_module(path: Path = OUT):
    spec = importlib.util.spec_from_file_location("capability_map_generated_check", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Generate the skill-discovery map.")
    ap.add_argument("--write", action="store_true", help="write the generated module")
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed map is stale")
    args = ap.parse_args(argv)

    b = build()
    text = render(b)

    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"STALE: {OUT.name} does not match skills/. Run: "
                  "python bin/capability-map-gen.py --write")
            return 1
        print(f"OK: {OUT.name} is current ({len(b['entries'])} entries)")
        return 0

    print(f"skills harvested : {b['skills_seen']}")
    print(f"entries          : {len(b['entries'])}")
    print(f"phrases dropped as generic ({AMBIG_MAX + 1}+ skills): {b['dropped_generic']}")
    for e in b["entries"]:
        print(f"  {e['id']:<34} {', '.join(e['triggers'])}")

    if args.write:
        OUT.write_bytes(text.encode("utf-8"))
        # Import it back: a generated module that does not import is a silent outage.
        mod = load_module()
        for _id, _skills, pat, _msg in mod.GENERATED_CAPABILITY_MAP:
            re.compile(pat, re.IGNORECASE)
        print(f"\nwrote {OUT} ({len(mod.GENERATED_CAPABILITY_MAP)} entries, re-imported, "
              "all patterns compile)")

    # NO SILENT CAPS: truncating without a word reads as "every trigger you declared landed".
    if DROPPED:
        total = sum(len(d) for _, d, _ in DROPPED)
        print(f"\n[capped] {total} declared trigger(s) discarded by MAX_PER_SKILL={MAX_PER_SKILL} "
              f"across {len(DROPPED)} skill(s). Name tokens consume slots too; to keep a specific "
              "phrase, shorten the trigger clause.")
        for name, dropped, kept in DROPPED:
            print(f"  {name}\n      kept    : {', '.join(kept)}\n      DROPPED : {', '.join(dropped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
