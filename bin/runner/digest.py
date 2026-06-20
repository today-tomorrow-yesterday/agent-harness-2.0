"""The 'while you were away' report — what ran, what it cost, what needs you.

build_digest is pure (takes run + event rows) so it's unit-testable; main()
fetches the last 24h from runner.db, writes agent-activity.md, and best-effort
posts to Slack. Scheduled daily so you review on return — keeps you ON the loop.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import events  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "agent-activity.md"


def build_digest(runs: list[dict], evts: list[dict], today: str) -> str:
    lines = [f"# Agent activity — {today}", ""]
    if not runs:
        lines.append("_No autonomous runs in the window._")
        return "\n".join(lines) + "\n"

    attention = [e for e in evts if e.get("needs_attention")]
    lines.append(f"**{len(runs)} run(s)** · "
                 f"{sum(r.get('action_count', 0) for r in runs)} actions · "
                 f"{len([r for r in runs if r.get('status') == 'halted'])} halted · "
                 f"⚠ {len(attention)} need attention")
    lines += ["", "## Runs", ""]
    for r in runs:
        cost = f" · ${r.get('cost', 0):.2f}" if r.get("cost") else ""
        reason = f" — {r['halt_reason']}" if r.get("halt_reason") else ""
        lines.append(f"- **{r.get('job', '?')}** [{r.get('status', '?')}] — "
                     f"{r.get('action_count', 0)} actions{cost}{reason}")

    if attention:
        lines += ["", "## ⚠ Needs your attention", ""]
        for e in attention:
            lines.append(f"- `{e.get('job', '')}` {e.get('event_type', '')}: "
                         f"{(e.get('payload') or '')[:160]}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    since = int(time.time()) - 24 * 3600
    runs, evts = events.fetch_since(since)
    today = time.strftime("%Y-%m-%d")
    md = build_digest(runs, evts, today)
    OUT.write_text(md, encoding="utf-8")
    try:
        sys.path.insert(0, str(REPO / "bin"))
        from notify_slack import post_slack
        post_slack(md, title=f"Agent activity ({today})")
    except Exception:  # noqa: BLE001 — Slack is best-effort
        pass
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
