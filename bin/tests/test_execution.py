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


# =========================================================================== #
# Parity port: execution-layer hardening
# =========================================================================== #
from execution.actions.research_web import ResearchWeb  # noqa: E402


# --- policy: a corrupt guardrail file fails CLOSED ---
def test_policy_corrupt_file_locks_everything(tmp_path):
    """An unreadable/corrupt policy file must lock every class to NEVER — never fall
    back to the permissive DEFAULT (that would silently re-enable autonomy)."""
    bad = tmp_path / "execution_policy.json"
    bad.write_text("{this is not json", encoding="utf-8")
    cfg = policy.load_policy(bad)
    assert cfg == policy.LOCKED_POLICY
    r = score_action(FakeAction(_summary="fetch a page"))  # LOW-risk read
    for cls in policy.DEFAULT_POLICY:
        assert policy.decide(r, cls, policy=cfg).action == "NEVER"


def test_policy_non_table_json_locks_everything(tmp_path):
    bad = tmp_path / "execution_policy.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    assert policy.load_policy(bad) == policy.LOCKED_POLICY


def test_policy_missing_file_uses_default(tmp_path):
    cfg = policy.load_policy(tmp_path / "does-not-exist.json")
    assert cfg == policy.DEFAULT_POLICY  # read_external-only enabled


# --- read_web: redirects and single-label allowlist entries ---
def test_readweb_denies_redirect_to_unlisted_host():
    def fake(url, headers, timeout):   # a transport that followed a 302
        return 200, "exfiltrated", "https://elsewhere.test/collect?d=1"

    a = ReadWeb(url="https://example.com/r", allowlist=("example.com",), transport=fake)
    with pytest.raises(EgressDenied) as e:
        a.run()
    assert "elsewhere.test" in str(e.value)


def test_readweb_allows_redirect_within_allowlist_and_reports_final_url():
    def fake(url, headers, timeout):
        return 200, "ok", "https://cdn.example.com/r2"

    a = ReadWeb(url="https://example.com/r", allowlist=("example.com",), transport=fake)
    out = a.run()
    # The audit trail must name the host that served the bytes, not the one requested.
    assert out["url"] == "https://cdn.example.com/r2"


def test_readweb_two_tuple_transport_still_supported():
    a = ReadWeb(url="https://example.com/r", allowlist=("example.com",),
                transport=lambda u, h, t: (200, "body"))
    assert a.run()["url"] == "https://example.com/r"


@pytest.mark.parametrize("entry", ["com", ".com", "  com  "])
def test_host_allowed_rejects_single_label_entries(entry):
    """A bare TLD on the allowlist would match every host under it."""
    assert _host_allowed("anything.com", [entry]) is False


def test_host_allowed_strips_only_one_leading_dot():
    assert _host_allowed("api.example.com", [".example.com"]) is True
    assert _host_allowed("api.example.com", ["..com"]) is False


class _FakeResp:
    def __init__(self, status=200, url="https://example.com/r", body=b""):
        self.status, self.url, self._body = status, url, body
        self.asked = None

    def read(self, n=None):
        self.asked = n
        return self._body or (b"x" * (n or 10))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_readweb_default_transport_refuses_to_follow_redirects(monkeypatch):
    """The real _urllib_fetch must not follow 30x at all."""
    import urllib.request
    from execution.actions.read_web import _urllib_fetch

    seen = {}

    def fake_build_opener(*handlers):
        seen["handlers"] = handlers

        class _O:
            def open(self, req, timeout=None):
                return _FakeResp(302)
        return _O()

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    _urllib_fetch("https://example.com/r", {}, 5.0)
    h = seen["handlers"][0]
    inst = h() if isinstance(h, type) else h
    assert inst.redirect_request(None, None, 302, "Found", {}, "https://elsewhere.test/") is None


def test_readweb_bounds_the_read_not_just_the_return(monkeypatch):
    """max_bytes is applied AT THE READ so a huge body is never materialised."""
    import urllib.request
    from execution.actions.read_web import _urllib_fetch

    resp = _FakeResp()

    class _O:
        def open(self, req, timeout=None):
            return resp

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_h: _O())
    _urllib_fetch("https://example.com/big", {}, 5.0, 1000)
    assert resp.asked == 1001, "read() must be given a size bound, not called bare"


