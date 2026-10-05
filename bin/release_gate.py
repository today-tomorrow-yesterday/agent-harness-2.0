#!/usr/bin/env python3
"""release_gate.py — one command, deterministic, before a change ships.

Runs the harness's existing deterministic checks as a single pass/fail and requires 100%:

  self-test     bin/self_test.py — the full test suite + component health (skips allowed)
  skill-canary  bin/skill_canary.py --check-all — every repo skill is invokable and its
                helper scripts compile
  conformance   bin/conformance_check.py --dry-run --exit-nonzero-on-fail — no structural
                invariant FAILs and no assertion is BLIND

Zero LLM calls. Appends one audit record per run to forge/eval_runs.jsonl.

    python bin/release_gate.py
    python bin/release_gate.py --dry-run    # list the checks; run nothing, write nothing

Exit 0 only when every check passed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EVAL_LOG = REPO / "forge" / "eval_runs.jsonl"


def checks() -> list[tuple[str, list[str], int]]:
    py, b = sys.executable, REPO / "bin"
    return [
        ("self-test", [py, str(b / "self_test.py")], 2400),
        ("skill-canary", [py, str(b / "skill_canary.py"), "--check-all"], 300),
        ("conformance", [py, str(b / "conformance_check.py"), "--dry-run",
                         "--exit-nonzero-on-fail"], 300),
    ]


def run_check(cmd: list[str], timeout: int, runner=subprocess.run) -> tuple[bool, str]:
    try:
        p = runner(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=timeout,
                   encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except Exception as e:  # noqa: BLE001
        return False, f"could not run: {e!r}"[:200]
    out = (p.stdout or "").strip() or (p.stderr or "").strip()
    last = out.splitlines()[-1] if out else ("passed" if p.returncode == 0 else "failed")
    return p.returncode == 0, f"exit {p.returncode} — {last[:160]}"


def gate(runner=subprocess.run, log_path: Path | None = None) -> bool:
    results, all_ok = [], True
    for name, cmd, timeout in checks():
        ok, summary = run_check(cmd, timeout, runner)
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<13} {summary}")
        results.append({"check": name, "passed": ok, "summary": summary})
        all_ok = all_ok and ok
    rec = {"timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "all_passed": all_ok, "total_checks": len(results),
           "passed_checks": sum(r["passed"] for r in results), "results": results}
    log_path = log_path or EVAL_LOG
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError as e:
        print(f"could not append to {log_path.name}: {e}", file=sys.stderr)
    print("RELEASE GATE " + ("PASSED" if all_ok else "FAILED")
          + f" ({rec['passed_checks']}/{rec['total_checks']})")
    return all_ok


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Unified deterministic release gate.")
    ap.add_argument("--dry-run", action="store_true", help="list the checks; run nothing")
    args = ap.parse_args(argv)
    if args.dry_run:
        for name, cmd, timeout in checks():
            print(f"{name:<13} {' '.join(Path(c).name for c in cmd[1:])}  (timeout {timeout}s)")
        return 0
    return 0 if gate() else 1


if __name__ == "__main__":
    sys.exit(main())
