"""Tests for bin/self_loop.py: liveness classification, the heal policy, and evidenced-
only recovery. The clock is pinned (no test depends on today's date) and nothing touches
a real scheduler."""
from __future__ import annotations

import datetime as dt
import types

import pytest

import harness_common as hc
import self_loop as sl
from _health_fixtures import PINNED, hc_env, iso  # noqa: F401
from scheduler import introspect as intro
from scheduler.jobs import Job

NOW = dt.datetime.fromtimestamp(PINNED, dt.timezone.utc)
REG = [Job("alpha", ["bin/a.py"], "daily", "08:00", safe_rerun=True),
       Job("beta", ["bin/b.py"], "daily", "08:00", safe_rerun=False),
       Job("self-loop", ["bin/self_loop.py"], "daily", "06:30")]


@pytest.fixture(autouse=True)
def _hermetic_log(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "LOG_PATH", tmp_path / "self-loop.log")


def inst(jid, hours_ago=None, result=0, state="Ready", next_in_h=None):
    return intro.Installed(
        jid, state=state, time="08:00",
        last_run=None if hours_ago is None else NOW - dt.timedelta(hours=hours_ago),
        last_result=result,
        next_run=None if next_in_h is None else NOW + dt.timedelta(hours=next_in_h))


def oc(status="ok", age_h=1.0, detail=""):
    return {"status": status, "age_h": age_h, "detail": detail, "ts": iso(-age_h)}


def classify(installed, outcomes=None, uptime=100.0, os_name="windows", reg=None):
    rows = sl.audit(installed, NOW, uptime, registry=reg or REG[:2],
                    outcomes=outcomes or {}, os_name=os_name)
    return {jid: (sev, st) for sev, jid, st, _ in rows}


# --- liveness ---------------------------------------------------------------------------
def test_missing_disabled_and_undeclared():
    got = classify({"beta": inst("beta", 1, state="Disabled"), "ghost": inst("ghost", 1)})
    assert got["alpha"] == ("CRIT", "MISSING")
    assert got["beta"] == ("HIGH", "DISABLED")
    assert got["ghost"] == ("HIGH", "UNDECLARED")


def test_never_fired_only_without_an_upcoming_trigger():
    got = classify({"alpha": inst("alpha"), "beta": inst("beta", next_in_h=5)})
    assert got["alpha"] == ("CRIT", "NEVER_FIRED")
    assert "beta" not in got                      # freshly installed, awaiting first run


def test_stale_vs_catching_up_after_boot():
    assert classify({"alpha": inst("alpha", 50), "beta": inst("beta", 1)})["alpha"] == \
        ("HIGH", "STALE")
    got = classify({"alpha": inst("alpha", 50), "beta": inst("beta", 1)}, uptime=0.5)
    assert "alpha" not in got and got["self-loop"] == ("INFO", "CATCHING-UP")


def test_failed_result_and_ran_but_failed_outcome():
    got = classify({"alpha": inst("alpha", 1, result=1), "beta": inst("beta", 1)},
                   outcomes={"beta": oc("auth_failed")})
    assert got["alpha"] == ("HIGH", "FAILED")
    assert got["beta"] == ("HIGH", "RAN-BUT-FAILED")


def test_stale_outcome_when_the_task_fires_but_the_sidecar_froze():
    got = classify({"alpha": inst("alpha", 1), "beta": inst("beta", 1)},
                   outcomes={"alpha": oc("ok", age_h=100)})
    assert got["alpha"] == ("HIGH", "STALE-OUTCOME") and got["beta"] == ("OK", "OK")


def test_linux_recency_comes_from_outcomes_or_is_unknown():
    cron = {"alpha": intro.Installed("alpha", time="08:00"),
            "beta": intro.Installed("beta", time="08:00")}
    got = classify(cron, outcomes={"alpha": oc("ok", age_h=3)}, os_name="linux")
    assert got["alpha"] == ("OK", "OK")
    assert got["beta"] == ("INFO", "UNKNOWN")      # never assumed healthy, never paged
    got = classify(cron, outcomes={"alpha": oc("ok", age_h=40)}, os_name="linux")
    assert got["alpha"] == ("HIGH", "STALE")


# --- heal policy ----------------------------------------------------------------------
def _findings(*pairs):
    return [("HIGH", jid, st, "") for jid, st in pairs]


def test_heals_only_safe_rerun_jobs_and_counts_attempts(hc_env, monkeypatch):
    monkeypatch.setattr(sl, "next_slot", lambda job, now: now + dt.timedelta(hours=10))
    ran, state = [], {"attempts": {}}
    actions, escs = sl.heal(_findings(("alpha", "FAILED"), ("beta", "FAILED")), state, NOW,
                            False, registry=REG, run_now=lambda j: (ran.append(j.id), (True, ""))[1])
    assert ran == ["alpha"] and state["attempts"]["alpha"]["count"] == 1
    assert any("beta" in e and "safe_rerun" in e for e in escs)


