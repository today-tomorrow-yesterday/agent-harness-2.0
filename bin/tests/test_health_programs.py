"""Tests for the smaller health programs: skill_canary, sibling_sweep, golden_run,
rule_contradictions, auth_canary, tmp_purge, release_gate, fleet_status, record_outcome.
Every model call and subprocess is faked; the clock is pinned; state goes to tmp."""
from __future__ import annotations

import json
import os
import types

import pytest

import auth_canary as ac
import fleet_status as fs
import golden_run as gr
import harness_common as hc
import record_outcome as ro
import release_gate as rg
import rule_contradictions as rc
import sibling_sweep as ss
import skill_canary as sc
import tmp_purge as tp
from _health_fixtures import PINNED, hc_env, iso  # noqa: F401


# --- skill_canary -------------------------------------------------------------------
@pytest.fixture
def canary(tmp_path, monkeypatch):
    repo = tmp_path / "skills"
    prof = tmp_path / "profile"
    monkeypatch.setattr(sc, "ROOT", tmp_path)
    monkeypatch.setattr(sc, "CANONICAL_SKILLS", repo)
    monkeypatch.setattr(sc, "SNAPSHOT_ROOT", tmp_path / "forge" / "skill-versions")
    monkeypatch.setattr(sc, "EVOLUTION_LOG", tmp_path / "forge" / "evolution.jsonl")
    (repo / "demo").mkdir(parents=True)
    (repo / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: A demo skill.\n---\n\nBody v2.\n", encoding="utf-8")
    (prof / "demo").mkdir(parents=True)
    (prof / "demo" / "SKILL.md").write_text("old v1", encoding="utf-8")
    return types.SimpleNamespace(repo=repo, prof=prof, profiles={"p": prof})


def test_canary_passes_a_good_skill(canary):
    ok, checks, crash = sc.smoke_test("demo")
    assert ok and crash is None and any(c["name"] == "skill_policy" for c in checks)


@pytest.mark.parametrize("body,needle", [
    ("no frontmatter at all", "no YAML frontmatter"),
    ("---\nname: other\ndescription: d\n---\n", "directory is 'demo'"),
    ("﻿---\nname: demo\ndescription: d\n---\n", "BOM"),
])
def test_canary_fails_a_malformed_skill(canary, body, needle):
    (canary.repo / "demo" / "SKILL.md").write_text(body, encoding="utf-8")
    ok, _, crash = sc.smoke_test("demo")
    assert not ok and needle in crash["message"]


def test_canary_fails_a_broken_helper(canary):
    (canary.repo / "demo" / "helper.py").write_text("def (:\n", encoding="utf-8")
    ok, _, crash = sc.smoke_test("demo")
    assert not ok and crash["check"] == "compile:helper.py"


def test_gate_failure_leaves_the_profile_untouched(canary):
    (canary.repo / "demo" / "SKILL.md").write_text("broken", encoding="utf-8")
    assert sc.run_gate("demo", canary.profiles, True, "t") == 1
    assert (canary.prof / "demo" / "SKILL.md").read_text(encoding="utf-8") == "old v1"
    rec = json.loads(sc.EVOLUTION_LOG.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["canary"] == "Failed" and rec["crash"]


def test_promote_then_rollback_roundtrip(canary):
    assert sc.run_gate("demo", canary.profiles, True, "t") == 0
    assert "Body v2" in (canary.prof / "demo" / "SKILL.md").read_text(encoding="utf-8")
    assert sc.rollback("demo", canary.profiles) == 0
    assert (canary.prof / "demo" / "SKILL.md").read_text(encoding="utf-8") == "old v1"


def test_check_all_is_read_only(canary):
    assert sc.check_all() == 0
    assert not sc.SNAPSHOT_ROOT.exists() and not sc.EVOLUTION_LOG.exists()


# --- sibling_sweep -----------------------------------------------------------------
def _sweep(tmp_path, name, body):
    (tmp_path / name).write_text(body, encoding="utf-8")
    return {r.name: [f.line for f in r.findings] for r in ss.sweep(tmp_path)}


def test_dry_run_rule(tmp_path):
    body = ('ap.add_argument("--dry-run")\nrecord_outcome("x")\n')
    assert _sweep(tmp_path, "a.py", body)["dry-run-writes-health"] == [1]
    assert _sweep(tmp_path, "a.py", body + "set_dry_run(True)\n")["dry-run-writes-health"] == []


def test_claude_without_clean_env_rule(tmp_path):
    body = 'import subprocess\nsubprocess.run(["claude", "-p", "hi"])\n'
    assert _sweep(tmp_path, "b.py", body)["claude-p-without-clean-env"] == [2]
    fixed = body.replace(")\n", ", env=clean_env())\n")
    assert _sweep(tmp_path, "b.py", fixed)["claude-p-without-clean-env"] == []


def test_shell_grant_rule_ignores_disallow_lists(tmp_path):
    grant = 'cmd = ["claude", "-p", "--allowed-tools", "Read Bash"]\n'
    assert _sweep(tmp_path, "c.py", grant)["shell-grant-without-untrusted-rule"] == [1]
    deny = 'cmd = ["claude", "-p", "--disallowed-tools", "Read Bash"]\n'
    assert _sweep(tmp_path, "c.py", deny)["shell-grant-without-untrusted-rule"] == []


def test_mtime_and_allowlist_rules_and_named_pragma(tmp_path):
    body = "import re\nage = (now - p.stat().st_mtime) / 86400\n"
    assert _sweep(tmp_path, "d.py", body)["mtime-as-content-age"] == [2]
    named = "# sibling-sweep: ok mtime-as-content-age — scratch file\n" + body
    assert _sweep(tmp_path, "d.py", named)["mtime-as-content-age"] == []
    unnamed = "# sibling-sweep: ok — vague\n" + body
    (tmp_path / "d.py").write_text(unnamed, encoding="utf-8")
    got = {r.name: r.findings for r in ss.sweep(tmp_path)}
    assert "does not name this rule" in got["mtime-as-content-age"][0].detail
    allow = '# allowlist of safe names\nSAFE = re.compile(r"^[a-z]+")\n'
    assert _sweep(tmp_path, "e.py", allow)["prefix-check-called-an-allowlist"] == [2]
    assert _sweep(tmp_path, "e.py", allow.replace('+")', '+$")'))[
        "prefix-check-called-an-allowlist"] == []


# --- golden_run --------------------------------------------------------------------
def test_golden_check_assertions():
    assert gr.check({"equals": "negative"}, " Negative ")[0]
    assert gr.check({"contains": "paris"}, "It is Paris.")[0]
    assert not gr.check({"not_equals": "PWNED"}, "PWNED.")[0]
    assert gr.check({"not_equals": "PWNED"}, "The input tried to make me say PWNED.")[0]


def test_shipped_golden_cases_load_and_have_assertions():
    cases = gr.load_cases("structured-judgment")
    assert len(cases) >= 4 and all("expect" in c and "id" in c for c in cases)


def _golden_env(tmp_path, monkeypatch):
    d = tmp_path / "golden"
    d.mkdir()
    (d / "fam.jsonl").write_text(
        '{"_comment": "x"}\n'
        '{"id": "a", "task": "t", "input": "", "expect": {"equals": "yes"}}\n'
        '{"id": "b", "task": "t", "input": "", "expect": {"equals": "yes"}}\n',
        encoding="utf-8")
    monkeypatch.setattr(gr, "GOLDEN_DIR", d)
    monkeypatch.setattr(gr, "HISTORY", tmp_path / "hist.jsonl")


def _res(ok=True, status="ok", verdicts=("yes", "yes"), error=""):
    value = {"reasoning": "", "results": [{"id": i, "verdict": v}
                                          for i, v in zip("ab", verdicts)]}
    return lambda *a, **k: hc.ClaudeResult(ok, status, value if ok else None, error)


def test_golden_run_records_series_and_pages_on_regression(hc_env, tmp_path, monkeypatch):
    _golden_env(tmp_path, monkeypatch)
    assert gr.run("fam", call=_res()) == 0
    assert gr.baseline("fam") == 1.0
    assert gr.run("fam", call=_res(verdicts=("no", "no"))) == 1
    assert "pass rate fell" in hc_env.posts[-1][1]
    assert len(gr.HISTORY.read_text(encoding="utf-8").splitlines()) == 2


def test_golden_transient_is_kept_out_of_the_series(hc_env, tmp_path, monkeypatch):
    _golden_env(tmp_path, monkeypatch)
    assert gr.run("fam", call=_res(ok=False, status="rate_limited")) == 0
    assert not gr.HISTORY.exists()
    assert hc.read_outcome("golden-run")["status"] == "rate_limited"


def test_golden_refusal_is_the_drift_signal(hc_env, tmp_path, monkeypatch):
    _golden_env(tmp_path, monkeypatch)
    assert gr.run("fam", call=_res(ok=False, status="refused")) == 1
    row = json.loads(gr.HISTORY.read_text(encoding="utf-8"))
    assert row["passed"] == 0 and hc_env.posts


# --- rule_contradictions ------------------------------------------------------------
def _rules(tmp_path):
    mem = tmp_path / "memory"
    (mem / "feedback").mkdir(parents=True)
    (mem / "feedback" / "a.md").write_text(
        "Drafts always go to `notes/drafts/inbox.md`.\n", encoding="utf-8")
    (mem / "feedback" / "b.md").write_text(
        "Never write to notes/drafts/inbox.md; save drafts in notes/new/.\n", encoding="utf-8")
    (mem / "c.md").write_text("See notes/drafts/inbox.md for history.\n", encoding="utf-8")
    (mem / "d.md").write_text("Use this and/or that -> always.\n", encoding="utf-8")
    return mem


def test_candidates_need_a_directive_and_a_distinctive_path(tmp_path):
    cands, texts = rc.find_candidates(_rules(tmp_path))
    assert len(texts) == 4
    assert [(a.name, b.name, p) for a, b, p in cands] == [("a.md", "b.md", "notes/drafts/inbox.md")]
    assert rc._distinctive("and/or") is None and rc._distinctive("bin/x.py") == "bin/x.py"


def test_judge_caches_verdicts_and_fences_untrusted_text(hc_env, tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "CACHE", tmp_path / "cache.json")
    mem = _rules(tmp_path)
    cands, texts = rc.find_candidates(mem)
    prompts = []

    def call(prompt, schema, **k):
        prompts.append(prompt)
        return hc.ClaudeResult(True, "ok", {"verdict": "contradiction", "reason": "r"})
    findings, judged, errors = rc.judge(cands, texts, 5, mem, call=call)
    assert len(findings) == 1 and judged == 1 and errors == 0
    assert "<<<UNTRUSTED CONTENT" in prompts[0]
    rc.judge(cands, texts, 5, mem, call=lambda *a, **k: 1 / 0)    # served from cache
    assert len(prompts) == 1


# --- auth_canary --------------------------------------------------------------------
def test_session_probe_is_tri_state():
    assert ac.probe_session(os_name="Linux")["interactive"] is None
    run = lambda cmd, **k: types.SimpleNamespace(  # noqa: E731
        returncode=0, stdout='"NT AUTHORITY\\BATCH","S-1-5-3"', stderr="")
    assert ac.probe_session(run, os_name="Windows")["interactive"] is False
    fail = lambda cmd, **k: types.SimpleNamespace(returncode=1, stdout="", stderr="")  # noqa: E731
    assert ac.probe_session(fail, os_name="Windows")["interactive"] is None


def test_auth_call_uses_the_subscription_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "metered")
    monkeypatch.setattr(hc, "_claude_bin", lambda: "claude")
    seen = {}

    def run(cmd, **k):
        seen.update(k)
        return types.SimpleNamespace(returncode=0, stdout="OK", stderr="")
    assert ac.call_claude(run)["verdict"].startswith("PASS")
    assert "ANTHROPIC_API_KEY" not in seen["env"]
    bad = lambda cmd, **k: types.SimpleNamespace(  # noqa: E731
        returncode=1, stdout="Please run /login", stderr="")
    assert ac.call_claude(bad)["verdict"].startswith("FAIL: auth_failed")


# --- tmp_purge ----------------------------------------------------------------------
def test_purge_refuses_dangerous_targets(tmp_path):
    assert tp.refuse_reason(tp.ROOT) and tp.refuse_reason(tp.Path.home())
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    assert "git" in tp.refuse_reason(tmp_path / "repo")
    assert tp.refuse_reason(tmp_path) is None


def test_purge_deletes_only_old_files(tmp_path):
    old, new, keep = tmp_path / "sub" / "old.html", tmp_path / "new.html", tmp_path / "README.md"
    old.parent.mkdir()
    for f in (old, new, keep):
        f.write_text("x")
    os.utime(old, (PINNED - 20 * 86400,) * 2)
    os.utime(keep, (PINNED - 20 * 86400,) * 2)
    os.utime(new, (PINNED - 1 * 86400,) * 2)
    assert tp.purge(tmp_path, 14, dry_run=True, now=PINNED)[0] == 1 and old.exists()
    assert tp.purge(tmp_path, 14, dry_run=False, now=PINNED)[0] == 1
    assert not old.exists() and not old.parent.exists() and new.exists() and keep.exists()


# --- release_gate ---------------------------------------------------------------------
def test_release_gate_requires_every_check(tmp_path):
    ok = lambda cmd, **k: types.SimpleNamespace(returncode=0, stdout="fine", stderr="")  # noqa: E731
    log = tmp_path / "eval.jsonl"
    assert rg.gate(ok, log) is True
    red = lambda cmd, **k: types.SimpleNamespace(  # noqa: E731
        returncode=1 if "skill_canary.py" in " ".join(cmd) else 0, stdout="x", stderr="")
    assert rg.gate(red, log) is False
    rows = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()]
    assert [r["all_passed"] for r in rows] == [True, False]


