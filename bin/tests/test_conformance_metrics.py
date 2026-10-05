"""Tests for bin/conformance_check.py and bin/harness_metrics.py. Each assertion is
driven to PASS / FAIL / SKIP / BLIND with tmp fixtures; nothing reads the real profile."""
from __future__ import annotations

import json
import os
import types

import pytest

import conformance_check as cc
import harness_common as hc
import harness_metrics as hm
from _health_fixtures import hc_env  # noqa: F401
from scheduler import introspect as intro
from scheduler.jobs import Job


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """An isolated Claude profile dir (settings.json + skills/)."""
    d = tmp_path / "profile"
    d.mkdir()
    monkeypatch.delenv("CLAUDE_SETTINGS_PATH", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(d))
    return d


def test_c1_registry_integrity(monkeypatch, tmp_path):
    monkeypatch.setattr(cc, "ROOT", tmp_path)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "good.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "bin" / "bad.py").write_text("def (:\n", encoding="utf-8")
    from scheduler import jobs
    monkeypatch.setattr(jobs, "REGISTRY", [Job("g", ["bin/good.py"], "daily", "01:00")])
    assert cc.c1_registry_integrity().status == "PASS"
    monkeypatch.setattr(jobs, "REGISTRY", [Job("b", ["bin/bad.py"], "daily", "01:00"),
                                           Job("m", ["bin/missing.py"], "daily", "01:00")])
    r = cc.c1_registry_integrity()
    assert r.status == "FAIL" and "2 problem" in r.observed


def test_c2_blind_skip_fail_pass(monkeypatch):
    from scheduler import jobs
    monkeypatch.setattr(jobs, "REGISTRY", [Job("a", ["x"], "daily", "01:00")])
    assert cc.c2_scheduler_matches_registry(lambda: (None, "boom")).status == "BLIND"
    assert cc.c2_scheduler_matches_registry(lambda: ({}, "none")).status == "SKIP"
    assert cc.c2_scheduler_matches_registry(lambda: ({"z": intro.Installed("z")}, "")).status == "FAIL"
    ok = {"a": intro.Installed("a", time="01:00")}
    assert cc.c2_scheduler_matches_registry(lambda: (ok, "")).status == "PASS"


def test_c3_index_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(cc, "ROOT", tmp_path)
    assert cc.c3_index_within_budget().status == "SKIP"
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "MEMORY.md").write_text("x" * 100, encoding="utf-8")
    assert cc.c3_index_within_budget().status == "PASS"
    (tmp_path / "memory" / "MEMORY.md").write_text("x" * 40000, encoding="utf-8")
    assert cc.c3_index_within_budget().status == "FAIL"


def test_c5_installed_skill_drift(monkeypatch, tmp_path, profile):
    monkeypatch.setattr(cc, "ROOT", tmp_path)
    assert cc.c5_installed_skills_current().status == "SKIP"
    for base, body in ((tmp_path / "skills", "v2"), (profile / "skills", "v1")):
        (base / "s").mkdir(parents=True)
        (base / "s" / "SKILL.md").write_text(body, encoding="utf-8")
    r = cc.c5_installed_skills_current()
    assert r.status == "WARN" and "1 of 1" in r.observed
    (profile / "skills" / "s" / "SKILL.md").write_text("v2", encoding="utf-8")
    assert cc.c5_installed_skills_current().status == "PASS"


