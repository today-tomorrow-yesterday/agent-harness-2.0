"""Parse / serialize / load / save memory/goals.md. Pure markdown I/O."""
from __future__ import annotations
import re
from pathlib import Path

_LIST_KEYS = {"repos", "open_questions"}


def _parse_value(key: str, raw: str):
    raw = raw.strip()
    if key in _LIST_KEYS:
        inner = raw.strip("[]").strip()
        return [x.strip() for x in inner.split(",") if x.strip()] if inner else []
    return raw


def parse_goals(text: str) -> dict:
    north = ""
    m = re.search(r"#\s*North Star\s*\n(.+?)(?:\n#|\Z)", text, re.S)
    if m:
        north = m.group(1).strip()
    goals = []
    for blk in re.split(r"\n##\s+", text)[1:]:
        head, *rest = blk.splitlines()
        gid, _, title = head.partition("—")
        g = {"id": gid.strip(), "title": title.strip(), "outcome": "", "success_signal": "",
             "status": "", "last_moved": "", "next_step": "", "repos": [],
             "research_notes": "", "open_questions": []}
        for line in rest:
            lm = re.match(r"\s*-\s*([a-z_]+):\s*(.*)", line)
            if lm and lm.group(1) in g:
                g[lm.group(1)] = _parse_value(lm.group(1), lm.group(2))
        goals.append(g)
    return {"north_star": north, "goals": goals}


def serialize_goals(doc: dict) -> str:
    out = [f"# North Star\n{doc.get('north_star','').strip()}\n", "# Active Goals\n"]
    for g in doc["goals"]:
        out.append(f"## {g['id']} — {g['title']}")
        for k in ("outcome", "success_signal", "status", "last_moved", "next_step",
                  "repos", "research_notes", "open_questions"):
            v = g.get(k, "")
            if k in _LIST_KEYS:
                v = "[" + ", ".join(v) + "]"
            out.append(f"- {k}: {v}")
        out.append("")
    return "\n".join(out) + "\n"


def load(path) -> dict:
    return parse_goals(Path(path).read_text(encoding="utf-8"))


def save(path, doc: dict) -> None:
    Path(path).write_text(serialize_goals(doc), encoding="utf-8")  # utf-8, no BOM
