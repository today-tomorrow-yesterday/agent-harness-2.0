#!/usr/bin/env python3
"""self_loop.py — closed-loop liveness auditor + mechanical healer for the fleet.

The middle layer of the health chain (detect -> HEAL -> fix):
  bin/self_test.py answers "is the code right?"; this answers "is the FLEET alive?"
  — the two die differently. A registry job whose installed task was deleted,
  disabled, or quietly stopped firing passes every unit test while the pipeline
  it powers has been dead for weeks.

CYCLE (scheduled daily by default; run it as often as you like — it's idempotent):
  1. AUDIT    — for every REGISTRY job (bin/scheduler/jobs.py): installed? enabled?
                last result? last-run AGE vs its cadence window?
  2. LIVENESS — classify: MISSING / DISABLED / NEVER_FIRED / STALE / FAILED / OK.
                Recency is the point — result codes alone are blind to a task that
                simply stopped being triggered.
  3. HEAL     — re-run a FAILED job marked safe_rerun=True in the registry (cheap +
                idempotent only; never claude-invoking or externally-writing jobs).
                Anti-thrash: at most one heal per job per 24h, max 3 per cycle.
  4. REPORT   — heartbeat to logs/self-loop.log; escalations (deduped per day) to
                Slack via notify_slack when something needs a human.

Platform: full audit/heal on Windows (Task Scheduler). On macOS/Linux the
installed-state audit is skipped for now (cron/launchd introspection TODO) and
the run degrades to a heartbeat — it never false-alarms on an OS it can't read.

Kill-switch honored (forge/STOP). Zero LLM calls.
"""
from __future__ import annotations

import datetime as dt
import json
import platform
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOG_PATH = REPO / "logs" / "self-loop.log"
STATE_PATH = REPO / "logs" / "self-loop-state.json"

sys.path.insert(0, str(REPO / "bin"))
from runner.stop import is_engaged  # noqa: E402
from scheduler import jobs as _jobs  # noqa: E402

# cadence -> hours of silence before a task counts as STALE (generous: a laptop
# can sleep through one trigger; StartWhenAvailable catch-up covers the rest).
STALE_HOURS = {"daily": 30, "weekly": 192}
MAX_HEALS_PER_CYCLE = 3
HEAL_COOLDOWN_H = 24

# Task-result codes that are benign, not failures.
_OK_RESULTS = {0, 0x41301, 0x41303, 0x41325}  # 0=ok, running, not-yet-run, queued


def log(level: str, message: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{ts} [{level}] {message}\n")
    print(f"{ts} [{level}] {message}", file=sys.stderr)


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"healed": {}, "escalated": {}}


def _save_state(state: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError as e:
        log("WARN", f"could not persist state: {e}")


def _query_tasks() -> dict:
    """One batched PowerShell query for all agent-harness-* tasks."""
    names = [f"agent-harness-{j.id}" for j in _jobs.REGISTRY]
    ps = (
        "$out=@{}; foreach ($n in @(" + ",".join(f"'{n}'" for n in names) + ")) {"
        "  $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue;"
        "  $i = Get-ScheduledTaskInfo -TaskName $n -ErrorAction SilentlyContinue;"
        "  if ($t) { $out[$n] = @{ state = [string]$t.State;"
        "    lastRun = if ($i.LastRunTime) { $i.LastRunTime.ToString('o') } else { '' };"
        "    lastResult = $i.LastTaskResult } } }"
        " $out | ConvertTo-Json -Depth 3"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not r.stdout.strip():
        return {}
    data = json.loads(r.stdout)
    return data if isinstance(data, dict) else {}


def audit(tasks: dict) -> list[tuple[str, str, str]]:
    """Classify each registry job -> (job_id, status, detail)."""
    now = dt.datetime.now().astimezone()
    findings: list[tuple[str, str, str]] = []
    for j in _jobs.REGISTRY:
        t = tasks.get(f"agent-harness-{j.id}")
        if not t:
            findings.append((j.id, "MISSING", "in REGISTRY but not installed"))
            continue
        if t.get("state") == "Disabled":
            findings.append((j.id, "DISABLED", "task is disabled"))
            continue
        raw = t.get("lastRun") or ""
        if not raw or raw.startswith("1999"):
            findings.append((j.id, "NEVER_FIRED", "installed but has never run"))
            continue
        last = dt.datetime.fromisoformat(raw)
        age_h = (now - last).total_seconds() / 3600
        if age_h > STALE_HOURS.get(j.cadence, 30):
            findings.append((j.id, "STALE", f"last ran {age_h:.0f}h ago (cadence={j.cadence})"))
            continue
        result = int(t.get("lastResult") or 0)
        if result not in _OK_RESULTS:
            findings.append((j.id, "FAILED", f"last result 0x{result:X}"))
            continue
        findings.append((j.id, "OK", ""))
    return findings


def heal(findings, state) -> int:
    """Re-run FAILED safe_rerun jobs (bounded + cooldown). Returns heal count."""
    now = dt.datetime.now(dt.timezone.utc)
    safe = {j.id for j in _jobs.REGISTRY if j.safe_rerun}
    healed = 0
    for job_id, status, _ in findings:
        if healed >= MAX_HEALS_PER_CYCLE:
            break
        if status != "FAILED" or job_id not in safe:
            continue
        last_heal = state["healed"].get(job_id)
        if last_heal and (now - dt.datetime.fromisoformat(last_heal)).total_seconds() < HEAL_COOLDOWN_H * 3600:
            continue  # anti-thrash: already tried recently
        r = subprocess.run(["schtasks", "/Run", "/TN", f"agent-harness-{job_id}"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            log("INFO", f"HEAL: re-ran failed safe job {job_id}")
            state["healed"][job_id] = now.isoformat()
            healed += 1
        else:
            log("WARN", f"HEAL failed to launch {job_id}: {r.stderr.strip()[:120]}")
    return healed


def escalate(findings, state) -> int:
    """Slack the findings a human must see — deduped to once per job+status per day."""
    today = dt.date.today().isoformat()
    to_send = []
    for job_id, status, detail in findings:
        if status in ("OK",):
            continue
        key = f"{job_id}:{status}"
        if state["escalated"].get(key) == today:
            continue
        state["escalated"][key] = today
        to_send.append(f"- {job_id}: {status} ({detail})")
    if to_send:
        try:
            from notify_slack import post_slack
            post_slack("self-loop fleet findings:\n" + "\n".join(to_send))
        except Exception:
            pass
    return len(to_send)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if is_engaged():
        log("INFO", "STOP engaged (forge/STOP) — skipping cycle.")
        return 0

    if platform.system().lower() != "windows":
        log("INFO", "cycle: non-Windows — installed-task audit skipped (heartbeat only).")
        return 0

    tasks = _query_tasks()
    if not tasks:
        log("INFO", "cycle: no agent-harness tasks installed yet — nothing to audit. "
                    "(run bin/scheduler/install.py --apply)")
        return 0

    state = _load_state()
    findings = audit(tasks)
    problems = [f for f in findings if f[1] != "OK"]
    healed = heal(findings, state)
    escalated = escalate(findings, state)
    _save_state(state)
    log("INFO", f"cycle: tasks={len(tasks)}/{len(_jobs.REGISTRY)} problems={len(problems)} "
                f"healed={healed} escalated_new={escalated}")
    for job_id, status, detail in problems:
        log("WARN", f"  {job_id}: {status} {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
