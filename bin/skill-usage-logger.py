"""PostToolUse hook: log Skill-tool invocations to forge/skill-usage.jsonl.

Registered in BOTH profiles' settings.json with matcher "Skill". Reads the hook
payload JSON on stdin and appends one JSONL line per Skill invocation.

HOT-PATH SAFETY: this runs after every Skill invocation. Any error is swallowed
and the hook always exits 0 — a logging failure must never break a skill call.
"""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from skill_forge.usage_logger import build_usage_record, parse_payload
    from skill_forge import config
    _LOG = config.FORGE_DIR / "skill-usage.jsonl"
except Exception:  # noqa: BLE001 - degrade gracefully if package import fails
    build_usage_record = None
    parse_payload = None
    _LOG = Path(r"Z:\agent-os\forge\skill-usage.jsonl")


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = parse_payload(raw) if parse_payload else {}
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rec = build_usage_record(payload, now) if build_usage_record else None
        if rec:
            _LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
    except Exception:  # noqa: BLE001 - never break a Skill invocation
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