def test_rolling_window_pauses_after_two_attempts_then_resumes(hc_env, monkeypatch):
    monkeypatch.setattr(sl, "next_slot", lambda job, now: now + dt.timedelta(hours=10))
    state, ran = {"attempts": {}}, []
    run = lambda j: (ran.append(j.id), (True, ""))[1]  # noqa: E731
    f = _findings(("alpha", "FAILED"))
    for i in range(3):
        _, escs = sl.heal(f, state, NOW + dt.timedelta(hours=i), False, registry=REG, run_now=run)
    assert len(ran) == 2 and any("PAUSED until" in e for e in escs)
    sl.heal(f, state, NOW + dt.timedelta(hours=30), False, registry=REG, run_now=run)
    assert len(ran) == 3                          # window elapsed -> retries resume


def test_imminent_own_slot_and_usage_limit_spend_no_attempt(hc_env, monkeypatch):
    run = lambda j: (_ for _ in ()).throw(AssertionError("must not run"))  # noqa: E731
    monkeypatch.setattr(sl, "next_slot", lambda job, now: now + dt.timedelta(hours=1))
    state = {"attempts": {}}
    actions, _ = sl.heal(_findings(("alpha", "FAILED")), state, NOW, False, registry=REG,
                         run_now=run)
    assert "own slot" in actions[0] and state["attempts"] == {}
    monkeypatch.setattr(sl, "next_slot", lambda job, now: now + dt.timedelta(hours=10))
    hc.record_outcome("alpha", status="rate_limited", detail="limit · resets 11pm")
    _, escs = sl.heal(_findings(("alpha", "RAN-BUT-FAILED")), state, NOW, False,
                      registry=REG, run_now=run)
    assert "usage limit" in escs[0] and state["attempts"] == {}


def test_dry_run_heal_runs_nothing(hc_env, monkeypatch):
    monkeypatch.setattr(sl, "next_slot", lambda job, now: now + dt.timedelta(hours=10))
    actions, _ = sl.heal(_findings(("alpha", "FAILED")), {"attempts": {}}, NOW, True,
                         registry=REG, run_now=lambda j: 1 / 0)
    assert actions[0].startswith("WOULD re-run alpha")


def test_next_slot_daily_and_weekly():
    daily = sl.next_slot(Job("d", ["x"], "daily", "08:00"), NOW)
    assert daily > NOW.astimezone() and (daily - NOW.astimezone()).total_seconds() <= 86400
    weekly = sl.next_slot(Job("w", ["x"], "weekly", "08:00", dow="MON"), NOW)
    assert weekly.weekday() == 0


# --- reconciliation -------------------------------------------------------------------
def test_green_only_with_positive_evidence_and_never_for_itself(hc_env):
    for j in ("alpha", "beta", "self-loop"):
        hc.mark_broken(j, f"{j}: STALE", fleet=True)
    findings = [("OK", "alpha", "OK", ""), ("OK", "beta", "OK", ""), ("OK", "self-loop", "OK", "")]
    rec = sl.reconcile_conditions(findings, registry=REG,
                                  outcomes={"alpha": oc("ok"), "beta": None})
    assert [r["job"] for r in rec] == ["alpha"]
    assert [i["job"] for i in hc.open_issues()] == ["self-loop"]


# --- cycle --------------------------------------------------------------------------
def test_blind_scheduler_is_an_alert_not_a_clean_fleet(hc_env, monkeypatch):
    monkeypatch.setattr(intro, "query", lambda *a, **k: (None, "scheduler offline"))
    rc = sl.cycle(types.SimpleNamespace(dry_run=False, quiet=True), now=NOW)
    assert rc == 1 and "BLIND" in hc.open_issues()[0]["message"]
    assert hc.read_outcome("self-loop")["status"] == "error"


def test_nothing_installed_is_empty_not_ok(hc_env, monkeypatch):
    monkeypatch.setattr(intro, "query", lambda *a, **k: ({}, "no crontab"))
    assert sl.cycle(types.SimpleNamespace(dry_run=False, quiet=True), now=NOW) == 0
    assert hc.read_outcome("self-loop")["status"] == "empty"


def test_full_cycle_escalates_once_and_writes_heartbeat(hc_env, monkeypatch, tmp_path):
    monkeypatch.setattr(sl, "REPORT", tmp_path / "report.md")
    monkeypatch.setattr(sl, "HEARTBEAT", tmp_path / "hb")
    monkeypatch.setattr(sl, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sl, "FORGE", tmp_path)
    monkeypatch.setattr(sl._jobs, "REGISTRY", REG[:2])
    monkeypatch.setattr(intro, "query", lambda *a, **k: ({"alpha": inst("alpha", 1)}, "read"))
    monkeypatch.setattr(intro, "system_uptime_h", lambda: 100.0)
    monkeypatch.setattr(intro, "detect_os", lambda name=None: "windows")
    args = types.SimpleNamespace(dry_run=False, quiet=False)
    assert sl.cycle(args, now=NOW) == 0
    assert (tmp_path / "hb").read_text() == NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert len(hc_env.posts) == 1                  # beta MISSING pages once...
    sl.cycle(args, now=NOW)
    assert len(hc_env.posts) == 1                  # ...and stays silent while chronic
