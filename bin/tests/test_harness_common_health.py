"""Tests for the health helpers in harness_common: outcomes, freshness barrier, the
state-gated alert ledger, dry-run, secret scrubbing, locks, and the structured claude call.

Hermetic: every state path is redirected to tmp and the clock is pinned (see
_health_fixtures.hc_env). No test posts to Slack or calls a model.
"""
from __future__ import annotations

import json
import os
import subprocess
import types

import harness_common as hc
from _health_fixtures import PINNED, hc_env, iso  # noqa: F401  (fixture import)


# --- condition_key ---------------------------------------------------------------------
def test_condition_key_ignores_volatile_numbers_and_hex():
    a = hc.condition_key("self-loop", "worker failed (0x1) — retry later")
    b = hc.condition_key("self-loop", "worker failed (0xDEADBEEF) — retry later")
    assert a == b
    assert hc.condition_key("j", "STALE: x last ran 32h ago") == \
        hc.condition_key("j", "STALE: x last ran 40h ago")


def test_condition_key_separates_jobs_and_failure_classes():
    assert hc.condition_key("a", "failed") != hc.condition_key("b", "failed")
    msg = "RAN-BUT-FAILED: worker exited 0 but its last run reported '{}' — padding padding"
    keys = {hc.condition_key("self-loop", msg.format(s))
            for s in ("auth_failed", "rate_limited", "transient", "error")}
    assert len(keys) == 4


# --- state gate --------------------------------------------------------------------------
def test_ok_to_broken_pages_once_then_silent(hc_env):
    assert hc.mark_broken("worker", "failed (0x1)") is True
    for _ in range(4):
        assert hc.mark_broken("worker", "failed (0x2)") is False


def test_fleet_condition_recovers_and_next_break_pages_again(hc_env):
    hc.mark_broken("worker", "failed", fleet=True)
    rec = hc.resolve_conditions(["worker"])
    assert len(rec) == 1 and rec[0]["job"] == "worker"
    assert hc.mark_broken("worker", "failed", fleet=True) is True


def test_non_fleet_recovery_clears_silently(hc_env):
    hc.mark_broken("worker", "failed")
    assert hc.resolve_conditions(["worker"]) == []
    assert hc.open_issues() == []


def test_resolve_matches_across_case_and_separators_but_never_blank(hc_env):
    hc.mark_broken("self-test", "red", fleet=True)
    assert len(hc.resolve_conditions(["Self_Test"])) == 1
    hc.mark_broken("", "nameless", fleet=True)
    assert hc.resolve_conditions([""]) == []


def test_subject_not_raiser_owns_the_condition(hc_env):
    hc.mark_broken("fleet-status", "heartbeat stale", fleet=True, subject="self-loop")
    assert hc.resolve_conditions(["fleet-status"]) == []        # the watchdog cannot clear it
    assert len(hc.resolve_conditions(["self-loop"])) == 1


def test_nonfleet_conditions_expire_after_24h(hc_env):
    hc.mark_broken("worker", "one-off")
    hc_env.advance(25)
    assert hc.mark_broken("other", "x") is True               # triggers expiry pass
    assert [i["job"] for i in hc.open_issues()] == ["other"]


def test_chronic_refresh_keeps_age_and_updates_wording(hc_env):
    hc.mark_broken("worker", "17 items queued", fleet=True)
    hc_env.advance(48)
    hc.mark_broken("worker", "5 items queued", fleet=True)
    [issue] = hc.open_issues()
    assert issue["message"] == "5 items queued"
    assert round(issue["age_d"], 1) == 2.0 and issue["quiet_d"] == 0.0


def test_corrupt_store_fails_open_and_open_issues_reports_it(hc_env):
    hc.ALERT_STATE.parent.mkdir(parents=True)
    hc.ALERT_STATE.write_text("{not json", encoding="utf-8")
    assert hc.mark_broken("worker", "x") is True
    hc.ALERT_STATE.write_text("[1, 2]", encoding="utf-8")
    issues = hc.open_issues()
    assert issues[0]["job"] == "alert-state" and "UNREADABLE" in issues[0]["message"]


def test_open_issues_oldest_first(hc_env):
    hc.mark_broken("old", "a")
    hc_env.advance(10)
    hc.mark_broken("new", "b")
    assert [i["job"] for i in hc.open_issues()] == ["old", "new"]


