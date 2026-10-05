#!/usr/bin/env python3
"""self_loop.py — closed-loop liveness auditor + mechanical healer for the fleet.

The middle layer of the health chain (detect -> HEAL -> fix):
  bin/self_test.py answers "is the code right?"; this answers "is the FLEET alive?"
  — the two die differently. A registry job whose installed task was deleted,
  disabled, or quietly stopped firing passes every unit test while the pipeline
  it powers has been dead for weeks.

CYCLE (scheduled daily by default; idempotent, run it as often as you like):
  1. AUDIT     — read what the OS scheduler really has installed (bin/scheduler/
                 introspect.py: cron / launchd / Task Scheduler) plus every job's outcome
                 sidecar (forge/outcomes/<job>.json, written by record_outcome).
  2. LIVENESS  — reconcile expected (REGISTRY) vs actual:
                   MISSING          declared, not installed
                   UNDECLARED       installed, not declared (unaudited)
                   DISABLED         installed, switched off
                   NEVER_FIRED      installed, never ran, no upcoming trigger
                   STALE            last run older than its cadence window
                   FAILED           scheduler's last result is a failure
                   RAN-BUT-FAILED   exited cleanly, but its own outcome says it did not
                                    do its work (login died, rate-limited, ...)
                   STALE-OUTCOME    the task keeps firing but its outcome sidecar stopped
                                    moving — its success signal is frozen, not healthy
                 Recency is the point: result codes alone are blind to a task that simply
                 stopped being triggered.
  3. HEAL      — re-run a FAILED / RAN-BUT-FAILED job marked safe_rerun=True (cheap +
                 idempotent only). Rolling-window anti-thrash: at most 2 re-runs per job per
                 24h, then re-runs PAUSE (with the resume time named) and it escalates; at
                 most 3 heals per cycle. A re-run is skipped — without spending an attempt —
                 when it cannot help: the job's own next slot is imminent, or its last run
                 hit a usage limit whose reset time has not passed.
  4. REPORT    — forge/self-loop-latest.md + a heartbeat (forge/self-loop-heartbeat, which
                 bin/fleet_status.py watches: a dead self-loop cannot report its own death).
                 Escalations go through the shared state gate (harness_common.mark_broken):
                 a condition pages once on OK->BROKEN, stays silent while chronic, and a
                 job that recovers WITH evidence (a fresh ok/empty outcome) gets a green
                 'recovered'.

PLATFORM: what each OS scheduler can report differs (see introspect.py). Windows reports
last-run time and result; launchd reports last exit status; cron reports neither, so on
Linux recency comes from outcome sidecars alone. A job with neither source is reported
"recency unknown" — it is never assumed healthy and never paged as stale.

An unreadable scheduler is reported as a BLIND audit, never as a clean fleet.

Kill-switch honored (forge/STOP). Single-instance. Zero LLM calls.

    python bin/self_loop.py             # one cycle
    python bin/self_loop.py --dry-run   # audit + liveness + would-heal; no actions, no pages
    python bin/self_loop.py --quiet     # never post to Slack (still logs + heartbeat)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FORGE = REPO / "forge"
LOG_PATH = REPO / "logs" / "self-loop.log"
STATE_PATH = REPO / "logs" / "self-loop-state.json"
HEARTBEAT = FORGE / "self-loop-heartbeat"
REPORT = FORGE / "self-loop-latest.md"
JOB_ID = "self-loop"

sys.path.insert(0, str(REPO / "bin"))
import harness_common as hc  # noqa: E402
from scheduler import introspect as _intro  # noqa: E402
from scheduler import jobs as _jobs  # noqa: E402

# cadence -> hours of silence before a job counts as STALE (generous: a laptop can sleep
# through one trigger; the Windows StartWhenAvailable catch-up covers the rest).
STALE_HOURS = {"daily": 30, "weekly": 192}
HEAL_CAP = 3                 # max heal actions per cycle
MAX_HEAL_ATTEMPTS = 2        # re-runs per job inside the rolling window before pausing
HEAL_WINDOW_H = 24
IMMINENT_SLOT_H = 3          # own next slot this close -> let the scheduler run it
POST_BOOT_GRACE_H = 2.0      # just booted: overdue jobs are catching up, not dead

# Scheduler result codes that are benign, not failures (Windows): 0 = ok,
# 0x41301 running, 0x41303 not yet run, 0x41325 queued.
_OK_RESULTS = {0, 0x41301, 0x41303, 0x41325}


def log(level: str, message: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{ts} [{level}] {message}\n")
    except OSError:
        pass
    print(f"{ts} [{level}] {message}", file=sys.stderr)


def _load_state() -> dict:
    try:
        d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            d.setdefault("attempts", {})
            return d
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001
        log("WARN", "state file unreadable — resetting heal-attempt memory")
    return {"attempts": {}}


def _hours_since(d: dt.datetime | None, now: dt.datetime) -> float | None:
    return None if d is None else (now - d).total_seconds() / 3600.0


def next_slot(job, now: dt.datetime) -> dt.datetime:
    """The job's next scheduled local time after `now` (pure)."""
    h, m = (int(x) for x in job.time.split(":"))
    local = now.astimezone()
    cand = local.replace(hour=h, minute=m, second=0, microsecond=0)
    if job.cadence == "weekly" and job.dow:
        want = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN").index(job.dow)
        cand += dt.timedelta(days=(want - cand.weekday()) % 7)
        if cand <= local:
            cand += dt.timedelta(days=7)
    elif cand <= local:
        cand += dt.timedelta(days=1)
    return cand


