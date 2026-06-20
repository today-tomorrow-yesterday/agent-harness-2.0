"""Tests for the Execution Layer (risk, policy, approval, redaction, secrets,
execute, read_web). Runs from bin/ — inserts bin on sys.path so `execution` and
`runner` import as packages. Uses a tmp runner.db.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

BIN = Path(__file__).resolve().parents[1]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import pytest  # noqa: E402

from execution import approval, policy, redaction  # noqa: E402
from execution import secrets as secrets_mod  # noqa: E402
from execution import execute as ex  # noqa: E402
from execution.risk import score_action  # noqa: E402
from execution.actions.read_web import ReadWeb, EgressDenied, _host_allowed  # noqa: E402
from runner import events  # noqa: E402


# --- test doubles ---
@dataclass
class FakeAction:
    name: str = "fake"
    action_class: str = "read_external"
    blast_radius: str = "none"
    self_risk: str = "LOW"
    _summary: str = "a harmless read"
    _result = "ok"

    def summary(self):
        return self._summary

    def run(self):
        return self._result


class BoomAction(FakeAction):
    def run(self):
        raise ValueError("kaboom")


# --- risk ---
def test_risk_floor_forces_high_on_destructive():
    a = FakeAction(_summary="rm -rf the workspace")
    assert score_action(a).level == "HIGH"


def test_risk_max_severity_floor_beats_low_self_hint():
    a = FakeAction(self_risk="LOW", _summary="please delete the user account")
    r = score_action(a)
    assert r.level == "HIGH"  # floor wins over the action's LOW self-claim


def test_risk_benign_read_is_low():
    a = FakeAction(_summary="fetch a public docs page")
    assert score_action(a).level == "LOW"


def test_risk_self_hint_can_raise():
    a = FakeAction(self_risk="MED", _summary="fetch a page")
    assert score_action(a).level == "MED"


# --- policy ---
def test_policy_read_external_low_is_auto():
    r = score_action(FakeAction(_summary="fetch a page"))
    assert policy.decide(r, "read_external").action == "AUTO"


def test_policy_read_external_med_pauses():
    r = score_action(FakeAction(self_risk="MED", _summary="fetch a page"))
    assert policy.decide(r, "read_external").action == "PAUSE"


def test_policy_disabled_class_never_auto():
    r = score_action(FakeAction(blast_radius="workspace", _summary="write a scratch file"))
    # write_workspace LOW would be PAUSE; never AUTO regardless
    assert policy.decide(r, "write_workspace").action != "AUTO"


def test_policy_external_mutate_always_never():
    for hint in ("LOW", "MED", "HIGH"):
        r = score_action(FakeAction(self_risk=hint, _summary="fetch a page"))
        assert policy.decide(r, "external_mutate").action == "NEVER"


def test_policy_unknown_class_never():
    r = score_action(FakeAction(_summary="x"))
    assert policy.decide(r, "made_up_class").action == "NEVER"


# --- approval ---
def test_approval_roundtrip(tmp_path):
    db = tmp_path / "runner.db"
    rid = events.start_run("j", db_path=db)
    r = score_action(FakeAction(self_risk="MED", _summary="fetch a page"))
    ap = approval.request(rid, "read_external", r, "GET https://x", db_path=db)
    assert approval.get(ap, db_path=db)["status"] == "pending"
    assert any(p["id"] == ap for p in approval.pending(db_path=db))
    assert approval.resolve(ap, True, by="operator", db_path=db) is True
    assert approval.get(ap, db_path=db)["status"] == "approved"
    assert approval.pending(db_path=db) == []
    # second resolve is a no-op (already resolved)
    assert approval.resolve(ap, True, db_path=db) is False


def test_approval_reject(tmp_path):
    db = tmp_path / "runner.db"
    rid = events.start_run("j", db_path=db)
    r = score_action(FakeAction(self_risk="MED", _summary="fetch"))
    ap = approval.request(rid, "read_external", r, "GET https://y", db_path=db)
    assert approval.resolve(ap, False, db_path=db) is True
    assert approval.get(ap, db_path=db)["status"] == "rejected"


# --- redaction / secrets ---
def test_redaction_scrubs_registered_secret():
    redaction.clear()
    redaction.register_secret("hunter2-supersecret")
    assert "hunter2-supersecret" not in redaction.scrub("token=hunter2-supersecret done")
    redaction.clear()


def test_redaction_regex_catches_bearer():
    redaction.clear()
    out = redaction.scrub("Authorization: Bearer abc.def-123")
    assert "abc.def-123" not in out


def test_secretstr_never_renders():
    s = secrets_mod.SecretStr("topsecret")
    assert "topsecret" not in str(s)
    assert "topsecret" not in repr(s)
    assert "topsecret" not in f"{s}"
    assert s.get_secret_value() == "topsecret"


# --- read_web ---
def test_host_allowed_matches_subdomain():
    assert _host_allowed("api.example.com", ("example.com",)) is True
    assert _host_allowed("evil.com", ("example.com",)) is False
    assert _host_allowed("example.com", ()) is False  # default-deny


def test_readweb_allowlisted_fetches():
    calls = {}

    def fake(url, headers, timeout):
        calls["url"] = url
        return 200, "<html>hi</html>"

    a = ReadWeb(url="https://example.com/x", allowlist=("example.com",), transport=fake)
    out = a.run()
    assert out["status"] == 200 and "hi" in out["text"]
    assert calls["url"] == "https://example.com/x"


def test_readweb_blocks_non_allowlisted():
    def fake(url, headers, timeout):  # must NOT be called
        raise AssertionError("transport called for a denied host")

    a = ReadWeb(url="https://evil.com/x", allowlist=("example.com",), transport=fake)
    with pytest.raises(EgressDenied):
        a.run()


# --- execute (the orchestrator) ---
def test_execute_auto_runs_and_logs(tmp_path):
    db = tmp_path / "runner.db"
    res = ex.execute(FakeAction(_summary="fetch a page"), db_path=db)
    assert res["decision"] == "AUTO" and res["status"] == "done" and res["result"] == "ok"
    evs = events.get_events(res["run_id"], db_path=db)
    assert any(e["event_type"] == "action:done" for e in evs)


def test_execute_pause_parks_and_does_not_run(tmp_path):
    db = tmp_path / "runner.db"
    res = ex.execute(FakeAction(self_risk="MED", _summary="fetch a page"), db_path=db)
    assert res["status"] == "pending" and res["approval_id"]
    assert approval.get(res["approval_id"], db_path=db)["status"] == "pending"
    evs = events.get_events(res["run_id"], db_path=db)
    assert any(e["event_type"] == "action:pending" for e in evs)


def test_execute_never_refuses(tmp_path):
    db = tmp_path / "runner.db"
    res = ex.execute(FakeAction(action_class="external_mutate", _summary="fetch"), db_path=db)
    assert res["status"] == "refused" and res["result"] is None
    evs = events.get_events(res["run_id"], db_path=db)
    assert any(e["event_type"] == "action:blocked" for e in evs)


def test_execute_action_error_is_recorded(tmp_path):
    db = tmp_path / "runner.db"
    res = ex.execute(BoomAction(_summary="fetch a page"), db_path=db)
    assert res["status"] == "error" and res["result"] is None
    err = [e for e in events.get_events(res["run_id"], db_path=db) if e["status"] == "error"]
    assert err and err[0]["needs_attention"] == 1


def test_execute_egress_denied_is_blocked(tmp_path):
    db = tmp_path / "runner.db"
    a = ReadWeb(url="https://evil.com/x", allowlist=("example.com",))
    res = ex.execute(a, db_path=db)
    assert res["status"] == "blocked"
    evs = events.get_events(res["run_id"], db_path=db)
    assert any(e["event_type"] == "action:blocked" for e in evs)


def test_execute_logged_payload_is_scrubbed(tmp_path):
    db = tmp_path / "runner.db"
    redaction.clear()
    redaction.register_secret("leaky-token-xyz")
    a = FakeAction(_summary="fetch a page")
    a._result = "response contains leaky-token-xyz oops"
    res = ex.execute(a, db_path=db)
    evs = events.get_events(res["run_id"], db_path=db)
    blob = " ".join(str(e["payload"]) for e in evs)
    assert "leaky-token-xyz" not in blob
    redaction.clear()