# --- alert ----------------------------------------------------------------------------
def test_alert_logs_every_time_but_pages_once(hc_env):
    for _ in range(3):
        hc.alert("worker", "broke")
    assert len(hc_env.posts) == 1 and hc_env.posts[0][0] == "harness alert"
    lines = hc.ALERTS_LOG.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and lines[0].startswith(iso(0))


def test_chronic_condition_repages_at_milestones(hc_env):
    for day in (0, 6.5, 8, 9, 15, 40):
        hc_env.now = PINNED + day * 86400
        hc.alert("worker", "still dead", fleet=True)   # fleet: never auto-expires
    titles = [t for t, _ in hc_env.posts]
    assert titles == ["harness alert", "harness still broken (7d)",
                      "harness still broken (14d)", "harness still broken (28d)"]


def test_alert_scrubs_secrets_everywhere(hc_env):
    hc.alert("worker", "failed with token=abcdefghijklmnopqrstuv and sk-abcdefghijklmnop")
    blob = hc.ALERTS_LOG.read_text(encoding="utf-8") + json.dumps(hc_env.posts) \
        + hc.ALERT_STATE.read_text(encoding="utf-8")
    assert "abcdefghijklmnopqrstuv" not in blob and "sk-abcdefghijklmnop" not in blob


def test_dry_run_makes_alerts_and_outcomes_inert(hc_env):
    hc.set_dry_run(True, "test")
    hc.alert("worker", "broke")
    hc.record_outcome("worker", status="error")
    hc.alert_recovered("worker", "fine")
    assert not hc.ALERTS_LOG.exists() and not hc.OUTCOMES_DIR.exists() and not hc_env.posts


def test_alert_recovered_posts_green(hc_env):
    hc.alert_recovered("worker", "recovered")
    assert hc_env.posts[0][0] == "harness recovered"
    assert "RECOVERED" in hc.ALERTS_LOG.read_text(encoding="utf-8")