def audit(installed: dict, now: dt.datetime, uptime_h: float | None,
          registry=None, outcomes: dict | None = None,
          os_name: str | None = None) -> list[tuple[str, str, str, str]]:
    """Classify each registry job. Returns [(severity, job_id, status, detail)].

    severity: CRIT / HIGH escalate; INFO is reported only. Pure apart from reading
    outcome sidecars (pass `outcomes` to inject them)."""
    registry = _jobs.REGISTRY if registry is None else registry
    # Only Task Scheduler keeps a run history, so only there can "never ran" be observed.
    tracks_runs = _intro.detect_os(os_name) == "windows"
    out: list[tuple[str, str, str, str]] = []
    catchup: list[str] = []
    declared = {j.id for j in registry}

    for j in registry:
        cad = STALE_HOURS.get(j.cadence, 30)
        inst = installed.get(j.id)
        oc = (outcomes or {}).get(j.id) if outcomes is not None else hc.read_outcome(j.id)
        if inst is None:
            out.append(("CRIT", j.id, "MISSING", "declared in REGISTRY but not installed"))
            continue
        if inst.state == "Disabled":
            out.append(("HIGH", j.id, "DISABLED", "installed but disabled"
                        + (f" ({'; '.join(inst.notes)})" if inst.notes else "")))
            continue

        sched_age = _hours_since(inst.last_run, now)
        oc_age = (oc or {}).get("age_h")
        # Recency evidence: the scheduler's own record where it keeps one, else the
        # job's outcome sidecar. Neither -> unknown, never assumed healthy.
        age = sched_age if sched_age is not None else oc_age

        if tracks_runs and inst.last_run is None and oc is None:
            if inst.next_run is None or inst.next_run <= now:
                out.append(("CRIT", j.id, "NEVER_FIRED",
                            "installed but has never run and has no upcoming trigger"))
            continue
        if age is None:
            out.append(("INFO", j.id, "UNKNOWN",
                        "recency unknown — this scheduler keeps no run history and the job "
                        "has no outcome sidecar (have it call record_outcome)"))
            continue
        if age > cad:
            if uptime_h is not None and uptime_h < POST_BOOT_GRACE_H:
                catchup.append(f"{j.id} ({age:.0f}h/{cad}h)")
            else:
                up = f"machine up {uptime_h:.1f}h" if uptime_h is not None else "uptime unknown"
                out.append(("HIGH", j.id, "STALE",
                            f"last ran {age:.0f}h ago (window {cad}h, {up}) — the trigger "
                            f"looks dead"))
            continue
        if inst.last_result is not None and inst.last_result not in _OK_RESULTS \
                and inst.state != "Running":
            out.append(("HIGH", j.id, "FAILED", f"last result 0x{inst.last_result:X}"))
            continue
        if oc and oc.get("status") in hc.FAILED_OUTCOMES:
            out.append(("HIGH", j.id, "RAN-BUT-FAILED",
                        f"exited cleanly but its last run reported '{oc['status']}' — it ran "
                        f"and did NOT do its work ({str(oc.get('detail', ''))[:80]})"))
            continue
        # STALE-OUTCOME: the scheduler says it ran recently, yet the sidecar the job writes
        # every run has not moved — the reporting path inside the job stopped executing,
        # so its health signal is frozen at its last good value.
        if sched_age is not None and oc is not None and oc_age is not None \
                and oc_age > max(2.0 * cad, cad + 2.0):
            out.append(("HIGH", j.id, "STALE-OUTCOME",
                        f"last ran {sched_age:.0f}h ago but its outcome sidecar is "
                        f"{oc_age:.0f}h old — treat '{oc.get('status')}' as unverified"))
            continue
        out.append(("OK", j.id, "OK", ""))

    for jid in sorted(set(installed) - declared):
        out.append(("HIGH", jid, "UNDECLARED",
                    "installed harness job missing from REGISTRY — it goes unaudited"))
    if catchup:
        out.append(("INFO", JOB_ID, "CATCHING-UP",
                    f"machine booted {uptime_h:.1f}h ago: {len(catchup)} job(s) overdue and "
                    f"expected to catch up — {', '.join(sorted(catchup))}"))
    return out


