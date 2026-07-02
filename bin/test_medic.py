#!/usr/bin/env python3
"""test_medic.py — OPT-IN autonomous repair for a red self-test.

The third layer of the harness's health chain:
  detect (bin/self_test.py, daily) -> heal-mechanical (re-runs/restarts) -> FIX-CODE (this).

READ THE TRUST MODEL in README.md before scheduling this. Unlike everything else
in the harness, the medic grants an unattended agent WRITE access to your repo.
The safety comes from three mechanisms, none of which is "trust the model":
  1. REPAIR CONTRACT (prompt): no VCS mutation, never delete/weaken a test to go
     green, smallest-diff root-cause fixes, escalate judgment calls.
  2. HEAD VERIFICATION (runner): the repo's git HEAD is recorded before and after
     the attempt — a moved HEAD flags the report as a hard-rule violation.
  3. DETERMINISTIC VERDICT (runner): self_test.py is re-run by THIS script after
     the repair; only a green re-run counts as FIXED. The model's own claim of
     success is never trusted.

CYCLE (one attempt per scheduled run — anti-thrash by design):
  1. Run bin/self_test.py. GREEN -> log + exit (no claude call, near-zero cost).
  2. RED  -> collect the failing output as a diagnosis bundle.
  3. One headless `claude -p` repair attempt (subscription OAuth — no API bill).
  4. Re-run self_test.py; report FIXED or ESCALATED to <repo>/forge/test-medic-latest.md
     and (if configured) Slack. Still red -> a human fixes it; the medic waits
     for its next scheduled slot.

Also honors the global kill-switch (forge/STOP) and backs off cleanly on a
rate-limit (retries at the next scheduled slot, never hammers a closed window).

Enable by uncommenting the "test-medic" Job in bin/scheduler/jobs.py.
Usage: python bin/test_medic.py [--dry-run]   (--dry-run: diagnose only, no claude call)
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SELF_TEST = REPO / "bin" / "self_test.py"
REPORT = REPO / "forge" / "test-medic-latest.md"
LOG_PATH = REPO / "logs" / "test-medic.log"
SELFTEST_REPORT = REPO / "self-test-report.md"

CLAUDE_TIMEOUT_S = 25 * 60

sys.path.insert(0, str(REPO / "bin"))
from runner.stop import is_engaged  # noqa: E402  (kill-switch: forge/STOP)


def log(level: str, message: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{ts} [{level}] {message}\n")
    print(f"{ts} [{level}] {message}", file=sys.stderr)


def classify_claude_result(returncode: int, stdout: str = "", stderr: str = "") -> str:
    """Classify a `claude -p` outcome: ok | auth_failed | rate_limited |
    model_unavailable | error. Only inspects output when the call FAILED —
    a successful answer may itself mention 'rate limit'."""
    if returncode == 0:
        return "ok"
    blob = f"{stdout}\n{stderr}".lower()
    if "401" in blob and ("auth" in blob or "credential" in blob):
        return "auth_failed"
    if "rate limit" in blob or "usage limit" in blob or "session limit" in blob or "spend limit" in blob:
        return "rate_limited"
    if "overloaded" in blob or "unavailable" in blob:
        return "model_unavailable"
    return "error"


def run_self_test() -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(SELF_TEST)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(REPO), timeout=2400)
    return r.returncode == 0, ((r.stdout or "") + "\n" + (r.stderr or "")).strip()


def collect_diagnosis() -> str:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(REPO), timeout=2400)
    pytest_out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
    report = SELFTEST_REPORT.read_text(encoding="utf-8", errors="replace") \
        if SELFTEST_REPORT.exists() else "(no report)"
    return f"=== self-test-report.md ===\n{report}\n\n=== pytest output ===\n{pytest_out[-12000:]}"


def repo_head() -> str:
    try:
        r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else "(no-git)"
    except Exception:
        return "(err)"


def invoke_medic(diagnosis: str) -> tuple[str, str]:
    claude_path = shutil.which("claude") or shutil.which("claude.exe") or shutil.which("claude.cmd")
    if not claude_path:
        return ("error", "claude CLI not found on PATH")

    prompt = f"""You are the TEST MEDIC for this repository ({REPO}).
The scheduled self-test is RED. Your one job: make it GREEN by fixing the ROOT CAUSE
with the smallest possible change, then verify by re-running the failing suite.

HARD RULES (violating any of these is worse than leaving the test red):
1. NEVER run `git commit`, `git push`, `git add`, or any VCS mutation. Read-only git is fine.
2. NEVER delete a test, skip a test, or weaken an assertion just to make it pass.
   If the TEST is what's wrong (stale expectation after an intentional change), fix the
   test minimally and leave a dated comment explaining why.