# --- outcomes + freshness -------------------------------------------------------------
def test_record_and_read_outcome_roundtrip_with_history(hc_env):
    hc.record_outcome("worker", status="ok", produced=3, detail="made 3")
    hc_env.advance(2)
    oc = hc.read_outcome("worker")
    assert oc["status"] == "ok" and oc["produced"] == 3 and oc["age_h"] == 2.0
    hist = (hc.OUTCOMES_DIR / "history.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(hist[0])["job"] == "worker"


def test_ok_with_zero_produced_is_alarmed_but_empty_is_not(hc_env):
    hc.record_outcome("quiet", status="empty", produced=0)
    hc.record_outcome("uninstrumented", status="ok", produced=None)
    assert hc_env.posts == []
    hc.record_outcome("liar", status="ok", produced=0)
    assert len(hc_env.posts) == 1 and "produced=0" in hc_env.posts[0][1]


def test_unparseable_timestamp_is_undatable_not_fresh(hc_env):
    hc.OUTCOMES_DIR.mkdir(parents=True)
    (hc.OUTCOMES_DIR / "w.json").write_text(json.dumps({"ts": "yesterday", "status": "ok"}),
                                            encoding="utf-8")
    assert hc.read_outcome("w")["age_h"] is None
    ok, why = hc.require_fresh("w", 24)
    assert not ok and "no readable timestamp" in why


def test_require_fresh_semantics(hc_env):
    assert hc.require_fresh("never", 24)[0] is False
    hc.record_outcome("p", status="ok", produced=5)
    assert hc.require_fresh("p", 24)[0] is True
    hc_env.advance(30)
    ok, why = hc.require_fresh("p", 24)
    assert not ok and "stale" in why
    hc.record_outcome("e", status="empty", produced=0)
    assert hc.require_fresh("e", 24)[0] is True
    assert hc.require_fresh("e", 24, require_produced=True)[0] is False
    hc.record_outcome("f", status="auth_failed")
    assert hc.require_fresh("f", 24)[0] is False


def test_require_fresh_refuses_a_future_timestamp(hc_env):
    hc.record_outcome("p", status="ok", produced=1)
    hc_env.advance(-5)
    ok, why = hc.require_fresh("p", 24)
    assert not ok and "FUTURE" in why


def test_parse_limit_reset_same_day_and_rollover():
    r = hc.parse_limit_reset("You've hit your session limit · resets 5:10pm",
                             "2030-01-15T12:00:00Z")
    assert r is not None and (r.hour, r.minute) == (17, 10)
    assert hc.parse_limit_reset("no time here", "2030-01-15T12:00:00Z") is None
    early = hc.parse_limit_reset("resets 1am", "2030-01-15T12:00:00Z")
    late = hc.parse_limit_reset("resets 11pm", "2030-01-15T12:00:00Z")
    assert early is not None and late is not None and early.hour == 1 and late.hour == 23


# --- kill-switch / files / locks -------------------------------------------------------
def test_guard_or_skip(hc_env):
    assert hc.guard_or_skip("j", lambda m: None) is True
    hc.STOP_FILE.parent.mkdir(parents=True)
    hc.STOP_FILE.write_text("{}", encoding="utf-8")
    msgs = []
    assert hc.guard_or_skip("j", msgs.append) is False and "STOP" in msgs[0]


def test_write_json_atomic_and_failure(tmp_path):
    p = tmp_path / "a" / "b.json"
    assert hc.write_json_atomic(p, {"x": 1}) and json.loads(p.read_text())["x"] == 1
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert hc.write_json_atomic(blocker / "c.json", {}) is False


def test_rotate_log_keeps_one_backup(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("a" * 50)
    hc.rotate_log(log, max_bytes=10)
    assert not log.exists() and (tmp_path / "x.log.1").exists()
    hc.rotate_log(tmp_path / "missing.log")   # never raises


def test_single_instance_blocks_a_second_holder(hc_env):
    with hc.single_instance("job") as a:
        assert a is True
        with hc.single_instance("job") as b:
            assert b is False
    assert not (hc.LOCK_DIR / "job.lock").exists()


def test_single_instance_reclaims_an_orphan_lock(hc_env, monkeypatch):
    hc.LOCK_DIR.mkdir(parents=True)
    (hc.LOCK_DIR / "job.lock").write_text("424242", encoding="ascii")
    os.utime(hc.LOCK_DIR / "job.lock", (PINNED, PINNED))
    monkeypatch.setattr(hc, "_pid_alive", lambda pid: False)
    with hc.single_instance("job") as ok:
        assert ok is True


def test_pid_alive_for_this_process():
    assert hc._pid_alive(os.getpid()) is True


def test_record_run_writes_to_the_audit_db(tmp_path, hc_env):
    db = tmp_path / "runner.db"
    rid = hc.record_run("worker", status="ok", actions=2, attention=["look"], db_path=db)
    from runner import events
    run = events.get_run(rid, db_path=db)
    assert run["status"] == "ok" and run["job"] == "worker"


# --- secrets -------------------------------------------------------------------------
def test_scrub_secrets_masks_canonical_shapes():
    text = ("AKIA" + "A" * 16 + " ghp_" + "a" * 30 + " Bearer abc.def "
            "-----BEGIN RSA PRIVATE KEY----- MY_API_KEY=abcdefghijklmnop ordinary words")
    out = hc.scrub_secrets(text)
    assert "AKIA" not in out and "ghp_" not in out and "Bearer abc" not in out
    assert "PRIVATE KEY" not in out and "abcdefghijklmnop" not in out
    assert "ordinary words" in out


# --- claude_json ---------------------------------------------------------------------
def _runner(stdout="", rc=0, stderr="", seen=None):
    def run(cmd, **kw):
        if seen is not None:
            seen.update(cmd=cmd, **kw)
        return types.SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)
    return run


SCHEMA = {"type": "object", "required": ["verdict"]}


def test_claude_json_ok_on_subscription_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "metered")
    seen = {}
    res = hc.claude_json("hi", SCHEMA, runner=_runner(
        json.dumps({"result": json.dumps({"verdict": "yes"})}), seen=seen))
    assert res.ok and res.value == {"verdict": "yes"}
    assert "ANTHROPIC_API_KEY" not in seen["env"]
    assert "--json-schema" in seen["cmd"] and seen["stdin"] == subprocess.DEVNULL


def test_claude_json_long_prompt_goes_through_stdin():
    seen = {}
    hc.claude_json("x" * 9000, SCHEMA, runner=_runner('{"verdict": "y"}', seen=seen))
    assert seen["input"] == "x" * 9000 and "x" * 9000 not in seen["cmd"]


def test_claude_json_failure_classes():
    assert hc.claude_json("p", SCHEMA, runner=_runner(
        '{"stop_reason": "refusal"}', rc=1)).status == "refused"
    assert hc.claude_json("p", SCHEMA, runner=_runner(
        "You've hit your session limit · resets 3pm", rc=1)).status == "rate_limited"
    assert hc.claude_json("p", SCHEMA, runner=_runner("plain prose")).status == "contract_failed"
    assert hc.claude_json("p", SCHEMA, runner=_runner('{"other": 1}')).status == "contract_failed"