def rerun_is_futile(job_id: str, now: dt.datetime, oc: dict | None = None) -> tuple[bool, str]:
    """True when a re-run cannot help: the job's last run hit a usage limit whose reset
    time has not passed (re-running only burns the shared session pool). Fail-open."""
    try:
        oc = oc if oc is not None else hc.read_outcome(job_id)
        if oc and oc.get("status") in ("rate_limited", "transient", "error"):
            reset = hc.parse_limit_reset(oc.get("detail", ""), oc.get("ts"))
            if reset is not None and now.astimezone().replace(tzinfo=None) < reset:
                return True, f"its last run hit a usage limit that resets at {reset:%H:%M} local"
    except Exception:  # noqa: BLE001
        pass
    return False, ""


def _window_open(first_iso: str, now: dt.datetime) -> bool:
    d = _intro.parse_iso(first_iso)
    return d is not None and (now - d).total_seconds() < HEAL_WINDOW_H * 3600


def heal(findings, state: dict, now: dt.datetime, dry: bool, registry=None,
         run_now=None) -> tuple[list[str], list[str]]:
    """Re-run FAILED / RAN-BUT-FAILED safe_rerun jobs. Returns (actions, escalations)."""
    registry = _jobs.REGISTRY if registry is None else registry
    by_id = {j.id: j for j in registry}
    run_now = run_now or (lambda job: _intro.run_now(job))
    attempts: dict = state.setdefault("attempts", {})
    actions, escalations = [], []
    failing = {jid for _, jid, status, _ in findings if status in ("FAILED", "RAN-BUT-FAILED")}
    now_iso = now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Sustained recovery clears the counter — only once the window has elapsed, so a
    # job flapping fail/ok every other cycle cannot reset its own cap.
    for jid in list(attempts):
        if jid not in failing and not _window_open(attempts[jid].get("first", ""), now):
            attempts.pop(jid, None)

    cap = HEAL_CAP
    for jid in sorted(failing):
        job = by_id.get(jid)
        if job is None or jid == JOB_ID:
            continue
        if not job.safe_rerun:
            escalations.append(f"{jid} failed — not marked safe_rerun, so it is not re-run "
                               f"automatically; needs a look")
            continue
        futile, why = rerun_is_futile(jid, now)
        if futile:
            escalations.append(f"{jid} failed — auto-rerun withheld: {why}; attempt budget "
                               f"untouched")
            continue
        due_in = (next_slot(job, now) - now.astimezone()).total_seconds() / 3600.0
        if 0 <= due_in <= IMMINENT_SLOT_H:
            actions.append(f"left {jid} for its own slot in {due_in:.1f}h (no heal needed)")
            continue
        rec = attempts.get(jid) or {}
        count, first = rec.get("count", 0), rec.get("first", now_iso)
        if rec and not _window_open(first, now):
            count, first = 0, now_iso
        if count >= MAX_HEAL_ATTEMPTS:
            resume = _intro.parse_iso(first)
            resume_s = ((resume + dt.timedelta(hours=HEAL_WINDOW_H)).strftime("%Y-%m-%dT%H:%MZ")
                        if resume else f"~{HEAL_WINDOW_H}h after the first failure")
            escalations.append(f"{jid} still failing after {count} auto-heals in "
                               f"{HEAL_WINDOW_H}h — re-runs PAUSED until {resume_s}, then "
                               f"resume automatically; needs a look")
            attempts[jid] = {"count": count, "first": first}
            continue
        if cap <= 0:
            escalations.append(f"{jid} failed — heal cap reached this cycle, deferred")
            continue
        cap -= 1
        if dry:
            actions.append(f"WOULD re-run {jid} (attempt {count + 1}/{MAX_HEAL_ATTEMPTS})")
            continue
        ok, detail = run_now(job)
        attempts[jid] = {"count": count + 1, "first": first}
        if ok:
            actions.append(f"re-ran {jid} (attempt {count + 1}/{MAX_HEAL_ATTEMPTS} in "
                           f"{HEAL_WINDOW_H}h)")
        else:
            escalations.append(f"{jid} heal launch failed: {detail}")
    return actions, escalations