def test_c6_dangling_hook(tmp_path, profile):
    assert cc.c6_hooks_point_at_scripts().status == "SKIP"
    real = tmp_path / "hook.py"
    real.write_text("", encoding="utf-8")
    gone = tmp_path / "moved.py"
    settings = {"hooks": {"PreToolUse": [{"hooks": [
        {"type": "command", "command": f'python "{real.as_posix()}"'},
        {"type": "command", "command": f"python {gone.as_posix()}"}]}]}}
    (profile / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    r = cc.c6_hooks_point_at_scripts()
    assert r.status == "FAIL" and "moved.py" in r.detail and "1 dangling of 2" in r.observed


def test_c7_brain_states(monkeypatch):
    monkeypatch.setattr(hm, "claude_brain", lambda: {"available": False,
                                                     "reason": "brain not set up (x)"})
    assert cc.c7_brain_reachable().status == "SKIP"
    monkeypatch.setattr(hm, "claude_brain", lambda: {"available": False,
                                                     "reason": "brain DB not found"})
    assert cc.c7_brain_reachable().status == "FAIL"
    monkeypatch.setattr(hm, "claude_brain", lambda: {"available": True, "schema_ok": True,
                                                     "messages": 5})
    assert cc.c7_brain_reachable().status == "PASS"


def test_c8_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(cc, "ROOT", tmp_path)
    sec = tmp_path / "bin" / "secrets"
    sec.mkdir(parents=True)
    (sec / "README.md").write_text("x", encoding="utf-8")
    (sec / "keyring.env.template").write_text("x", encoding="utf-8")
    assert cc.c8_secrets_restricted().status == "SKIP"
    (sec / "keyring.env").write_text("K=v", encoding="utf-8")
    monkeypatch.setattr(cc, "_broad_access", lambda p, runner=None: (True, "Everyone"))
    assert cc.c8_secrets_restricted().status == "FAIL"
    monkeypatch.setattr(cc, "_broad_access", lambda p, runner=None: (False, "owner"))
    assert cc.c8_secrets_restricted().status == "PASS"
    monkeypatch.setattr(cc, "_broad_access", lambda p, runner=None: (None, "icacls failed"))
    assert cc.c8_secrets_restricted().status == "BLIND"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_c8_posix_mode_bits(tmp_path):
    f = tmp_path / "s"
    f.write_text("x")
    f.chmod(0o644)
    assert cc._broad_access(f)[0] is True
    f.chmod(0o600)
    assert cc._broad_access(f)[0] is False


def test_c8_windows_icacls_parsing(tmp_path):
    f = tmp_path / "s"
    f.write_text("x")
    if os.name != "nt":
        pytest.skip("icacls path is Windows-only")
    run = lambda cmd, **k: types.SimpleNamespace(  # noqa: E731
        returncode=0, stdout=f"{f} BUILTIN\\Users:(RX)\n", stderr="")
    assert cc._broad_access(f, run) == (True, "BUILTIN\\Users")


def test_c10_untracked_threshold():
    run = lambda lines: (lambda cmd, **k: types.SimpleNamespace(  # noqa: E731
        returncode=0, stdout="\n".join(lines), stderr=""))
    assert cc.c10_work_has_a_recovery_point(run([" M a"] * 100)).status == "PASS"
    assert cc.c10_work_has_a_recovery_point(run(["?? f"] * 60)).status == "FAIL"
    bad = lambda cmd, **k: types.SimpleNamespace(returncode=128, stdout="",  # noqa: E731
                                                  stderr="fatal: not a git repository")
    assert cc.c10_work_has_a_recovery_point(bad).status == "SKIP"


def test_c11_ledger(hc_env):
    assert cc.c11_alert_ledger_readable().status == "SKIP"
    hc.mark_broken("x", "y")
    assert cc.c11_alert_ledger_readable().status == "PASS"
    hc.ALERT_STATE.write_text("[]", encoding="utf-8")
    assert cc.c11_alert_ledger_readable().status == "FAIL"


def test_crashed_assertion_is_blind_and_main_exits_2(hc_env, monkeypatch):
    def boom():
        raise RuntimeError("x")
    monkeypatch.setattr(cc, "ASSERTIONS", [boom])
    assert cc.run_all()[0].status == "BLIND"
    assert cc.main(["--dry-run"]) == 2


def test_main_records_checker_health_and_alerts_per_failure(hc_env, monkeypatch):
    monkeypatch.setattr(cc, "ASSERTIONS", [
        lambda: cc.Result("C1", "q1", "PASS", "", ""),
        lambda: cc.Result("C2", "q2", "FAIL", "broken", "")])
    assert cc.main([]) == 0                                 # the checker ran fine
    assert cc.main(["--exit-nonzero-on-fail"]) == 1
    assert hc.read_outcome("conformance-check")["status"] == "ok"
    assert [i["job"] for i in hc.open_issues()] == ["conformance:C2"]


# --- harness_metrics ------------------------------------------------------------------
def test_brain_db_path_from_config(monkeypatch, tmp_path):
    monkeypatch.setattr(hm, "ROOT", tmp_path)
    assert hm.brain_db_path()[0] is None
    (tmp_path / "claude-brain").mkdir()
    (tmp_path / "claude-brain" / "config.yaml").write_text(
        'storage:\n  local_db_path: "~/brain/x.db"\n', encoding="utf-8")
    p, _ = hm.brain_db_path()
    assert p.name == "x.db" and "~" not in str(p)
    assert hm.claude_brain()["available"] is False          # unmeasured, never 0


def test_credentials_reports_names_never_values(monkeypatch, tmp_path):
    monkeypatch.setattr(hm, "ROOT", tmp_path)
    assert hm.credentials()["available"] is False
    sec = tmp_path / "bin" / "secrets"
    sec.mkdir(parents=True)
    (sec / "keyring.env").write_text("# c\nALPHA_KEY=supersecretvalue\nBETA=x\n", encoding="utf-8")
    c = hm.credentials()
    assert c["items"] == ["ALPHA_KEY", "BETA"] and "supersecret" not in json.dumps(c)


def test_scheduled_jobs_blind_is_not_zero():
    m = hm.scheduled_jobs(lambda: (None, "offline"))
    assert m["installed"] == {"available": False, "reason": "offline"}
    m = hm.scheduled_jobs(lambda: ({"ghost": intro.Installed("ghost")}, "read"))
    assert m["installed_not_declared"] == ["ghost"]


def test_collect_runs_on_a_fresh_tree(profile):
    m = hm.collect(stable=True, query=lambda: ({}, "none"))
    assert "generated_at" not in m and m["hooks"]["wired_events"]["available"] is False
    assert "declared jobs" in hm.render(m)
