"""Tests for the cross-platform scheduler core (pure parts).

The side-effectful apply()/remove() backends (crontab/launchd/schtasks) are NOT
exercised here — they need a real per-OS machine. We test the generators,
registry, OS detection, and plan(), which are pure and run anywhere.
"""
import importlib.util
import sys
from pathlib import Path


def _load(name):
    p = Path(__file__).resolve().parents[1] / "scheduler" / f"{name}.py"
    modname = f"scheduler_{name}"
    s = importlib.util.spec_from_file_location(modname, p)
    m = importlib.util.module_from_spec(s)
    sys.modules[modname] = m  # required for @dataclass under Python 3.12+
    s.loader.exec_module(m)
    return m


jobs = _load("jobs")
backends = _load("backends")
install = _load("install")


# --- registry / model ---
def test_job_defaults():
    j = jobs.Job(id="x", args=["bin/x.py"], cadence="daily", time="07:00")
    assert j.dow is None and j.cadence == "daily"


def test_registry_is_list_and_repo_relative():
    # Empty by default (safe); any entries the user adds must be repo-relative.
    assert isinstance(jobs.REGISTRY, list)
    for j in jobs.REGISTRY:
        for a in j.args:
            assert not a.startswith("/") and ":" not in a  # no absolute/Windows paths


_EXAMPLE = [
    jobs.Job("daily-brief", ["bin/daily-brief.py"], "daily", "07:00"),
    jobs.Job("weekly-planner", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN"),
]


# --- cron ---
def test_cron_daily():
    j = jobs.Job("daily-brief", ["bin/daily-brief.py"], "daily", "07:00")
    line = backends.to_cron_line(j, python="/usr/bin/python3", repo="/home/u/ah")
    assert line.startswith("0 7 * * * ")
    assert "cd /home/u/ah && /usr/bin/python3 bin/daily-brief.py" in line
    assert "# agent-harness:daily-brief" in line


def test_cron_weekly_sunday():
    j = jobs.Job("wp", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN")
    assert backends.to_cron_line(j, "/usr/bin/python3", "/r").startswith("0 9 * * 0 ")


# --- launchd ---
def test_launchd_plist():
    import plistlib
    j = jobs.Job("wp", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN")
    xml = backends.to_launchd_plist(j, "/usr/bin/python3", "/r")
    d = plistlib.loads(xml.encode())
    assert d["Label"] == "agent-harness.wp"
    assert d["ProgramArguments"] == ["/usr/bin/python3", "/r/bin/weekly-planner.py"]
    assert d["StartCalendarInterval"]["Hour"] == 9
    assert d["StartCalendarInterval"]["Minute"] == 0
    assert d["StartCalendarInterval"]["Weekday"] == 0


# --- schtasks ---
def test_schtasks_cmd():
    j = jobs.Job("wp", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN")
    cmd = backends.to_schtasks_cmd(j, "python", r"C:\r")
    assert cmd[:3] == ["schtasks", "/Create", "/SC"]
    assert "WEEKLY" in cmd and "/D" in cmd and "SUN" in cmd
    assert "09:00" in cmd
    assert f"agent-harness-wp" in cmd


# --- detect_os / plan ---
def test_detect_os(monkeypatch):
    monkeypatch.setattr(install.platform, "system", lambda: "Darwin")
    assert install.detect_os() == "macos"
    monkeypatch.setattr(install.platform, "system", lambda: "Linux")
    assert install.detect_os() == "linux"
    monkeypatch.setattr(install.platform, "system", lambda: "Windows")
    assert install.detect_os() == "windows"


def test_plan_one_artifact_per_job_linux():
    p = install.plan(os_name="linux", python="/usr/bin/python3", repo="/r", registry=_EXAMPLE)
    assert len(p) == len(_EXAMPLE)
    assert all("# agent-harness:" in x for x in p)


def test_plan_macos_emits_plists():
    p = install.plan(os_name="macos", python="/usr/bin/python3", repo="/r", registry=_EXAMPLE)
    assert len(p) == 2 and all("<plist" in x for x in p)


def test_plan_empty_registry_is_safe():
    assert install.plan(os_name="linux", python="/usr/bin/python3", repo="/r") == []
