"""Tests for bin/scheduler/introspect.py (installed-state readback) and
bin/verify_scheduled_tasks.py. Parsers are pure; queries use a fake runner, so every OS
path is exercised on any OS without touching a real scheduler."""
from __future__ import annotations

import json
import plistlib
import types

import verify_scheduled_tasks as vst
from scheduler import introspect as intro
from scheduler.jobs import Job

REG = [Job("alpha", ["bin/a.py"], "daily", "08:00"),
       Job("beta", ["bin/b.py"], "weekly", "09:00", dow="SUN")]


def _run(stdout="", rc=0, stderr=""):
    return lambda cmd, **kw: types.SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)


def test_parse_crontab_reads_tagged_lines_and_disabled_ones():
    text = ("0 8 * * * cd /r && py bin/a.py  # agent-harness:alpha\n"
            "# 0 9 * * 0 cd /r && py bin/b.py  # agent-harness:beta\n"
            "5 4 * * * unrelated-user-job\n")
    got = intro.parse_crontab(text)
    assert set(got) == {"alpha", "beta"}
    assert got["alpha"].time == "08:00" and got["alpha"].dow is None
    assert got["beta"].state == "Disabled" and got["beta"].dow == "SUN"
    assert got["alpha"].last_run is None          # cron keeps no run history


def test_linux_query_no_crontab_is_empty_but_other_errors_are_blind():
    inst, _ = intro.query("Linux", runner=_run(rc=1, stderr="no crontab for user"))
    assert inst == {}
    inst, why = intro.query("Linux", runner=_run(rc=1, stderr="permission denied"))
    assert inst is None and "permission denied" in why


def test_launchctl_and_plist_parsing():
    rows = intro.parse_launchctl_list("PID\tStatus\tLabel\n-\t0\tagent-harness.alpha\n"
                                      "123\t0\tagent-harness.beta\n-\t0\tcom.other\n")
    assert rows == {"agent-harness.alpha": ("-", "0"), "agent-harness.beta": ("123", "0")}
    data = plistlib.dumps({"StartCalendarInterval": {"Hour": 9, "Minute": 5, "Weekday": 0}})
    assert intro.parse_plist_schedule(data) == ("09:05", "SUN")


def test_macos_query_marks_unloaded_plist_disabled(tmp_path):
    la = tmp_path / "LaunchAgents"
    la.mkdir()
    for jid, h in (("alpha", 8), ("beta", 9)):
        (la / f"agent-harness.{jid}.plist").write_bytes(
            plistlib.dumps({"StartCalendarInterval": {"Hour": h, "Minute": 0}}))
    inst, _ = intro._query_macos(_run("-\t78\tagent-harness.alpha\n"), agents_dir=la)
    assert inst["alpha"].state == "Ready" and inst["alpha"].last_result == 78
    assert inst["beta"].state == "Disabled"


def test_windows_json_parsing():
    payload = json.dumps([
        {"Name": "agent-harness-alpha", "State": "Ready", "LastRun": "2030-01-15T08:00:00.1234567-05:00",
         "NextRun": "", "LastResult": 0, "Start": "2030-01-01T08:00:00", "Days": 0},
        {"Name": "agent-harness-beta", "State": "Disabled", "LastRun": "1999-11-30T00:00:00",
         "NextRun": "", "LastResult": 267011, "Start": "2030-01-05T09:00:00", "Days": 1},
        {"Name": "SomethingElse", "State": "Ready"},
    ])
    got = intro.parse_windows_json(payload)
    assert set(got) == {"alpha", "beta"}
    assert got["alpha"].last_run is not None and got["alpha"].time == "08:00"
    assert got["beta"].last_run is None and got["beta"].dow == "SUN"
    assert intro.parse_windows_json("") == {}


def test_reconcile_finds_every_kind_of_drift():
    installed = {
        "alpha": intro.Installed("alpha", time="08:30"),
        "beta": intro.Installed("beta", state="Disabled", time="09:00", dow="SUN"),
        "ghost": intro.Installed("ghost", time="01:00"),
    }
    kinds = {(k, j) for _, k, j, _ in intro.reconcile(REG, installed)}
    assert ("INSTALLED-NOT-DECLARED", "ghost") in kinds
    assert ("SCHEDULE-MISMATCH", "alpha") in kinds
    assert ("DISABLED", "beta") in kinds
    missing = intro.reconcile(REG, {"alpha": intro.Installed("alpha", time="08:00")})
    assert [(k, j) for _, k, j, _ in missing] == [("DECLARED-NOT-INSTALLED", "beta")]


def test_parse_iso_handles_sentinels_and_naive_values():
    assert intro.parse_iso("") is None and intro.parse_iso("1999-11-30T00:00:00") is None
    assert intro.parse_iso("garbage") is None
    assert intro.parse_iso("2030-01-15T12:00:00Z").tzinfo is not None
    assert intro.parse_iso("2030-01-15T12:00:00").tzinfo is not None


# --- verify_scheduled_tasks ----------------------------------------------------------
def test_verify_unknown_when_blind_or_nothing_installed(monkeypatch):
    monkeypatch.setattr(intro, "query", lambda os_name=None, runner=None: (None, "boom"))
    verdict, lines = vst.verify(REG)
    assert verdict == "unknown" and "not a pass" in lines[0]
    monkeypatch.setattr(intro, "query", lambda os_name=None, runner=None: ({}, "empty"))
    assert vst.verify(REG)[0] == "unknown"
    assert vst.main([]) == 2


def test_verify_pass_and_fail(monkeypatch):
    ok = {"alpha": intro.Installed("alpha", time="08:00"),
          "beta": intro.Installed("beta", time="09:00", dow="SUN")}
    monkeypatch.setattr(intro, "query", lambda os_name=None, runner=None: (ok, "read"))
    assert vst.verify(REG)[0] == "pass"
    monkeypatch.setattr(intro, "query",
                        lambda os_name=None, runner=None: ({"alpha": ok["alpha"]}, "read"))
    verdict, lines = vst.verify(REG)
    assert verdict == "fail" and any("DECLARED-NOT-INSTALLED" in ln for ln in lines)
