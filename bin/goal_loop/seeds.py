"""Idea Cultivation Loop — the seedbank.

Captures the user's ideas as SEEDS, resurfaces them on a cadence so they can water /
refine / let go, and tracks them non-deterministically (status + verdict history,
never a completion %). The human-in-the-loop complement to the Goal Loop: the goal
loop measures movement toward goals; this keeps new ideas from dying in a folder by
bringing each one back until the user decides what it is.

Store: forge/seedbank.json (per-machine, gitignored; absent until the first capture).
All functions take an optional path for testing, and an optional now_ts so the
cadence logic is deterministic under test.

Lifecycle:
    new --water--> growing --graduate--> graduated   (became a project or a goal)
        --refine-> refining
        --let_go-> let_go                            (never resurfaces)
        --snooze-> (status unchanged, clock reset)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

SEEDBANK = Path(__file__).resolve().parents[2] / "forge" / "seedbank.json"

# How often an active seed comes back for a decision. Twice a week by default; the
# planner and the nudge share this so a seed is never surfaced by both in one cycle.
DEFAULT_CADENCE_DAYS = 3.5

# statuses that get resurfaced for watering
ACTIVE = ("new", "watering", "refining", "growing")
# verdict -> new status (None = keep current status, e.g. snooze)
_VERDICT_STATUS = {"water": "growing", "refine": "refining",
                   "let_go": "let_go", "graduate": "graduated", "snooze": None}
VERDICTS = tuple(_VERDICT_STATUS)


def _load(path=None) -> dict:
    p = Path(path or SEEDBANK)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("seeds"), list):
                return data
        except (ValueError, OSError):
            pass
    return {"seeds": []}


def _save(data, path=None) -> None:
    p = Path(path or SEEDBANK)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Atomic: a crash mid-write must not truncate the seedbank (which _load would
    # then silently read as empty -> every seed lost).
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def capture(text, detail="", source="", status="new", refs=None,
            now_ts=None, path=None) -> str:
    """Plant a seed. Returns its id."""
    now = int(now_ts if now_ts is not None else time.time())
    sid = uuid.uuid4().hex[:8]
    data = _load(path)
    data["seeds"].append({
        "id": sid, "text": text, "detail": detail, "source": source,
        "status": status, "captured_at": now, "last_surfaced_at": None,
        "surface_count": 0, "refs": refs or [], "verdicts": [],
    })
    _save(data, path)
    return sid


def list_seeds(status=None, path=None) -> list[dict]:
    seeds = _load(path)["seeds"]
    if status is None:
        return seeds
    if isinstance(status, str):
        status = (status,)
    return [s for s in seeds if s["status"] in status]


def due_for_review(now_ts, cadence_days=DEFAULT_CADENCE_DAYS, path=None) -> list[dict]:
    """Active seeds never surfaced, or last surfaced >= cadence_days ago."""
    cutoff = int(now_ts) - int(cadence_days * 86400)
    out = []
    for s in _load(path)["seeds"]:
        if s["status"] not in ACTIVE:
            continue
        if s["last_surfaced_at"] is None or s["last_surfaced_at"] <= cutoff:
            out.append(s)
    return out


def mark_surfaced(seed_ids, now_ts, path=None) -> None:
    data = _load(path)
    ids = set(seed_ids)
    for s in data["seeds"]:
        if s["id"] in ids:
            s["surface_count"] += 1
            s["last_surfaced_at"] = int(now_ts)
    _save(data, path)


def resolve(seed_id, verdict, note="", now_ts=None, path=None) -> bool:
    """Record the user's verdict (water/refine/let_go/graduate/snooze) and move the
    seed's status. False for an unknown seed id or an unknown verdict."""
    if verdict not in _VERDICT_STATUS:
        return False
    now = int(now_ts if now_ts is not None else time.time())
    data = _load(path)
    for s in data["seeds"]:
        if s["id"] == seed_id:
            s["verdicts"].append({"ts": now, "verdict": verdict, "note": note})
            new = _VERDICT_STATUS[verdict]
            if new is not None:
                s["status"] = new
            s["last_surfaced_at"] = now
            _save(data, path)
            return True
    return False


def render_review(seeds, today="") -> str:
    """Markdown 'Seed Review' block for the briefing / nudge — each seed is a header
    bullet with indented sub-bullets, a blank line between seeds, and clear
    instructions for recording a decision."""
    if not seeds:
        return "## Seed Review\n\nNo seeds due for watering — the seedbank is quiet.\n"
    head = f"## Seed Review — {today}".rstrip(" —")
    lines = [head, "",
             "Each idea you planted is below. To decide, tell Claude "
             "**water / refine / let go** + the seed's `[id]` (or just its name).",
             ""]
    for s in seeds:
        lines.append(f"- **{s['text']}**  `[{s['id']}]`")
        if s.get("detail"):
            lines.append(f"    - {s['detail']}")
        if s.get("recommendation"):
            lines.append(f"    - *What watering looks like:* {s['recommendation']}")
        lines.append(f"    - status: **{s['status']}**  ·  surfaced {s['surface_count']}×")
        lines.append("    - **water**  ·  **refine**  ·  **let go**")
        lines.append("")          # blank line = visual gap between ideas
    lines.append("---")
    lines.append("_Decide in a session, or run_ `python bin/seeds-cli.py water <id>` "
                 "_(also `refine` / `letgo` / `graduate` / `snooze`)._")
    return "\n".join(lines) + "\n"
