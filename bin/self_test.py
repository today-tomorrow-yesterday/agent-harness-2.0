#!/usr/bin/env python3
"""self_test.py — the harness tests itself while nobody is at the keyboard.

Runs the full pytest suite (bin/tests), the claude-brain health check, and a
gbrain liveness probe — then writes a machine- and digest-readable report to
<repo>/self-test-report.md. The daily-digest surfaces the one-line verdict, so a
red self-test is seen within a day instead of weeks after a pipeline quietly died.

LLM-FREE (zero token cost): pure pytest + sqlite + a TCP probe.

Fresh-clone friendly: components that aren't set up yet (no brain DB, no gbrain
port file) report SKIPPED, not FAIL — a brand-new clone is green out of the box.

Usage:
    python bin/self_test.py            # run everything + write the report
    python bin/self_test.py --print    # also print the report to stdout
Exit: 0 = all green (skips allowed) · 1 = any component failed.

Wire it as a scheduled job (see bin/scheduler/jobs.py — the "self-test" entry;
schedule it BEFORE your daily-digest so every digest carries a fresh verdict).
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "self-test-report.md"
BRAIN_CONFIG = REPO / "claude-brain" / "config.yaml"
BRAIN_HEALTH = REPO / "claude-brain" / "scripts" / "brain_health.py"
GBRAIN_PORT_FILE = REPO / "logs" / "gbrain-serve.port"

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Component outcome: (status, detail) where status is "pass" | "fail" | "skip".


def run_pytest_suite() -> tuple[str, str]:
    """The whole bin/tests suite, exactly as CI/humans run it (pytest.ini applies)."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(REPO), timeout=1800)
    out = _ANSI.sub("", (r.stdout or "") + (r.stderr or "")).strip()
    tally = next((ln.strip() for ln in reversed(out.splitlines())
                  if "passed" in ln or "failed" in ln or "error" in ln),
                 out.splitlines()[-1] if out else "(no output)")
    return ("pass" if r.returncode == 0 else "fail", tally)


def run_brain_health() -> tuple[str, str]:
    """claude-brain's own health check — skipped until the brain is set up."""
    if not BRAIN_CONFIG.exists():
        return ("skip", "brain not set up (no claude-brain/config.yaml) — run brain-setup.py")
    r = subprocess.run([sys.executable, str(BRAIN_HEALTH)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(REPO), timeout=600)
    out = _ANSI.sub("", r.stdout or "")
    score = next((ln.strip() for ln in out.splitlines() if "Score:" in ln), "Score: ?")
    score = "".join(ch for ch in score if ch.isprintable()).strip("│ ").strip()
    return ("pass" if (r.returncode == 0 and "FAIL" not in out) else "fail", score)


def probe_gbrain() -> tuple[str, str]:
    """TCP-connect to the port gbrain-serve recorded — skipped if gbrain isn't used."""
    if not GBRAIN_PORT_FILE.exists():
        return ("skip", "gbrain not set up (no logs/gbrain-serve.port)")
    try:
        port = int(GBRAIN_PORT_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as e:
        return ("fail", f"port file unreadable ({e})")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            return ("pass", f"listening on {port}")
    except OSError as e:
        return ("fail", f"port {port} unreachable ({e})")


def main() -> int:
    try:  # Windows consoles default to cp1252 — glyphs below would crash prints
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Run the harness self-test and write the report.")
    ap.add_argument("--print", dest="print_only", action="store_true",
                    help="Also print the report to stdout.")
    args = ap.parse_args()

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    components = [
        ("Test suite (bin/tests)", run_pytest_suite),
        ("Brain health (claude-brain)", run_brain_health),
        ("gbrain server", probe_gbrain),
    ]

    results: list[tuple[str, str, str]] = []
    for name, fn in components:
        try:
            status, detail = fn()
        except Exception as e:  # a crashed check is a failed check, never a crashed report
            status, detail = "fail", f"check crashed: {e}"
        results.append((name, status, detail))
        print(f"[self-test] {status.upper():4s}  {name} — {detail.splitlines()[-1] if detail else ''}",
              file=sys.stderr)

    all_ok = all(s != "fail" for _, s, _ in results)
    verdict = "PASS" if all_ok else "FAIL"
    glyph = {"pass": "✅ PASS", "fail": "🔴 FAIL", "skip": "⚪ SKIPPED"}

    lines = [
        f"# Self-test report — {now}",
        "",
        f"**VERDICT: {verdict}**",
        "",
        "| Component | Status | Detail |",
        "|---|---|---|",
    ]
    for name, status, detail in results:
        d = (detail or "").replace("|", "\\|").replace("\n", " · ")[:220]
        lines.append(f"| {name} | {glyph[status]} | {d} |")
    lines += [
        "",
        "_Written by `bin/self_test.py`. Schedule it daily (see bin/scheduler/jobs.py) — "
        "the daily-digest surfaces this verdict._",
    ]
    try:
        REPORT.write_text("\n".join(lines), encoding="utf-8")
    except OSError as e:
        print(f"[self-test] could not write {REPORT}: {e}", file=sys.stderr)
        return 1

    if args.print_only:
        print("\n".join(lines))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
