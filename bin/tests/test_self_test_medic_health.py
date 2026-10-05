"""Tests for the merged improvements in bin/self_test.py and bin/test_medic.py.
No pytest is spawned, no model is called; components and subprocesses are faked."""
from __future__ import annotations

import types

import harness_common as hc
import self_test as st
import test_medic as tm
from _health_fixtures import hc_env  # noqa: F401


# --- self_test ------------------------------------------------------------------------
def test_brain_health_warn_exit_is_not_a_failure(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("x", encoding="utf-8")
    monkeypatch.setattr(st, "BRAIN_CONFIG", cfg)
    for rc, out, want in ((1, "Score: 9/10 WARN", "pass"), (2, "Score: 5/10", "fail"),
                          (0, "row FAIL", "fail"), (0, "Score: 10/10", "pass")):
        monkeypatch.setattr(st.subprocess, "run",
                            lambda *a, _rc=rc, _o=out, **k: types.SimpleNamespace(
                                returncode=_rc, stdout=_o, stderr=""))
        assert st.run_brain_health()[0] == want, (rc, out)


def test_scheduler_component_maps_unknown_to_skip(monkeypatch):
    import verify_scheduled_tasks as vst
    monkeypatch.setattr(vst, "verify", lambda: ("unknown", ["NOT CONFIGURED: none installed"]))
    assert st.check_scheduler() == ("skip", "NOT CONFIGURED: none installed")
    monkeypatch.setattr(vst, "verify", lambda: ("fail", ["x", "  FAIL DECLARED-NOT-INSTALLED a"]))
    status, detail = st.check_scheduler()
    assert status == "fail" and "1 drift" in detail


def _fake_components(monkeypatch, suite_status):
    monkeypatch.setattr(st, "run_pytest_suite", lambda: (suite_status, "3 passed"))
    monkeypatch.setattr(st, "run_brain_health", lambda: ("skip", "not set up"))
    monkeypatch.setattr(st, "probe_gbrain", lambda: ("skip", "not set up"))
    monkeypatch.setattr(st, "check_scheduler", lambda: ("skip", "not installed"))


def test_red_verdict_alerts_and_green_clears(hc_env, monkeypatch, tmp_path):
    monkeypatch.setattr(st, "REPORT", tmp_path / "self-test-report.md")
    args = types.SimpleNamespace(print_only=False)
    _fake_components(monkeypatch, "fail")
    assert st._run_and_report(args) == 1
    assert "VERDICT: FAIL" in (tmp_path / "self-test-report.md").read_text(encoding="utf-8")
    assert [i["job"] for i in hc.open_issues()] == ["self-test"] and len(hc_env.posts) == 1
    _fake_components(monkeypatch, "pass")
    assert st._run_and_report(args) == 0
    assert hc.open_issues() == []
    oc = hc.read_outcome("self-test")
    assert oc["status"] == "ok" and "PASS" in oc["detail"] and "skipped" in oc["detail"]


def test_self_test_defers_to_a_running_instance(hc_env, monkeypatch):
    monkeypatch.setattr(st.sys, "argv", ["self_test.py"])
    monkeypatch.setattr(st, "_run_and_report", lambda a: 1 / 0)
    with hc.single_instance("self-test"):
        assert st.main() == 0


# --- test_medic -----------------------------------------------------------------------
def test_medic_spawn_uses_clean_env_and_shared_classifier(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "metered")
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return types.SimpleNamespace(returncode=1, stdout="You've hit your session limit",
                                     stderr="")
    monkeypatch.setattr(tm.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(tm.subprocess, "run", fake_run)
    status, _ = tm.invoke_medic("diag")
    assert status == "rate_limited"
    assert "ANTHROPIC_API_KEY" not in seen["env"]


def test_medic_dry_run_never_pages(hc_env, monkeypatch, tmp_path):
    monkeypatch.setattr(tm, "REPORT", tmp_path / "medic.md")
    monkeypatch.setattr(tm, "LOG_PATH", tmp_path / "medic.log")
    monkeypatch.setattr(tm, "run_self_test", lambda: (False, "red"))
    monkeypatch.setattr(tm, "collect_diagnosis", lambda: "diag")
    monkeypatch.setattr(tm, "invoke_medic", lambda d: 1 / 0)
    monkeypatch.setattr(tm.sys, "argv", ["test_medic.py", "--dry-run"])
    assert tm.main() == 1
    assert not hc_env.posts and not hc.OUTCOMES_DIR.exists()
    assert "dry-run" in (tmp_path / "medic.md").read_text(encoding="utf-8")


def test_medic_still_red_pages_once_and_fix_posts_green(hc_env, monkeypatch, tmp_path):
    monkeypatch.setattr(tm, "REPORT", tmp_path / "medic.md")
    monkeypatch.setattr(tm, "LOG_PATH", tmp_path / "medic.log")
    monkeypatch.setattr(tm, "collect_diagnosis", lambda: "diag")
    monkeypatch.setattr(tm, "invoke_medic", lambda d: ("ok", "MEDIC: ESCALATED"))
    monkeypatch.setattr(tm, "repo_head", lambda: "abc")
    monkeypatch.setattr(tm.sys, "argv", ["test_medic.py"])
    monkeypatch.setattr(tm, "run_self_test", lambda: (False, "red"))
    assert tm.main() == 1 and tm.main() == 1
    assert len(hc_env.posts) == 1                          # chronic red stays silent
    monkeypatch.setattr(tm, "run_self_test", iter([(False, "red"), (True, "green")]).__next__)
    assert tm.main() == 0
    # one green line, and the red condition is cleared from the ledger
    assert len(hc_env.posts) == 2 and "fixed" in hc_env.posts[-1][1]
    assert hc.open_issues() == []
