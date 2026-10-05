#!/usr/bin/env python3
"""tmp_purge.py — keep a scratch directory self-cleaning.

A designated DISPOSABLE drop zone (one-off HTML reports, mockups, scratch output an agent
hands over to open in a browser) only stays disposable if something empties it. The
contract: anything in it is temporary and auto-deleted, so nobody has to remember to clean
up — and nobody should put anything there they want to keep.

Deletes files whose modified-time is older than --days (default 14), then prunes empty
subdirectories. README.txt / README.md are never deleted (they carry the contract).
Dotfiles are skipped.

Target directory: --dir, else $HARNESS_TMP_DIR, else <repo>/tmp. As a guard against a
mistyped path it REFUSES to purge a filesystem root, the home directory, the repo root, or
any directory that contains a .git folder.

    python bin/tmp_purge.py --dry-run         # list what would be deleted
    python bin/tmp_purge.py [--days 14] [--dir PATH]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import harness_common as hc  # noqa: E402

KEEP = {"readme.txt", "readme.md"}


def default_dir() -> Path:
    env = os.environ.get("HARNESS_TMP_DIR")
    return Path(env).expanduser() if env else ROOT / "tmp"


def refuse_reason(target: Path) -> str | None:
    """Why `target` must not be purged, or None if it is a plausible scratch dir."""
    t = target.resolve()
    if t == Path(t.anchor):
        return "it is a filesystem root"
    if t == Path.home().resolve():
        return "it is the home directory"
    if t == ROOT.resolve():
        return "it is the repo root"
    if (t / ".git").exists():
        return "it contains a .git folder"
    return None


def purge(target: Path, days: int, dry_run: bool, now: float | None = None) -> tuple[int, int]:
    """(files deleted-or-would-be, bytes). Ages come from mtime on purpose."""
    cutoff = (now if now is not None else time.time()) - days * 86400
    deleted = freed = 0
    for f in target.rglob("*"):
        if not f.is_file() or f.name.lower() in KEEP or f.name.startswith("."):
            continue
        try:
            st = f.stat()
            # sibling-sweep: ok mtime-as-content-age — for a scratch file "untouched for N
            # days" IS the retention rule; there is no content date to prefer.
            if st.st_mtime >= cutoff:
                continue
            if dry_run:
                print(f"[tmp-purge] would delete: {f.relative_to(target).as_posix()}")
            else:
                f.unlink()
            deleted += 1
            freed += st.st_size
        except OSError as e:
            print(f"[tmp-purge] could not remove {f.name}: {e}", file=sys.stderr)
    if not dry_run:
        for d in sorted((p for p in target.rglob("*") if p.is_dir()),
                        key=lambda p: len(p.parts), reverse=True):
            try:
                next(d.iterdir())
            except StopIteration:
                try:
                    d.rmdir()
                except OSError:
                    pass
            except OSError:
                pass
    return deleted, freed


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Purge old files from the scratch directory.")
    ap.add_argument("--days", type=int, default=14, help="delete files older than N days")
    ap.add_argument("--dir", default=None, help="scratch dir (default: $HARNESS_TMP_DIR or <repo>/tmp)")
    ap.add_argument("--dry-run", action="store_true", help="list what would be deleted")
    args = ap.parse_args(argv)
    hc.set_dry_run(args.dry_run, "tmp_purge.py --dry-run")
    if not hc.guard_or_skip("tmp-purge", lambda m: print(m, file=sys.stderr)):
        return 0
    target = Path(args.dir).expanduser() if args.dir else default_dir()
    if not target.is_dir():
        print(f"[tmp-purge] {target} does not exist — nothing to purge (not configured)")
        return 0
    why = refuse_reason(target)
    if why:
        print(f"[tmp-purge] REFUSING to purge {target}: {why}", file=sys.stderr)
        return 2
    deleted, freed = purge(target, args.days, args.dry_run)
    verb = "would purge" if args.dry_run else "purged"
    print(f"[tmp-purge] {verb} {deleted} file(s), ~{freed // 1024} KB, older than "
          f"{args.days}d from {target.name}/")
    hc.record_outcome("tmp-purge", status="ok" if deleted else "empty", produced=deleted,
                      detail=f"{deleted} file(s), {freed // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