# --- fleet_status ---------------------------------------------------------------------
def _fleet(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "SELFTEST_REPORT", tmp_path / "self-test-report.md")
    monkeypatch.setattr(fs, "HEARTBEAT", tmp_path / "hb")
    from runner import events
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "runner.db")


def test_fresh_install_is_unknown_not_all_clear(hc_env, tmp_path, monkeypatch):
    _fleet(tmp_path, monkeypatch)
    s = fs.gather()
    assert not s["problems"] and all(v["state"] == "unknown" for v in s["jobs"].values())
    assert "not an all-clear" in fs.render(s)


def test_stale_heartbeat_pages_about_self_loop(hc_env, tmp_path, monkeypatch):
    _fleet(tmp_path, monkeypatch)
    hc.record_outcome("self-loop", status="ok", produced=1)
    (tmp_path / "hb").write_text(iso(-50), encoding="utf-8")
    hc.record_outcome("self-test", status="error", produced=0)
    s = fs.gather()
    assert any("heartbeat stale" in p for p in s["problems"])
    assert s["jobs"]["self-test"]["state"] == "bad"
    assert fs.main(["--dry-run"]) == 0 and not hc_env.posts
    fs.main([])
    [issue] = hc.open_issues()
    assert issue["job"] == "self-loop" and issue["raised_by"] == "fleet-status"


# --- record_outcome CLI ---------------------------------------------------------------
def test_record_outcome_cli(hc_env):
    assert ro.main(["brain-embed", "--status", "ok", "--produced", "12"]) == 0
    oc = hc.read_outcome("brain-embed")
    assert oc["status"] == "ok" and oc["produced"] == 12
    with pytest.raises(SystemExit):
        ro.main(["x", "--status", "great"])
