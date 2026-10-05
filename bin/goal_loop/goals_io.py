"""Parse / serialize / load / save memory/goals.md.

Lossless markdown I/O. goals.md is authored by hand with rich, multi-line goal
bodies (checklists, research notes, prose). The Goal Loop only mutates two fields
programmatically (research_notes, open_questions), so serialization PRESERVES each
goal's raw body verbatim and surgically patches just those two fields. This avoids
the old failure mode where serialize() rebuilt goals.md from flat fields and (a)
dropped all multi-line content and (b) mis-read '## 1.'-style content headers as
phantom goals.
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path

_LIST_KEYS = {"repos", "open_questions"}
_FIELD_KEYS = ("outcome", "success_signal", "status", "last_moved", "next_step",
               "repos", "research_notes", "open_questions")

# Only headers of the form '## G<number> — Title' are goals. A '## 1. ...' line
# inside a goal's prose is body content, NOT a new goal.
_GOAL_HEADER_RE = re.compile(r"(?m)^##[ \t]+(G\d+)[ \t]*—[ \t]*(.*)$")
_FIELD_LINE_RE = re.compile(r"^\s*-\s*([a-z_]+):\s*(.*)$")
# The first top-level section the serializer owns. Everything above it (frontmatter,
# a how-to note) is the file's PREAMBLE and is written back verbatim.
_NORTH_STAR_RE = re.compile(r"(?m)^#[ \t]*North Star[ \t]*$")

# A goals.md that still carries this marker is the unfilled template shipped with the
# repo. The marker sits on the BOOTSTRAP block the user deletes when they fill the
# file in, so the loop never assesses, researches or rewrites placeholder goals.
TEMPLATE_MARKER = "goal-loop:template"


def _parse_list(raw: str) -> list[str]:
    """Read a list field. JSON is the canonical encoding; bare comma-joined is legacy.

    The old encoding was a bare `[a, b]` split on commas, which silently shredded
    every value CONTAINING a comma — and the Goal Loop's own generated questions all
    do (questions.py emits "... — kill it, or what's the ONE next shippable step?").
    One question round-tripped as two. JSON escapes commas and brackets, so the
    parsed data now round-trips, not just the file text.
    """
    raw = raw.strip()
    if not raw:
        return []
    try:
        val = json.loads(raw)
    except ValueError:
        pass
    else:
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
    # Legacy fallback. Strip ONE bracket pair, not every trailing bracket:
    # raw.strip("[]") ate both closing brackets of a value ending in a [[wikilink]].
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1].strip()
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else []


def _parse_value(key: str, raw: str):
    raw = raw.strip()
    if key in _LIST_KEYS:
        return _parse_list(raw)
    return raw


def _new_goal(gid: str, title: str) -> dict:
    return {"id": gid, "title": title, "outcome": "", "success_signal": "",
            "status": "", "last_moved": "", "next_step": "", "repos": [],
            "research_notes": "", "open_questions": [], "_body": ""}


def is_unfilled_template(text: str) -> bool:
    """True while goals.md is still the shipped template (see TEMPLATE_MARKER)."""
    return TEMPLATE_MARKER in (text or "")


def _preamble(text: str, headers: list) -> str:
    """Text above the first section the serializer owns (North Star or a goal)."""
    cut = len(text)
    m = _NORTH_STAR_RE.search(text)
    if m:
        cut = m.start()
    if headers:
        cut = min(cut, headers[0].start())
    return text[:cut].strip("\n") if cut < len(text) else ""


def parse_goals(text: str) -> dict:
    north = ""
    m = re.search(r"#\s*North Star\s*\n(.+?)(?:\n#|\Z)", text, re.S)
    if m:
        north = m.group(1).strip()

    goals = []
    headers = list(_GOAL_HEADER_RE.finditer(text))
    for i, h in enumerate(headers):
        gid, title = h.group(1).strip(), h.group(2).strip()
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end].strip("\n")
        g = _new_goal(gid, title)
        g["_body"] = body
        for line in body.splitlines():
            lm = _FIELD_LINE_RE.match(line)
            if lm and lm.group(1) in _FIELD_KEYS:
                g[lm.group(1)] = _parse_value(lm.group(1), lm.group(2))
        goals.append(g)
    return {"north_star": north, "goals": goals, "preamble": _preamble(text, headers)}


def _fmt(key: str, value) -> str:
    if key in _LIST_KEYS:
        # JSON, so a value containing a comma or a bracket survives the round trip.
        return json.dumps([str(x) for x in (value or [])], ensure_ascii=False)
    return (value or "").replace("\r", " ").replace("\n", " ").strip()


def _body_field_value(body: str, key: str):
    for line in body.splitlines():
        lm = _FIELD_LINE_RE.match(line)
        if lm and lm.group(1) == key:
            return _parse_value(key, lm.group(2))
    return None


def _patch_field(lines: list[str], key: str, new_line: str) -> list[str]:
    """Replace the '- key: ...' line AND its continuation lines with one canonical
    line. Append if the field is absent.

    A value's continuation is every following line up to (not including) the next
    field line or the first blank line. Indentation is NOT the test, which is what
    this used to use: a value whose second line was un-indented had only its FIRST
    line replaced, and lines 2..N were orphaned into the goal body as free-standing
    prose owned by no field. For research_notes that orphan is fetched web content
    that loses the UNTRUSTED fences research.py guarantees it carries, so an
    unattended reader sees web text as trusted memory.

    The blank-line stop is deliberate and conservative: a prose block separated from
    the field list by a blank line is goal body, not a runaway value, and must not be
    swallowed. Trading a rewritten field for deleted hand-authored content is a worse
    bug than the one being fixed.
    """
    out, i, n, done = [], 0, len(lines), False
    while i < n:
        lm = _FIELD_LINE_RE.match(lines[i])
        if not done and lm and lm.group(1) == key:
            out.append(new_line)
            i += 1
            while i < n and lines[i].strip() and not _FIELD_LINE_RE.match(lines[i]):
                i += 1
            done = True
            continue
        out.append(lines[i])
        i += 1
    if not done:
        out.append(new_line)
    return out


def _sync_body(body: str, g: dict) -> str:
    lines = body.split("\n")
    # open_questions is always a single canonical line — safe to rewrite every time.
    lines = _patch_field(lines, "open_questions",
                         f"- open_questions: {_fmt('open_questions', g.get('open_questions', []))}")
    # research_notes: only rewrite if the loop actually changed it, so hand-written
    # multi-line notes are preserved untouched.
    if (g.get("research_notes", "") or "").strip() != ((_body_field_value(body, "research_notes") or "")).strip():
        lines = _patch_field(lines, "research_notes",
                             f"- research_notes: {_fmt('research_notes', g.get('research_notes', ''))}")
    return "\n".join(lines)


def _canonical_body(g: dict) -> str:
    return "\n".join(f"- {k}: {_fmt(k, g.get(k, [] if k in _LIST_KEYS else ''))}"
                     for k in _FIELD_KEYS)


def serialize_goals(doc: dict) -> str:
    out = []
    preamble = (doc.get("preamble") or "").strip("\n")
    if preamble:
        # Frontmatter and any guidance above "# North Star" survive a rewrite; without
        # this the first save silently dropped them.
        out.append(preamble + "\n")
    out += [f"# North Star\n{doc.get('north_star', '').strip()}\n", "# Active Goals\n"]
    for g in doc["goals"]:
        body = g.get("_body")
        body = _sync_body(body, g) if body else _canonical_body(g)
        out.append(f"## {g['id']} — {g['title']}")
        out.append(body)
        out.append("")
    return "\n".join(out) + "\n"


def is_paused(goal: dict) -> bool:
    """A goal the user has deliberately set aside: `- status: paused ...`.

    Paused is not stalled. A stalled goal is one nobody decided about, and the loop
    asks "kill it, or what's the ONE next step?" every week. A paused goal HAS been
    decided, so asking again is noise — it gets no verdict, no question, no research
    fetch and no recommended action until its status changes. The goal and all its
    notes stay in goals.md untouched.
    """
    return (goal.get("status") or "").strip().lower().startswith("paused")


def active_goals(goals: list[dict]) -> list[dict]:
    return [g for g in goals if not is_paused(g)]


def load(path) -> dict:
    return parse_goals(Path(path).read_text(encoding="utf-8"))


def save(path, doc: dict) -> None:
    """ATOMIC full-rewrite of goals.md (tmp + os.replace), utf-8, no BOM.

    Atomicity is load-bearing, not hygiene: goals.md is HAND-AUTHORED (rich multi-line
    bodies that cannot be regenerated), this is a full rewrite of all of it, and a caller
    on a scheduler runs under an execution time limit with a long claude call inside the
    same run. A plain write_text() truncates the file first, so a
    kill mid-write left a truncated or empty goals.md with no copy anywhere. tmp + os.replace
    is atomic on one filesystem: readers see either the whole old file or the whole new one.
    """
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(serialize_goals(doc), encoding="utf-8")
        os.replace(tmp, path)          # atomic same-filesystem swap
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()           # never leave a stray .tmp behind
        except OSError:
            pass
        raise