# --- approval: connections close; secrets never reach the DB ---
def test_approval_closes_its_connections(tmp_path, monkeypatch):
    """`with _conn(...)` commits but does NOT close; a long-lived process parking
    approvals in a loop must not accumulate open handles."""
    from execution import approval as ap_mod
    from runner import events as ev

    db = tmp_path / "runner.db"
    r = score_action(FakeAction(self_risk="MED", _summary="fetch a page"))
    opened, closed = [], []
    real_conn = ev._conn

    class _Proxy:
        """sqlite3.Connection.close is read-only, so count closes through a proxy."""

        def __init__(self, inner):
            object.__setattr__(self, "_inner", inner)

        def __getattr__(self, k):
            return getattr(self._inner, k)

        def __setattr__(self, k, v):
            setattr(self._inner, k, v)

        def __enter__(self):
            self._inner.__enter__()
            return self

        def __exit__(self, *a):
            return self._inner.__exit__(*a)

        def close(self):
            closed.append(self)
            return self._inner.close()

    def counting_conn(db_path=None):
        c = _Proxy(real_conn(db_path))
        opened.append(c)
        return c

    monkeypatch.setattr(ev, "_conn", counting_conn)
    rid = ev.start_run("approval-leak", db_path=db)
    for _ in range(5):
        a = ap_mod.request(rid, "read_external", r, "GET https://x", db_path=db)
        ap_mod.get(a, db_path=db)
        ap_mod.pending(db_path=db)
        ap_mod.latest_for("GET https://x", "read_external", db_path=db)
        ap_mod.resolve(a, True, db_path=db)
        ap_mod.consume(a, db_path=db)
    assert opened, "sanity: the patched connection factory was used"
    assert len(closed) == len(opened), (
        f"{len(opened) - len(closed)} sqlite connection(s) leaked")


SECRET_URL = "GET https://api.example.com/v1?api_key=sk-ABCDEFGH12345678WXYZ"


def test_approval_scrubs_summary_and_payload_before_storing(tmp_path):
    import sqlite3
    db = tmp_path / "runner.db"
    r = score_action(FakeAction(self_risk="MED", _summary="fetch a page"))
    ap = approval.request("r1", "read_external", r, SECRET_URL,
                          payload={"auth": "Bearer abc.def-123"}, db_path=db)
    with sqlite3.connect(db) as c:
        summary, payload = c.execute(
            "SELECT summary, payload FROM approvals WHERE id=?", (ap,)).fetchone()
    assert "sk-ABCDEFGH12345678WXYZ" not in summary and "[REDACTED]" in summary
    assert "abc.def-123" not in payload
    # latest_for is called with the RAW summary and still finds the scrubbed row.
    assert approval.latest_for(SECRET_URL, "read_external", db_path=db)["id"] == ap


def test_a_parked_action_with_a_secret_in_its_summary_can_still_resume(tmp_path):
    """The stored summary is scrubbed, so the resume comparison must be scrubbed to
    scrubbed — comparing the raw summary would leave this action parked forever."""
    db = tmp_path / "runner.db"
    runs = []

    class Secretive(FakeAction):
        def run(self):
            runs.append(1)
            return "ok"

    action = Secretive(self_risk="MED", _summary=SECRET_URL)
    parked = ex.execute(action, db_path=db)
    assert parked["status"] == "pending"
    approval.resolve(parked["approval_id"], True, db_path=db)
    res = ex.execute(action, db_path=db, approved_id=parked["approval_id"])
    assert res["status"] == "done" and res["decision"] == "APPROVED" and runs == [1]
    assert approval.get(parked["approval_id"], db_path=db)["status"] == "executed"


def test_scrubbed_match_does_not_widen_an_approval(tmp_path):
    """Two actions that differ only inside a secret scrub to the SAME stored summary.
    An approval given for one must not authorize the other: the row's digest of the
    raw summary pins the exact action."""
    db = tmp_path / "runner.db"
    a1 = FakeAction(self_risk="MED", _summary="GET https://x?token=sk-AAAAAAAAAAAAAAAA1")
    a2 = FakeAction(self_risk="MED", _summary="GET https://x?token=sk-BBBBBBBBBBBBBBBB2")
    parked = ex.execute(a1, db_path=db)
    approval.resolve(parked["approval_id"], True, db_path=db)
    assert ex.execute(a2, db_path=db, approved_id=parked["approval_id"])["status"] == "pending"
    assert approval.get(parked["approval_id"], db_path=db)["status"] == "approved"  # unspent
    assert ex.execute(a1, db_path=db, approved_id=parked["approval_id"])["status"] == "done"
    # and the lookup used by research does not hand a1's decision to a2
    newest = approval.latest_for(a2.summary(), a2.action_class, db_path=db)
    assert newest is not None and newest["id"] != parked["approval_id"]


