"""Pure per-OS schedule generators: turn a Job into a cron line / launchd plist /
schtasks command. No side effects, no OS calls — unit-testable on any platform.
"""
from __future__ import annotations

import os
import plistlib

# cron / launchd weekday numbering: 0=Sun .. 6=Sat
_CRON_DOW = {"SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6}


def _hm(t: str) -> tuple[int, int]:
    h, m = t.split(":")
    return int(h), int(m)


def to_cron_line(job, python: str, repo: str) -> str:
    """Build a crontab line; tagged with `# agent-harness:<id>` for idempotent removal."""
    h, m = _hm(job.time)
    dow = _CRON_DOW[job.dow] if job.cadence == "weekly" else "*"
    cmd = " ".join([python, *job.args])
    return f"{m} {h} * * {dow} cd {repo} && {cmd}  # agent-harness:{job.id}"


def to_launchd_plist(job, python: str, repo: str) -> str:
    """Build a launchd plist (macOS) as XML text."""
    h, m = _hm(job.time)
    sci: dict = {"Hour": h, "Minute": m}
    if job.cadence == "weekly":
        sci["Weekday"] = _CRON_DOW[job.dow]  # launchd: 0/7=Sunday
    d = {
        "Label": f"agent-harness.{job.id}",
        "ProgramArguments": [python, *[f"{repo}/{a}" for a in job.args]],
        "StartCalendarInterval": sci,
        "RunAtLoad": False,
    }
    return plistlib.dumps(d).decode()


def to_schtasks_cmd(job, python: str, repo: str) -> list[str]:
    """Build a Windows schtasks /Create argv list."""
    tr = " ".join([python, *[os.path.join(repo, a) for a in job.args]])
    cmd = ["schtasks", "/Create", "/SC"]
    if job.cadence == "weekly":
        cmd += ["WEEKLY", "/D", job.dow]
    else:
        cmd += ["DAILY"]
    cmd += ["/ST", job.time, "/TN", f"agent-harness-{job.id}", "/TR", tr, "/F"]
    return cmd


def to_schtasks_settings_patch(job) -> list[str]:
    """Build a post-create PowerShell argv that hardens a Windows task's settings.

    `schtasks /Create` cannot set these, and their absence is a silent-death trap
    learned the hard way: a weekly task whose trigger fires while the machine is
    asleep (or whose launch is refused) simply loses that week. The patch adds:
      - StartWhenAvailable  — missed trigger -> run as soon as possible (catch-up)
      - RestartCount/Interval — a failed launch retries 3x every 30 minutes

    Pure generator (no OS calls) — the applier runs it after each /Create."""
    ps = (
        f"$t = Get-ScheduledTask -TaskName 'agent-harness-{job.id}'; "
        "$s = $t.Settings; "
        "$s.StartWhenAvailable = $true; "
        "$s.RestartCount = 3; "
        "$s.RestartInterval = 'PT30M'; "
        f"Set-ScheduledTask -TaskName 'agent-harness-{job.id}' -Settings $s | Out-Null"
    )
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps]
