"""Fleet-integrity guard: the scheduled-job registry can never silently rot.

The classic failure mode of unattended automation is SILENT: a registry entry
points at a script that moved, the script stops compiling, or the installed
task quietly stops firing — and nothing notices until the pipeline has been
dead for weeks. This suite locks each layer, deriving everything from
bin/scheduler/jobs.py (the single source of truth) so it never drifts from
what install.py actually installs.

Layers:
  1. every REGISTRY job's script EXISTS at its repo-relative path,
  2. Python job scripts COMPILE,
  3. (Windows + installed only) the task is REGISTERED and not disabled, and
     has FIRED within its cadence window (heartbeat). These skip gracefully on
     other OSes or before `install.py --apply` — a fresh clone stays green.
"""
from __future__ import annotations

import json
import platform
import py_compile
import subprocess
from pathlib import Path

import pytest

from scheduler import jobs as _jobs

REPO = _jobs.repo_root()
REGISTRY = _jobs.REGISTRY

# cadence -> max days since last run before we call the task silently dead.
HEARTBEAT_DAYS = {"daily": 3, "weekly": 9}

IS_WINDOWS = platform.system().lower() == "windows"


def test_registry_is_not_empty():
    assert REGISTRY, "scheduler REGISTRY is empty — nothing runs unattended"


def test_every_job_script_exists():
    missing = [f"{j.id} -> {j.args[0]}" for j in REGISTRY if not (REPO / j.args[0]).exists()]
    assert not missing, "REGISTRY jobs point at missing scripts:\n  " + "\n  ".join(missing)


def test_python_job_scripts_compile():
    bad = []
    for j in REGISTRY:
        script = REPO / j.args[0]
        if script.suffix == ".py" and script.exists():
            try:
                py_compile.compile(str(script), doraise=True)
            except py_compile.PyCompileError as e:
                bad.append(f"{j.id}: {str(e).splitlines()[-1]}")
    assert not bad, "job scripts do not compile:\n  " + "\n  ".join(bad)


def test_job_ids_are_unique():
    ids = [j.id for j in REGISTRY]
    assert len(ids) == len(set(ids)), f"duplicate job ids: {ids}"


# ── installed-state checks (Windows-only, and only once tasks are installed) ──

def _query_installed() -> dict:
    """One batched PowerShell query for all agent-harness-* tasks (25x faster
    than per-task calls). Returns {} when nothing is installed."""
    names = [f"agent-harness-{j.id}" for j in REGISTRY]
    ps = (
        "$out=@{}; foreach ($n in @(" + ",".join(f"'{n}'" for n in names) + ")) {"
        "  $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue;"
        "  $i = Get-ScheduledTaskInfo -TaskName $n -ErrorAction SilentlyContinue;"
        "  if ($t) { $out[$n] = @{ state = [string]$t.State;"
        "    lastRun = if ($i.LastRunTime) { $i.LastRunTime.ToString('o') } else { '' } } } }"
        " $out | ConvertTo-Json -Depth 3"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not r.stdout.strip():
        return {}
    data = json.loads(r.stdout)
    return data if isinstance(data, dict) else {}


@pytest.fixture(scope="module")
def installed():
    if not IS_WINDOWS:
        pytest.skip("installed-task checks are Windows-only (cron/launchd not covered yet)")
    tasks = _query_installed()
    if not tasks:
        pytest.skip("no agent-harness tasks installed yet (run bin/scheduler/install.py --apply)")
    return tasks


def test_installed_tasks_not_disabled(installed):
    disabled = [n for n, t in installed.items() if t.get("state") == "Disabled"]
    assert not disabled, f"installed harness tasks are disabled: {disabled}"


def test_installed_tasks_fired_within_cadence(installed):
    """The silent-death heartbeat. Never asserts on exit codes (rate limits etc.
    are environmental); only that the scheduler is actually FIRING the task."""
    from datetime import datetime, timedelta
    now = datetime.now().astimezone()
    stale = []
    for j in REGISTRY:
        t = installed.get(f"agent-harness-{j.id}")
        if not t:
            continue  # partially installed — existence isn't this test's concern
        raw = t.get("lastRun") or ""
        if not raw or raw.startswith("1999"):
            continue  # never fired yet — legitimate right after install
        last = datetime.fromisoformat(raw)
        if now - last > timedelta(days=HEARTBEAT_DAYS[j.cadence]):
            stale.append(f"{j.id}: last ran {last:%Y-%m-%d} ({(now - last).days}d ago, cadence={j.cadence})")
    assert not stale, "tasks appear to have STOPPED FIRING:\n  " + "\n  ".join(stale)