def test_legacy_row_without_digest_matches_only_a_secret_free_summary(tmp_path):
    """Rows written before the digest column stored the summary RAW. Such a row must
    still resume the same plain action it always did, and nothing else."""
    import sqlite3
    db = tmp_path / "runner.db"
    plain = FakeAction(self_risk="MED", _summary="fetch a page")
    parked = ex.execute(plain, db_path=db)
    with sqlite3.connect(db) as c:          # simulate a pre-digest row
        c.execute("UPDATE approvals SET action_digest=NULL, status='approved'")
    assert ex.execute(plain, db_path=db, approved_id=parked["approval_id"])["status"] == "done"

    secret = FakeAction(self_risk="MED", _summary=SECRET_URL)
    parked2 = ex.execute(secret, db_path=db)
    with sqlite3.connect(db) as c:          # a legacy row held the raw, unscrubbed text
        c.execute("UPDATE approvals SET action_digest=NULL, status='approved', summary=?"
                  " WHERE id=?", (SECRET_URL, parked2["approval_id"]))
    assert ex.execute(secret, db_path=db,
                      approved_id=parked2["approval_id"])["status"] == "pending"


# --- redaction derives from the canonical shape list ---
def test_redaction_derives_from_the_canonical_list_not_a_copy():
    """Re-inlining a private pattern list in redaction.py re-creates the drift."""
    import re
    from execution.secret_patterns import SECRET_PATTERNS
    assert [p.pattern for p in redaction._PATTERNS] == [re.compile(x).pattern
                                                         for x in SECRET_PATTERNS]


# --- research_web: the goal-loop fetch as a gated read_external action ---
def test_researchweb_benign_question_autos_and_logs(tmp_path):
    db = tmp_path / "runner.db"
    a = ResearchWeb(question="open-source static site generators compared",
                    fetcher=lambda q, t: f"summary about {q}")
    res = ex.execute(a, db_path=db)
    assert res["decision"] == "AUTO" and res["status"] == "done"
    assert res["result"] == "summary about open-source static site generators compared"
    evs = events.get_events(res["run_id"], db_path=db)
    assert any(e["event_type"] == "action:done" for e in evs)


def test_researchweb_risky_question_parks_without_fetching(tmp_path):
    db = tmp_path / "runner.db"

    def boom(q, t):  # must NOT be called — the gate decides before the fetch
        raise AssertionError("fetcher called for a parked action")

    a = ResearchWeb(question="how to sign up and pay for a seller account", fetcher=boom)
    res = ex.execute(a, db_path=db)
    assert res["decision"] == "PAUSE" and res["status"] == "pending"
    assert approval.get(res["approval_id"], db_path=db)["status"] == "pending"


def test_researchweb_fetch_failure_recorded_as_error(tmp_path):
    db = tmp_path / "runner.db"

    def fail(q, t):
        raise RuntimeError("claude -p research fetch failed [rate_limited]")

    res = ex.execute(ResearchWeb(question="benign topic", fetcher=fail), db_path=db)
    assert res["status"] == "error" and res["result"] is None
    err = [e for e in events.get_events(res["run_id"], db_path=db) if e["status"] == "error"]
    assert err and err[0]["needs_attention"] == 1


# --- execute: per-invocation audit, crash logging, kill-switch ---
def test_execute_logs_invoke_on_every_branch(tmp_path):
    """AUTO, PAUSE and NEVER all emit action:invoke with action class + target +
    caller + policy source before the branch runs."""
    db = tmp_path / "runner.db"
    cases = [
        (FakeAction(_summary="fetch a page"), "AUTO"),
        (FakeAction(self_risk="MED", _summary="fetch a page"), "PAUSE"),
        (FakeAction(action_class="external_mutate", _summary="fetch"), "NEVER"),
    ]
    for action, expected in cases:
        res = ex.execute(action, db_path=db)
        assert res["decision"] == expected
        evs = events.get_events(res["run_id"], db_path=db)
        inv = [e for e in evs if e["event_type"] == "action:invoke"]
        assert inv, f"missing action:invoke on {expected} branch"
        p = inv[0]["payload"]
        assert action.action_class in p
        assert action.summary() in p
        assert '"caller": "test_execution.py:' in p   # the real calling file, not execute.py
        assert "fresh-load" in p


def test_execute_prelog_failure_still_logs_invoke(tmp_path):
    """A crash before the branch (summary() raising) leaves an invoke-with-error audit
    trail and closes the run row — never an invisible exit or a zombie 'running' row."""
    db = tmp_path / "runner.db"

    class SummaryBoom(FakeAction):
        def summary(self):
            raise RuntimeError("summary exploded")

    with pytest.raises(RuntimeError, match="summary exploded"):
        ex.execute(SummaryBoom(), db_path=db)
    runs, evs = events.fetch_since(0, db_path=db)
    inv = [e for e in evs if e["event_type"] == "action:invoke"]
    assert inv and inv[0]["status"] == "error"
    assert "summary exploded" in inv[0]["payload"] and inv[0]["needs_attention"] == 1
    assert runs and runs[0]["status"] == "error"


