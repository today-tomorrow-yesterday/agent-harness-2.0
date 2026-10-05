#!/usr/bin/env python3
"""Plant seeds and record decisions on them from the command line (the manual path;
the other path is telling Claude in a session). See bin/goal_loop/seeds.py.

    python bin/seeds-cli.py add "idea in one line" ["optional detail"]
    python bin/seeds-cli.py list
    python bin/seeds-cli.py water    <id> ["note"]
    python bin/seeds-cli.py refine   <id> ["note"]
    python bin/seeds-cli.py letgo    <id> ["note"]
    python bin/seeds-cli.py graduate <id> ["note"]
    python bin/seeds-cli.py snooze   <id> ["note"]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from goal_loop import seeds  # noqa: E402

_VERDICT = {"water": "water", "refine": "refine", "letgo": "let_go",
            "graduate": "graduate", "snooze": "snooze"}


def main(argv=None, path=None) -> int:
    ap = argparse.ArgumentParser(prog="seeds-cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("text")
    add.add_argument("detail", nargs="?", default="")
    sub.add_parser("list")
    for v in _VERDICT:
        p = sub.add_parser(v)
        p.add_argument("id")
        p.add_argument("note", nargs="?", default="")
    args = ap.parse_args(argv)

    if args.cmd == "add":
        if not args.text.strip():
            print("nothing to plant (empty text).")
            return 1
        sid = seeds.capture(args.text.strip(), detail=args.detail, source="cli", path=path)
        print(f"planted [{sid}]  {args.text.strip()}")
        return 0

    if args.cmd == "list":
        rows = seeds.list_seeds(path=path)
        if not rows:
            print("seedbank is empty.")
            return 0
        for s in rows:
            print(f"[{s['id']}]  {s['status']:<10}  {s['text']}")
        return 0

    ok = seeds.resolve(args.id, _VERDICT[args.cmd], note=args.note, path=path)
    print(f"{args.cmd} {args.id}: {'recorded' if ok else 'NOT FOUND (run `list`)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
