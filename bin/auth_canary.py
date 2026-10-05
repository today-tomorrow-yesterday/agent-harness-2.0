#!/usr/bin/env python3
"""auth_canary.py — does `claude -p` still authenticate from where the scheduler runs it?

Every scheduled job that calls `claude -p` depends on the subscription login being usable
from an unattended session: a cron job with no TTY, a launchd agent, a Windows task that
runs whether or not anyone is logged on. That is easy to assume and expensive to discover
wrong — every such job exits early and the fleet looks idle rather than broken. This
canary OBSERVES it instead of reasoning about it, and keeps three questions separate:

  1. Did it execute at all from this context?        (the verdict file exists)
  2. Is this an interactive session or a background one?   (tri-state, see below)
  3. Does `claude -p` authenticate here?              (one tiny call on the subscription)

Run it once from the scheduler (or wire it as a job) and read forge/auth-canary.json.
The call goes through harness_common.clean_env, so a metered API key in the environment
can never make it "pass" on per-token billing.

Interactive-ness is TRI-STATE on purpose: None means the probe could not tell. Collapsing
"unknown" into "not interactive" would make an interactive control run look like proof.
  Windows: whoami /groups — the INTERACTIVE well-known group (S-1-5-4) is present only in
           interactive logons.
  macOS / Linux: no equivalent group exists; reported as None with the reason, plus
           whether stdin is a TTY (cron and launchd jobs have none).

    python bin/auth_canary.py            # probe + one `claude -p` call
    python bin/auth_canary.py --dry-run  # probe the session only; no call, no file written

Exit 0 on PASS, 1 otherwise.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import harness_common as hc  # noqa: E402

OUT = ROOT / "forge" / "auth-canary.json"
PROMPT = "Reply with exactly: OK"
TIMEOUT_S = 180


def probe_session(runner=subprocess.run, os_name: str | None = None) -> dict:
    out = {"interactive": None, "reason": "", "stdin_tty": None, "error": None}
    try:
        out["stdin_tty"] = bool(sys.stdin and sys.stdin.isatty())
    except Exception:  # noqa: BLE001
        out["stdin_tty"] = None
    os_name = (os_name or platform.system()).lower()
    if os_name != "windows":
        out["reason"] = (f"{os_name}: no interactive-logon group to test; see stdin_tty "
                         f"(cron/launchd jobs have no TTY)")
        return out
    try:
        # The System32 whoami: a POSIX-layer `whoami` earlier on PATH (Git Bash, MSYS)
        # does not understand /groups.
        sysroot = os.environ.get("SystemRoot")
        exe = str(Path(sysroot) / "System32" / "whoami.exe") if sysroot else "whoami"
        r = runner([exe, "/groups", "/fo", "csv", "/nh"],
                   capture_output=True, text=True, timeout=30)
        # Only trust a verdict when the probe actually produced group output.
        if r.returncode == 0 and "S-1-5-" in (r.stdout or ""):
            out["interactive"] = "S-1-5-4" in r.stdout
            out["reason"] = "whoami /groups: INTERACTIVE group (S-1-5-4) " + \
                ("present" if out["interactive"] else "absent")
        else:
            out["reason"] = f"whoami /groups gave no usable output (rc={r.returncode})"
    except Exception as exc:  # noqa: BLE001
        out["error"] = repr(exc)[:200]
        out["reason"] = "whoami probe failed"
    return out


def call_claude(runner=subprocess.run) -> dict:
    exe = hc._claude_bin()
    res = {"claude_found": bool(exe), "rc": None, "status": None, "stdout": "", "verdict": ""}
    if not exe:
        res["verdict"] = "FAIL: claude CLI not found on PATH in this session"
        return res
    try:
        r = runner([exe, "-p", PROMPT], capture_output=True, text=True, timeout=TIMEOUT_S,
                   env=hc.clean_env(CLAUDE_BRAIN_SKIP_HOOKS="1"), stdin=subprocess.DEVNULL,
                   encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        res["verdict"] = f"FAIL: claude timed out after {TIMEOUT_S}s"
        return res
    except Exception as exc:  # noqa: BLE001
        res["verdict"] = f"FAIL: {exc!r}"[:200]
        return res
    status, detail = hc.classify_claude_result(r.returncode, r.stdout or "", r.stderr or "")
    res.update(rc=r.returncode, status=status,
               stdout=hc.scrub_secrets((r.stdout or "")[:500]))
    if status == "ok" and "OK" in (r.stdout or ""):
        res["verdict"] = "PASS: executed and authenticated on the subscription"
    elif status == "ok":
        res["verdict"] = "PARTIAL: rc=0 but no OK in the reply — inspect stdout"
    else:
        res["verdict"] = f"FAIL: {status}" + (f" ({detail})" if detail else "")
    return res


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Observe whether claude -p authenticates here.")
    ap.add_argument("--dry-run", action="store_true",
                    help="probe the session only; no claude call, no file written")
    args = ap.parse_args(argv)
    hc.set_dry_run(args.dry_run, "auth_canary.py --dry-run")
    started = time.time()
    result = {
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform": platform.system(),
        "user": getpass.getuser(),
        "session": probe_session(),
    }
    if args.dry_run:
        result["claude"] = {"verdict": "NOT RUN: dry run — authentication was not tested"}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    result["claude"] = call_claude()
    result["verdict"] = result["claude"]["verdict"]
    result["elapsed_s"] = round(time.time() - started, 1)
    hc.write_json_atomic(OUT, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    ok = str(result["verdict"]).startswith("PASS")
    if ok:
        hc.resolve_conditions(["auth-canary"])
    else:
        hc.alert("auth-canary", f"claude -p did not authenticate from this context: "
                                f"{result['verdict']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
