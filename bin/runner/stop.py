"""Kill-switch helper: engage/clear/status the global STOP file (forge/STOP).

Any running harness job checks this file before each step and halts cleanly.
CLI: python bin/runner/stop.py on|off|status   (or just touch/rm the file).
"""
from __future__ import annotations

import sys
from pathlib import Path

STOP_FILE = Path(__file__).resolve().parents[2] / "forge" / "STOP"


def engage() -> None:
    STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOP_FILE.write_text("stop\n", encoding="utf-8")


def clear() -> None:
    if STOP_FILE.exists():
        STOP_FILE.unlink()


def is_engaged() -> bool:
    return STOP_FILE.exists()


def main(argv=None) -> int:
    arg = (argv or sys.argv[1:] or ["status"])[0].lower()
    if arg in ("on", "engage", "stop"):
        engage(); print(f"STOP engaged: {STOP_FILE}")
    elif arg in ("off", "clear", "resume"):
        clear(); print("STOP cleared — runs may proceed")
    else:
        print(f"STOP {'ENGAGED' if is_engaged() else 'clear'} ({STOP_FILE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
