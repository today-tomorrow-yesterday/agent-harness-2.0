#!/usr/bin/env python3
"""fleet_status.py — one-command, READ-ONLY health view of the harness fleet.

Composes signals that already exist (no new data sources):
  - kill-switch state + reason                  (forge/STOP)
  - autonomous runs in the last 24h             (forge/runner.db)
  - every declared job's last OUTCOME           (forge/outcomes/<job>.json)
  - open issues from the alert ledger           (forge/alert-state.json)
  - in-flight job locks                         (forge/locks/*.lock)
  - recent operational alerts                   (forge/alerts.log)
  - the self-loop heartbeat                     (forge/self-loop-heartbeat)
  - the latest self-test verdict                (self-test-report.md)

A job's health is its outcome sidecar — did it FINISH, and what did it produce — not a
log file's mtime: a hung process keeps touching its log while it never finishes.

THE DEAD-MAN'S SWITCH. self_loop heals everything else, but it cannot report its own
death. This is the one component that watches it: a missing or stale heartbeat raises a
state-gated alert ABOUT self-loop (subject="self-loop"), so only self-loop's own recovery
can clear it — never this program's clean run.

    python bin/fleet_status.py           # human summary
    python bin/fleet_status.py --json    # machine-readable
    python bin/fleet_status.py --slack   # also post the summary (if Slack is configured)
    python bin/fleet_status.py --dry-run # never raise the dead-man's-switch alert

Exit 0 by default even when problems are found: a REPORTER must not be punished for
reporting (a non-zero exit makes the healer treat it as the broken job and silences the
status feed exactly while the fleet has problems). --exit-nonzero-on-problems restores
that for shell use.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import harness_common as hc  # noqa: E402

FORGE = ROOT / "forge"
SELFTEST_REPORT = ROOT / "self-test-report.md"
HEARTBEAT = FORGE / "self-loop-heartbeat"
WINDOW_H = {"daily": 30.0, "weekly": 192.0}


def _iso_age_h(raw: str) -> float | None:
    from scheduler.introspect import parse_iso  # noqa: PLC0415
    d = parse_iso(raw)
    return None if d is None else (hc._clock() - d.timestamp()) / 3600.0


def gather() -> dict:
    """Collect the fleet's health into a plain dict (each probe fail-open, never fabricating
    a value it could not read)."""
    s: dict = {"problems": [], "notes": []}

    try:
        from runner import stop  # noqa: PLC0415
        s["stopped"] = stop.is_engaged()
        s["stop_reason"] = stop.reason() if s["stopped"] else ""
    except Exception:  # noqa: BLE001
        s["stopped"], s["stop_reason"] = hc.is_stopped(), ""
    if s["stopped"]:
        s["problems"].append(f"fleet STOPPED {s['stop_reason']}".strip())

    # last-24h runs from the audit DB
    try:
        from runner import events  # noqa: PLC0415
        if not events.DB_PATH.exists():
            s["runs_24h"] = None
            s["notes"].append("no runner audit DB yet — no autonomous run has been recorded")
        else:
            runs, evts = events.fetch_since(int(hc._clock()) - 24 * 3600)
            halted = [r for r in runs if r.get("status") == "halted"]
            benign = [r for r in halted if any(k in (r.get("halt_reason") or "").lower()
                                               for k in ("rate limit", "session limit",
                                                         "usage limit"))]
            errored = [r for r in runs if r.get("status") == "error"]
            attn = [e for e in evts if e.get("needs_attention")]
            s.update(runs_24h=len(runs), halted_24h=len(halted), errored_24h=len(errored),
                     backoff_halts_24h=len(benign), needs_attention_24h=len(attn),
                     recent_runs=[(r.get("job", "?"), r.get("status", "?"),
                                   r.get("action_count", 0)) for r in runs[-8:]])
            if len(halted) > len(benign):
                s["problems"].append(f"{len(halted) - len(benign)} halted run(s) in 24h")
            if errored:
                jobs = sorted({r.get("job", "?") for r in errored})
                s["problems"].append(f"{len(errored)} errored run(s) in 24h ({', '.join(jobs[:4])})")
            if attn:
                s["problems"].append(f"{len(attn)} needs-attention event(s) in 24h")
    except Exception as e:  # noqa: BLE001
        s["runs_24h"] = None
        s["problems"].append(f"runner.db unreadable: {type(e).__name__}")

    # every declared job's outcome
    from scheduler import jobs as _jobs  # noqa: PLC0415
    s["jobs"] = {}
    for j in _jobs.REGISTRY:
        rec = hc.read_outcome(j.id)
        win = WINDOW_H.get(j.cadence, 30.0)
        if rec is None:
            s["jobs"][j.id] = {"state": "unknown", "why": "no outcome recorded"}
            continue
        age, status = rec.get("age_h"), rec.get("status")
        if age is None:
            state, why = "bad", "outcome has no readable timestamp"
        elif age > win:
            state, why = "bad", f"last finished {age:.0f}h ago (window {win:.0f}h)"
        elif status in hc.FAILED_OUTCOMES:
            state, why = "bad", f"last run reported '{status}'"
        else:
            state, why = "ok", f"{status}, {age:.1f}h ago, produced {rec.get('produced')!r}"
        s["jobs"][j.id] = {"state": state, "why": why, "status": status,
                           "age_h": None if age is None else round(age, 1)}
        if state == "bad":
            s["problems"].append(f"{j.id}: {why}")
    unknown = [k for k, v in s["jobs"].items() if v["state"] == "unknown"]
    if unknown:
        s["notes"].append(f"{len(unknown)} job(s) have never recorded an outcome: "
                          f"{', '.join(unknown)}")

    s["open_issues"] = hc.open_issues() if hc.ALERT_STATE.exists() else []

    try:
        s["locks"] = sorted(p.stem for p in hc.LOCK_DIR.glob("*.lock")) \
            if hc.LOCK_DIR.exists() else []
    except OSError:
        s["locks"] = []

    try:
        lines = [ln.strip() for ln in hc.ALERTS_LOG.read_text(
            encoding="utf-8", errors="replace").splitlines() if ln.strip()] \
            if hc.ALERTS_LOG.exists() else []
        s["recent_alerts"] = lines[-5:]
    except OSError:
        s["recent_alerts"] = []

    # self-loop dead-man's switch: the heartbeat holds the UTC time the loop last wrote.
    sl = next((j for j in _jobs.REGISTRY if j.id == "self-loop"), None)
    if sl is None:
        s["self_loop_age_h"] = None
        s["notes"].append("self-loop is not in the registry — nothing heals the fleet")
    else:
        try:
            hb = HEARTBEAT.read_text(encoding="utf-8").strip() if HEARTBEAT.exists() else ""
        except OSError:
            hb = ""
        age = _iso_age_h(hb) if hb else None
        s["self_loop_age_h"] = None if age is None else round(age, 1)
        limit = WINDOW_H.get(sl.cadence, 30.0)
        if age is None:
            if (hc.OUTCOMES_DIR / "self-loop.json").exists():
                s["problems"].append("self-loop heartbeat missing — the self-healing loop "
                                     "may be dead")
            else:
                s["notes"].append("self-loop has never run here (no heartbeat yet)")
        elif age > limit:
            s["problems"].append(f"self-loop heartbeat stale ({age:.0f}h > {limit:.0f}h) — "
                                 f"the self-healing loop may be dead")

    # latest self-test verdict
    if SELFTEST_REPORT.exists():
        try:
            text = SELFTEST_REPORT.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"\*\*VERDICT:\s*(\w+)\*\*", text)
            s["self_test"] = m.group(1) if m else "unreadable"
            if s["self_test"] != "PASS":
                s["problems"].append(f"self-test verdict {s['self_test']}")
        except OSError:
            s["self_test"] = "unreadable"
    else:
        s["self_test"] = None
        s["notes"].append("self-test has not run here yet")
    return s


def render(s: dict) -> str:
    out = ["# harness fleet status", ""]
    out.append(f"STOPPED {s['stop_reason']}".strip() if s["stopped"] else "kill-switch clear")
    if s.get("runs_24h") is None:
        out.append("Runs (24h): unknown")
    else:
        out.append(f"Runs (24h): {s['runs_24h']} · halted {s.get('halted_24h', 0)}"
                   + (f" ({s['backoff_halts_24h']} rate-limit backoff)"
                      if s.get("backoff_halts_24h") else "")
                   + f" · errored {s.get('errored_24h', 0)}"
                   + f" · needs-attention {s.get('needs_attention_24h', 0)}")
    out += ["", "Jobs (last outcome):"]
    mark = {"ok": "ok  ", "bad": "BAD ", "unknown": "??  "}
    out += [f"  {mark[v['state']]} {k}: {v['why']}" for k, v in s["jobs"].items()]
    sl = s.get("self_loop_age_h")
    out.append("")
    out.append(f"Self-loop heartbeat: {f'{sl}h ago' if sl is not None else 'none'}")
    out.append(f"Self-test verdict: {s.get('self_test') or 'not run yet'}")
    if s.get("open_issues"):
        out += ["", "Open issues:"] + [f"  {i['job']} ({i['age_d']:.1f}d): {i['message'][:100]}"
                                       for i in s["open_issues"]]
    if s["locks"]:
        out.append(f"In-flight: {', '.join(s['locks'])}")
    if s["recent_alerts"]:
        out += ["", "Recent alerts:"] + [f"  {a}" for a in s["recent_alerts"]]
    if s["notes"]:
        out += ["", "Notes:"] + [f"  {n}" for n in s["notes"]]
    unknown = sum(1 for v in s["jobs"].values() if v["state"] == "unknown")
    if s["problems"]:
        out += ["", f"{len(s['problems'])} issue(s): " + "; ".join(s["problems"])]
    elif unknown:
        out += ["", f"no problems found, but {unknown} of {len(s['jobs'])} job(s) are UNKNOWN "
                    f"(no outcome recorded) — not an all-clear"]
    else:
        out += ["", "all clear"]
    return "\n".join(out)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Read-only harness fleet health view.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--slack", action="store_true", help="also post the summary to Slack")
    ap.add_argument("--dry-run", action="store_true", help="raise no alert, post nothing")
    ap.add_argument("--exit-nonzero-on-problems", action="store_true")
    args = ap.parse_args(argv)
    hc.set_dry_run(args.dry_run, "fleet_status.py --dry-run")
    s = gather()
    summary = render(s)
    print(json.dumps(s, indent=2, default=str) if args.json else summary)
    if any("self-loop heartbeat" in p for p in s["problems"]):
        hc.alert("fleet-status", "self-loop heartbeat stale/missing — the self-healing loop "
                                 "may be DEAD; nothing else watches it",
                 fleet=True, subject="self-loop")
    if args.slack and not hc.is_dry_run():
        hc._post(summary, title=(f"fleet — {len(s['problems'])} issue(s)" if s["problems"]
                                 else "fleet — all clear"))
    if args.exit_nonzero_on_problems:
        return 1 if s["problems"] else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