def test_execute_invoke_flags_caller_supplied_policy(tmp_path):
    db = tmp_path / "runner.db"
    res = ex.execute(FakeAction(_summary="fetch a page"), db_path=db,
                     policy_cfg=policy.DEFAULT_POLICY)
    evs = events.get_events(res["run_id"], db_path=db)
    inv = [e for e in evs if e["event_type"] == "action:invoke"]
    assert inv and "caller-supplied" in inv[0]["payload"]


class _Guard:
    """A RunGuard double: check() honours the STOP file, record() counts."""

    def __init__(self, stop_file):
        self.stop_file = stop_file
        self.records = 0

    def check(self):
        from runner.guard import Halted
        if self.stop_file.exists():
            raise Halted("STOP file present")

    def record(self, cost=0.0):
        self.records += 1


def test_execute_stop_engaged_before_action_halts_and_never_runs(tmp_path):
    db, stop = tmp_path / "runner.db", tmp_path / "STOP"
    stop.write_text("{}", encoding="utf-8")
    ran = []

    class Tracked(FakeAction):
        def run(self):
            ran.append(1)
            return "ok"

    res = ex.execute(Tracked(_summary="fetch a page"), db_path=db, guard=_Guard(stop))
    assert res["status"] == "halted" and ran == []
    assert events.get_run(res["run_id"], db_path=db)["status"] == "halted"


def test_execute_stop_engaged_during_action_is_caught_after_it(tmp_path):
    """Kill-switch re-check AFTER the action bounds the check-then-act race to the one
    action already in flight, and the owned run row ends 'halted', not 'running'."""
    db, stop = tmp_path / "runner.db", tmp_path / "STOP"

    class EngagesStop(FakeAction):
        def run(self):
            stop.write_text("{}", encoding="utf-8")   # operator hits STOP mid-action
            return "partial"

    g = _Guard(stop)
    res = ex.execute(EngagesStop(_summary="fetch a page"), db_path=db, guard=g)
    assert res["status"] == "halted" and g.records == 1
    run = events.get_run(res["run_id"], db_path=db)
    assert run["status"] == "halted" and "post-action" in (run["halt_reason"] or "")
    evs = events.get_events(res["run_id"], db_path=db)
    assert any(e["event_type"] == "action:halted" and e["needs_attention"] for e in evs)


def test_execute_halt_inside_a_callers_run_propagates(tmp_path):
    """When the caller owns the run (a runner batch), Halted propagates so the batch
    stops and the owner ends the run."""
    from runner.guard import Halted
    db, stop = tmp_path / "runner.db", tmp_path / "STOP"
    stop.write_text("{}", encoding="utf-8")
    rid = events.start_run("batch", db_path=db)
    with pytest.raises(Halted):
        ex.execute(FakeAction(_summary="fetch a page"), run_id=rid, db_path=db,
                   guard=_Guard(stop))
    assert events.get_run(rid, db_path=db)["status"] == "running"   # owner's to close


# --- risk: unrecognized self-hints fail CLOSED ---
@pytest.mark.parametrize("hint,expected", [
    ("high", "HIGH"), ("High", "HIGH"), ("med", "MED"), ("  low  ", "LOW"),
])
def test_risk_self_hint_case_and_whitespace_are_normalized(hint, expected):
    r = score_action(FakeAction(self_risk=hint, _summary="fetch a page"))
    assert r.level == expected
    assert not any("unrecognized" in x for x in r.reasons)


@pytest.mark.parametrize("hint", ["CRITICAL", "SEVERE", "unknown", "", "  "])
def test_risk_unrecognized_self_hint_scores_high_not_low(hint):
    """An unreadable token used to resolve to LOW and leave no trace in the reasons."""
    r = score_action(FakeAction(self_risk=hint, _summary="fetch a page"))
    assert r.level == "HIGH"
    assert any("unrecognized" in x for x in r.reasons), "the discarded token left no trace"


def test_risk_unrecognized_self_hint_cannot_auto_run():
    r = score_action(FakeAction(self_risk="critical", _summary="fetch a page"))
    assert policy.decide(r, "read_external").action != "AUTO"


@pytest.mark.parametrize("hint,expected", [("LOW", "LOW"), ("MED", "MED"), ("HIGH", "HIGH")])
def test_risk_known_hints_are_unchanged(hint, expected):
    r = score_action(FakeAction(self_risk=hint, _summary="fetch a page"))
    assert r.level == expected
    assert not any("unrecognized" in x for x in r.reasons)
