"""Read back what the OS scheduler ACTUALLY has installed for this harness.

`install.py` writes jobs; this module answers "what is really there?" on every OS, so
the health programs (self_loop, verify_scheduled_tasks, conformance_check,
harness_metrics) can compare the declared REGISTRY against reality.

Every harness entry is tagged by install.py, which is what makes this possible without
an allowlist of names:
    Linux    crontab line ending in      `# agent-harness:<id>`
    macOS    ~/Library/LaunchAgents/agent-harness.<id>.plist  (label agent-harness.<id>)
    Windows  Task Scheduler task named   agent-harness-<id>

What each OS can tell us differs, and the gaps are reported as None, never guessed:
    field         Linux (cron)        macOS (launchd)            Windows (schtasks)
    installed     yes                 yes (plist present)        yes
    disabled      commented-out line  plist present, not loaded  task State=Disabled
    time / dow    yes                 yes                        yes
    last_run      None (cron keeps    None                       yes
                  no run history)
    last_result   None                last exit status           yes
    running       None                PID present                State=Running

`query()` returns (None, reason) when the scheduler cannot be read at all — callers must
treat that as BLIND, never as "nothing installed". An unreadable scheduler and an empty
one are different facts.

The Windows path uses PowerShell's ScheduledTasks module (guarded by OS); macOS uses
`launchctl`; Linux uses `crontab -l`. Pure parsers are split out so they are unit-tested
on any platform.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import plistlib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

TAG = "agent-harness"
_DOW_NAMES = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")   # cron/launchd numbering


@dataclass
class Installed:
    id: str
    state: str = "Ready"          # Ready | Disabled | Running | Unknown
    time: str | None = None       # "HH:MM"
    dow: str | None = None        # MON..SUN for weekly, else None
    last_run: dt.datetime | None = None      # timezone-aware, or None if not tracked
    last_result: int | None = None
    next_run: dt.datetime | None = None
    notes: list[str] = field(default_factory=list)


def detect_os(name: str | None = None) -> str:
    s = (name or platform.system()).lower()
    return {"darwin": "macos", "linux": "linux", "windows": "windows"}.get(s, s)


def parse_iso(raw: str | None) -> dt.datetime | None:
    """Parse an ISO timestamp (tolerating 7-digit fractions and a trailing Z) into an
    AWARE datetime; naive input is taken as local time. None for blank/sentinel/garbage."""
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.year < 2000:            # Task Scheduler's 1999-11-30 "never ran" sentinel
        return None
    return d if d.tzinfo else d.astimezone()


# --------------------------------------------------------------------------- Linux
def parse_crontab(text: str) -> dict[str, Installed]:
    """Pure: harness entries in `crontab -l` output. A line that has been commented out
    (`# 0 8 * * * ... # agent-harness:x`) is reported Disabled, not missing."""
    out: dict[str, Installed] = {}
    for line in (text or "").splitlines():
        m = re.search(rf"#\s*{TAG}:([A-Za-z0-9_.\-]+)\s*$", line)
        if not m:
            continue
        jid = m.group(1)
        body = line[:m.start()].strip()
        disabled = body.startswith("#")
        body = body.lstrip("#").strip()
        fields = body.split()
        inst = Installed(jid, state="Disabled" if disabled else "Ready")
        if len(fields) >= 5 and fields[0].isdigit() and fields[1].isdigit():
            inst.time = f"{int(fields[1]):02d}:{int(fields[0]):02d}"
            if fields[4] != "*" and fields[4].isdigit():
                inst.dow = _DOW_NAMES[int(fields[4]) % 7]
        else:
            inst.notes.append("unparseable schedule fields")
        out[jid] = inst
    return out


def _query_linux(runner) -> tuple[dict[str, Installed] | None, str]:
    try:
        r = runner(["crontab", "-l"], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return None, "crontab command not found"
    except Exception as e:  # noqa: BLE001
        return None, f"crontab -l failed: {e!r}"
    if r.returncode != 0:
        if "no crontab" in (r.stderr or "").lower():
            return {}, "user has no crontab"
        return None, f"crontab -l exited {r.returncode}: {(r.stderr or '').strip()[:160]}"
    return parse_crontab(r.stdout or ""), "crontab read"


# --------------------------------------------------------------------------- macOS
def parse_launchctl_list(text: str) -> dict[str, tuple[str, str]]:
    """Pure: `launchctl list` rows -> {label: (pid, status)}."""
    out: dict[str, tuple[str, str]] = {}
    for line in (text or "").splitlines():
        parts = line.split("\t") if "\t" in line else line.split()
        if len(parts) >= 3 and parts[2].startswith(f"{TAG}."):
            out[parts[2]] = (parts[0], parts[1])
    return out


def parse_plist_schedule(data: bytes) -> tuple[str | None, str | None]:
    d = plistlib.loads(data)
    sci = d.get("StartCalendarInterval") or {}
    if isinstance(sci, list):
        sci = sci[0] if sci else {}
    t = None
    if "Hour" in sci:
        t = f"{int(sci['Hour']):02d}:{int(sci.get('Minute', 0)):02d}"
    dow = _DOW_NAMES[int(sci["Weekday"]) % 7] if "Weekday" in sci else None
    return t, dow


def _query_macos(runner, agents_dir: Path | None = None) -> tuple[dict[str, Installed] | None, str]:
    la = agents_dir or (Path.home() / "Library" / "LaunchAgents")
    out: dict[str, Installed] = {}
    try:
        plists = sorted(la.glob(f"{TAG}.*.plist")) if la.is_dir() else []
    except OSError as e:
        return None, f"cannot list {la}: {e}"
    try:
        r = runner(["launchctl", "list"], capture_output=True, text=True, timeout=30)
        loaded = parse_launchctl_list(r.stdout or "") if r.returncode == 0 else None
    except Exception:  # noqa: BLE001
        loaded = None
    for p in plists:
        jid = p.name[len(TAG) + 1:-len(".plist")]
        inst = Installed(jid)
        try:
            inst.time, inst.dow = parse_plist_schedule(p.read_bytes())
        except Exception as e:  # noqa: BLE001
            inst.state = "Unknown"
            inst.notes.append(f"plist unreadable: {e!r}"[:120])
        if loaded is None:
            inst.notes.append("launchctl list unavailable — load state unknown")
        else:
            row = loaded.get(f"{TAG}.{jid}")
            if row is None:
                inst.state = "Disabled"
                inst.notes.append("plist present but not loaded")
            else:
                pid, status = row
                if pid not in ("-", ""):
                    inst.state = "Running"
                try:
                    inst.last_result = int(status)
                except ValueError:
                    pass
        out[jid] = inst
    return out, f"{len(plists)} plist(s) in {la.name}"


# --------------------------------------------------------------------------- Windows
_WIN_DOW_BITS = {1: "SUN", 2: "MON", 4: "TUE", 8: "WED", 16: "THU", 32: "FRI", 64: "SAT"}


def parse_windows_json(text: str) -> dict[str, Installed]:
    """Pure: the JSON emitted by _WIN_PS below -> {id: Installed}."""
    data = json.loads(text) if (text or "").strip() else []
    if isinstance(data, dict):
        data = [data]
    out: dict[str, Installed] = {}
    for t in data or []:
        name = str(t.get("Name", ""))
        if not name.startswith(f"{TAG}-"):
            continue
        jid = name[len(TAG) + 1:]
        inst = Installed(jid, state=str(t.get("State") or "Unknown"))
        inst.last_run = parse_iso(t.get("LastRun"))
        inst.next_run = parse_iso(t.get("NextRun"))
        try:
            inst.last_result = int(t.get("LastResult")) if t.get("LastResult") is not None else None
        except (TypeError, ValueError):
            inst.last_result = None
        start = parse_iso(t.get("Start"))
        if start:
            inst.time = f"{start.hour:02d}:{start.minute:02d}"
        try:
            bits = int(t.get("Days") or 0)
        except (TypeError, ValueError):
            bits = 0
        days = [n for b, n in _WIN_DOW_BITS.items() if bits & b]
        if len(days) == 1:
            inst.dow = days[0]
        out[jid] = inst
    return out


_WIN_PS = (
    f"$ts = Get-ScheduledTask -TaskName '{TAG}-*' -ErrorAction SilentlyContinue; "
    "@($ts | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; $tr = $_.Triggers | Select-Object -First 1; "
    "[pscustomobject]@{ Name=$_.TaskName; State=$_.State.ToString(); "
    "LastRun=$(if ($i.LastRunTime) { $i.LastRunTime.ToString('o') } else { '' }); "
    "NextRun=$(if ($i.NextRunTime) { $i.NextRunTime.ToString('o') } else { '' }); "
    "LastResult=[int64]($i.LastTaskResult -band 0xFFFFFFFF); "
    "Start=$(if ($tr) { [string]$tr.StartBoundary } else { '' }); "
    "Days=$(if ($tr -and $tr.DaysOfWeek) { [int]$tr.DaysOfWeek } else { 0 }) } }) "
    "| ConvertTo-Json -Compress -Depth 3; exit 0"
)


def _query_windows(runner) -> tuple[dict[str, Installed] | None, str]:
    try:
        r = runner(["powershell", "-NoProfile", "-NonInteractive", "-Command", _WIN_PS],
                   capture_output=True, text=True, timeout=120,
                   encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None, "powershell not found"
    except Exception as e:  # noqa: BLE001
        return None, f"scheduler query failed: {e!r}"
    if r.returncode != 0:
        return None, f"scheduler query exited {r.returncode}: {(r.stderr or '').strip()[:160]}"
    try:
        return parse_windows_json(r.stdout or ""), "Task Scheduler read"
    except (ValueError, TypeError) as e:
        return None, f"scheduler output unparseable: {e}"


def query(os_name: str | None = None, runner=None) -> tuple[dict[str, Installed] | None, str]:
    """(installed, reason). installed is None when the scheduler could not be read."""
    runner = runner or subprocess.run
    os_name = detect_os(os_name)
    if os_name == "linux":
        return _query_linux(runner)
    if os_name == "macos":
        return _query_macos(runner)
    if os_name == "windows":
        return _query_windows(runner)
    return None, f"unsupported OS {os_name!r}"


# --------------------------------------------------------------------------- reconcile
def reconcile(registry, installed: dict[str, Installed]) -> list[tuple[str, str, str, str]]:
    """Pure: declared REGISTRY vs installed -> [(severity, kind, job_id, detail)].

    severity is "FAIL" (the registry promises something that is not there, or the other
    way round) or "WARN" (present but drifted)."""
    out: list[tuple[str, str, str, str]] = []
    declared = {j.id: j for j in registry}
    for jid in sorted(declared):
        if jid not in installed:
            out.append(("FAIL", "DECLARED-NOT-INSTALLED", jid,
                        "in REGISTRY but not installed — re-run install.py --apply"))
    for jid in sorted(installed):
        if jid not in declared:
            out.append(("FAIL", "INSTALLED-NOT-DECLARED", jid,
                        "installed but missing from REGISTRY — it runs unaudited; "
                        "add it to jobs.py or remove it"))
    for jid in sorted(set(declared) & set(installed)):
        j, inst = declared[jid], installed[jid]
        if inst.state == "Disabled":
            out.append(("WARN", "DISABLED", jid, "installed but disabled"
                        + (f" ({'; '.join(inst.notes)})" if inst.notes else "")))
        if inst.time and inst.time != j.time:
            out.append(("WARN", "SCHEDULE-MISMATCH", jid,
                        f"REGISTRY says {j.time}, scheduler says {inst.time}"))
        want_dow = j.dow if j.cadence == "weekly" else None
        if inst.time and (inst.dow or None) != (want_dow or None):
            out.append(("WARN", "SCHEDULE-MISMATCH", jid,
                        f"REGISTRY day {want_dow or 'daily'}, scheduler day {inst.dow or 'daily'}"))
    return out


# --------------------------------------------------------------------------- heal helper
def run_now(job, os_name: str | None = None, repo: Path | None = None,
            python: str | None = None, runner=None) -> tuple[bool, str]:
    """Trigger one immediate run of `job` through the native scheduler where it can do
    that (Windows `schtasks /Run`, macOS `launchctl start`); on Linux cron has no
    run-now, so the job's argv is launched directly as a detached process."""
    runner = runner or subprocess.run
    os_name = detect_os(os_name)
    try:
        if os_name == "windows":
            r = runner(["schtasks", "/Run", "/TN", f"{TAG}-{job.id}"],
                       capture_output=True, text=True, timeout=60)
            return r.returncode == 0, (r.stderr or r.stdout or "").strip()[:160]
        if os_name == "macos":
            r = runner(["launchctl", "start", f"{TAG}.{job.id}"],
                       capture_output=True, text=True, timeout=60)
            return r.returncode == 0, (r.stderr or r.stdout or "").strip()[:160]
        if os_name == "linux":
            repo = repo or Path(__file__).resolve().parents[2]
            argv = [python or sys.executable, *[str(repo / a) for a in job.args]]
            logs = repo / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            with open(logs / f"{job.id}.heal.log", "a", encoding="utf-8") as fh:
                subprocess.Popen(argv, cwd=str(repo), stdout=fh, stderr=fh,
                                 start_new_session=True)
            return True, "launched directly (cron has no run-now)"
    except Exception as e:  # noqa: BLE001
        return False, repr(e)[:160]
    return False, f"unsupported OS {os_name!r}"


def system_uptime_h() -> float | None:
    """Hours since boot, or None if it cannot be read. Linux: /proc/uptime. macOS:
    `sysctl -n kern.boottime`. Windows: GetTickCount64."""
    try:
        if os.name == "nt":
            import ctypes  # noqa: PLC0415
            k32 = ctypes.windll.kernel32
            k32.GetTickCount64.restype = ctypes.c_ulonglong
            return k32.GetTickCount64() / 3_600_000.0
        p = Path("/proc/uptime")
        if p.exists():
            return float(p.read_text().split()[0]) / 3600.0
        r = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True,
                           text=True, timeout=10)
        m = re.search(r"sec\s*=\s*(\d+)", r.stdout or "")
        if m:
            import time  # noqa: PLC0415
            return (time.time() - int(m.group(1))) / 3600.0
    except Exception:  # noqa: BLE001
        return None
    return None