def reconcile_conditions(findings, registry=None, outcomes: dict | None = None) -> list[dict]:
    """BROKEN->OK half of the alert gate. A job that audited OK clears its conditions; a
    green 'recovered' is returned only for jobs with POSITIVE evidence (a fresh ok/empty
    outcome sidecar) — a clean exit code alone is not a claim of recovery."""
    registry = _jobs.REGISTRY if registry is None else registry
    healthy = {jid for sev, jid, status, _ in findings if status == "OK"}
    healthy.discard(JOB_ID)          # self-loop never absolves itself
    if not healthy:
        return []
    cleared = hc.resolve_conditions(healthy)
    evidenced = set()
    for jid in healthy:
        oc = (outcomes or {}).get(jid) if outcomes is not None else hc.read_outcome(jid)
        if oc and oc.get("status") in ("ok", "empty") and oc.get("age_h") is not None:
            evidenced.add(hc._norm_job(jid))
    return [r for r in cleared if hc._norm_job((r or {}).get("job")) in evidenced]


def render(findings, actions, escalations, recovered, why: str) -> str:
    L = ["# self-loop cycle", "", f"Scheduler: {why}", ""]
    problems = [f for f in findings if f[0] in ("CRIT", "HIGH")]
    infos = [f for f in findings if f[0] == "INFO"]
    L += ["## Liveness (declared vs actual)"]
    L += [f"- [{s}] {jid}: {st} — {d}" for s, jid, st, d in problems] or \
         ["- all declared jobs installed, enabled and fresh"]
    if infos:
        L += ["", "## Notes"] + [f"- {jid}: {st} — {d}" for _, jid, st, d in infos]
    L += ["", "## Healed"] + ([f"- {a}" for a in actions] or ["- (nothing to heal)"])
    if recovered:
        L += ["", "## Recovered"] + [f"- {r.get('job', '?')} — was: {r.get('message', '')}"
                                     for r in recovered]
    L += ["", "## Escalated (needs a human)"] + ([f"- {e}" for e in escalations] or ["- (none)"])
    return "\n".join(L) + "\n"


