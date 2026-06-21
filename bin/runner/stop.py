"""Kill-switch helper: engage/clear/status the global STOP file (forge/STOP).

Any running harness job checks this file before each step/run and halts cleanly.
CLI: python bin/runner/stop.py on ["reason..."] | off | status

The file holds JSON {ts, reason} so a stale STOP is self-documenting (status shows
when + why), and the CLI fires a best-effort Slack alert on engage/clear so a
stopped fleet can't go unnoticed. Existence is all the job-side guards check, so the
JSON content is backward-compatible with is_stopped()/is_engaged().
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

STOP_FILE = Path(__file__).resolve().parents[2] / "forge" / "STOP"


def engage(reason: str = "") -> None:
    STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOP_FILE.write_text(
        json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "reason": reason}),
        encoding="utf-8")


def clear() -> None:
    if STOP_FILE.exists():
        STOP_FILE.unlink()


def is_engaged() -> bool:
    return STOP_FILE.exists()


def reason() -> str:
    """'since <ts> - <reason>' when engaged, else ''. Tolerates the old bare format."""
    if not STOP_FILE.exists():
        return ""
    try:
        d = json.loads(STOP_FILE.read_text(encoding="utf-8"))
        s = f"since {d.get('ts', '?')}"
        return s + (f" - {d['reason']}" if d.get("reason") else "")
    except (ValueError, OSError):
        return "since unknown"


def _alert(msg: str) -> None:
    """Best-effort Slack alert (CLI path only; never raises)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bin"))
        from notify_slack import post_slack
        post_slack(msg, title="kill-switch")
    except Exception:
        pass


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        args = ["status"]
    cmd = args[0].lower()
    if cmd in ("on", "engage", "stop"):
        r = " ".join(args[1:])
        engage(r)
        print(f"STOP engaged: {STOP_FILE}")
        _alert(f"FLEET STOPPED{(' - ' + r) if r else ''} - all jobs skip until cleared")
    elif cmd in ("off", "clear", "resume"):
        clear()
        print("STOP cleared - runs may proceed")
        _alert("fleet RESUMED - kill-switch cleared")
    else:
        print(f"STOP {'ENGAGED ' + reason() if is_engaged() else 'clear'} ({STOP_FILE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