3. Fix root causes, not symptoms. Smallest diff that genuinely fixes it.
4. If the failure requires human judgment — credentials, API/spend limits, policy calls,
   external services being down, anything irreversible — do NOT force a fix. Write your
   findings to {REPO / 'forge' / 'test-medic-escalation.md'} and stop.
5. Windows: any Python you write that prints non-ASCII must reconfigure stdout to utf-8.

PROCESS:
1. Read the diagnosis below; reproduce the failure (`python -m pytest <file> -q` from the repo root).
2. Investigate and apply the minimal fix.
3. Re-run the failing test file, then the whole suite: `python -m pytest -q`.
4. End your final message with exactly one line: `MEDIC: FIXED` or `MEDIC: ESCALATED`,
   followed by a one-paragraph summary of what you changed (files + why).

=== DIAGNOSIS ===
{diagnosis}
"""
    try:
        result = subprocess.run(
            [claude_path, "-p",
             "--no-session-persistence",
             "--allowed-tools", "Read Write Edit Glob Grep Bash",
             "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(REPO), timeout=CLAUDE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return ("timeout", f"claude timed out after {CLAUDE_TIMEOUT_S}s")
    except Exception as e:
        return ("error", f"claude launch failed: {e}")

    status = classify_claude_result(result.returncode, result.stdout or "", result.stderr or "")
    return (status, (result.stdout or result.stderr or "").strip()[-3000:])


def write_report(outcome: str, sections: list[tuple[str, str]]) -> None:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Test-Medic run — {now}", "", f"**OUTCOME: {outcome}**", ""]
    for title, body in sections:
        lines += [f"## {title}", "", body.strip()[:6000], ""]
    lines.append("_Written by bin/test_medic.py. One attempt per run; still-red escalates to you._")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def notify(msg: str) -> None:
    try:
        from notify_slack import post_slack
        post_slack(msg)
    except Exception:
        pass


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Autonomous repair for a red self-test (opt-in).")
    ap.add_argument("--dry-run", action="store_true", help="diagnose only; no claude call")
    args = ap.parse_args()

    if is_engaged():
        log("INFO", "STOP engaged (forge/STOP) — skipping run.")
        return 0

    log("INFO", "test-medic start — running self-test for a fresh verdict")
    green, _ = run_self_test()
    if green:
        log("INFO", "self-test GREEN — nothing to fix.")
        write_report("GREEN (no action)", [("Verdict", "Self-test passed; no repair attempted.")])
        return 0

    log("WARN", "self-test RED — collecting diagnosis")
    diagnosis = collect_diagnosis()
    if args.dry_run:
        write_report("RED (dry-run, no repair)", [("Diagnosis", diagnosis)])
        return 1

    head_before = repo_head()
    status, tail = invoke_medic(diagnosis)
    head_after = repo_head()
    head_moved = head_before != head_after

    if head_moved:
        log("ERROR", f"HARD-RULE VIOLATION: repo HEAD moved during medic run: {head_before} -> {head_after}")

    if status == "rate_limited":
        log("WARN", "rate-limited — will retry next scheduled slot.")
        write_report("SKIPPED (rate-limited)", [("Detail", tail[:1000])])
        return 0
    if status in ("auth_failed", "timeout", "error", "model_unavailable"):
        log("ERROR", f"medic invocation failed [{status}]")
        write_report(f"FAILED ({status})", [("Detail", tail), ("Diagnosis", diagnosis)])
        notify(f"Test-Medic could not run ({status}) — self-test still RED. See forge/test-medic-latest.md")
        return 1

    # Deterministic verdict — never trust the model's own claim.
    green_after, verify_out = run_self_test()
    outcome = "FIXED (verified green)" if green_after else "STILL RED — escalated"
    sections = [("Medic summary (model's final message)", tail),
                ("Deterministic re-verify", verify_out[-1500:])]
    if head_moved:
        outcome += " — WARNING: repo HEAD moved (hard-rule violation, review!)"
        sections.insert(0, ("HEAD violation", f"{head_before} -> {head_after}"))
    write_report(outcome, sections)
    log("INFO" if green_after else "ERROR", f"test-medic done — {outcome}")
    notify(("Test-Medic fixed the red self-test (verified green). "
            if green_after else
            "Test-Medic attempted a fix but self-test is STILL RED — needs a human. ")
           + "Report: forge/test-medic-latest.md")
    return 0 if green_after else 1


if __name__ == "__main__":
    sys.exit(main())