def cycle(args, now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    installed, why = _intro.query()
    if installed is None:
        msg = f"audit BLIND: the scheduler could not be read ({why}) — this is not a healthy fleet"
        log("ERROR", msg)
        if not args.dry_run:
            hc.alert(JOB_ID, msg)
        hc.record_outcome(JOB_ID, status="error", produced=0, detail=msg)
        return 1
    if not installed:
        log("INFO", f"cycle: no harness jobs installed ({why}) — nothing to audit. "
                    f"Run bin/scheduler/install.py --apply")
        hc.record_outcome(JOB_ID, status="empty", produced=0, detail="no jobs installed")
        return 0

    state = _load_state()
    findings = audit(installed, now, _intro.system_uptime_h())
    actions, heal_escs = heal(findings, state, now, args.dry_run)
    escalations = [f"{jid}: {st} — {d}" for s, jid, st, d in findings if s in ("CRIT", "HIGH")]
    escalations += heal_escs

    def _subject(e: str) -> str:
        head = e.split(":", 1)[0].split(" ", 1)[0]
        return head if head in {j.id for j in _jobs.REGISTRY} else JOB_ID

    if args.dry_run:
        new_escs, recovered = list(escalations), []
    else:
        new_escs = [e for e in escalations if hc.mark_broken(_subject(e), e, fleet=True)]
        recovered = reconcile_conditions(findings)

    text = render(findings, actions, escalations, recovered, why)
    log("INFO", f"cycle: installed={len(installed)}/{len(_jobs.REGISTRY)} "
                f"problems={sum(1 for f in findings if f[0] in ('CRIT', 'HIGH'))} "
                f"healed={len(actions)} escalated={len(escalations)} new={len(new_escs)} "
                f"recovered={len(recovered)} dry={args.dry_run}")
    if not args.dry_run:
        try:
            FORGE.mkdir(parents=True, exist_ok=True)
            REPORT.write_text(text, encoding="utf-8")
            HEARTBEAT.write_text(now_iso, encoding="utf-8")   # proof of life for fleet_status
        except OSError as e:
            log("WARN", f"could not write report/heartbeat: {e}")
        state["last_cycle"] = now_iso
        hc.write_json_atomic(STATE_PATH, state)
        if new_escs:
            hc._append_alerts_log("[self-loop] " + " | ".join(new_escs)[:1000])
    if not args.quiet and not args.dry_run:
        if new_escs:
            hc._post(text, title="self-loop — needs a look")
        for rec in recovered:
            hc.alert_recovered(rec.get("job", "?"), f"recovered — was: {rec.get('message', '')}",
                               lambda m: log("INFO", m))
    hc.record_outcome(JOB_ID, status="ok", produced=1,
                      detail=f"{len(installed)} installed, {len(escalations)} escalation(s)")
    print(text)
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Fleet liveness auditor + mechanical healer.")
    ap.add_argument("--dry-run", action="store_true",
                    help="audit + liveness + would-heal; take no action, page nobody")
    ap.add_argument("--quiet", action="store_true", help="never post to Slack")
    args = ap.parse_args(argv)
    hc.set_dry_run(args.dry_run, "self_loop.py --dry-run")
    hc.rotate_log(LOG_PATH)
    if not hc.guard_or_skip(JOB_ID, lambda m: log("INFO", m)):
        return 0
    with hc.single_instance(JOB_ID) as ok:
        if not ok:
            log("INFO", "another self-loop instance holds the lock — skipping")
            return 0
        rc, err = 0, None
        try:
            rc = cycle(args)
        except Exception as e:  # noqa: BLE001
            rc, err = 1, repr(e)
            log("ERROR", f"cycle crashed: {err}")
        finally:
            hc.record_run(JOB_ID, status="ok" if rc == 0 else "error", halt_reason=err)
            if err:
                hc.record_outcome(JOB_ID, status="error", produced=0, detail=err)
        return rc


if __name__ == "__main__":
    sys.exit(main())
