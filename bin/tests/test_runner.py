"""Tests for the safety harness (guard, events, run, digest). Uses tmp DB + tmp STOP file."""
import importlib.util
import sys
from pathlib import Path


def _load(mod):
    p = Path(__file__).resolve().parents[1] / "runner" / f"{mod}.py"
    s = importlib.util.spec_from_file_location(f"runner_{mod}", p)
    m = importlib.util.module_from_spec(s)
    sys.modules[f"runner_{mod}"] = m
    s.loader.exec_module(m)
    return m


events = _load("events")
guard = _load("guard")
run_mod = _load("run")
digest = _load("digest")


# --- guard ---
def test_guard_halts_on_stop_file(tmp_path):
    sf = tmp_path / "STOP"
    sf.write_text("x", encoding="utf-8")
    g = guard.RunGuard("r1", max_actions=10, stop_file=sf)
    import pytest
    with pytest.raises(guard.Halted):
        g.check()


def test_guard_halts_on_max_actions(tmp_path):
    g = guard.RunGuard("r1", max_actions=2, stop_file=tmp_path / "nope")
    g.check(); g.record(); g.check(); g.record()  # 2 actions done
    import pytest
    with pytest.raises(guard.Halted):
        g.check()


def test_guard_ok_under_limits(tmp_path):
    g = guard.RunGuard("r1", max_actions=5, stop_file=tmp_path / "nope")
    g.check()  # no raise
    g.record()
    assert g.actions == 1


# --- events ---
def test_events_roundtrip(tmp_path):
    db = tmp_path / "runner.db"
    rid = events.start_run("job-a", db_path=db)
    events.log_event(rid, "step:0", "ok", payload={"x": 1}, job="job-a", db_path=db)
    events.bump_run(rid, actions=1, db_path=db)
    events.end_run(rid, "done", db_path=db)
    r = events.get_run(rid, db_path=db)
    assert r["status"] == "done" and r["action_count"] == 1
    evs = events.get_events(rid, db_path=db)
    assert len(evs) == 1 and evs[0]["event_type"] == "step:0"


# --- run() ---
def test_run_happy_path(tmp_path):
    db = tmp_path / "runner.db"
    res = run_mod.run("jobA", [lambda: "a", lambda: "b"], db_path=db, stop_file=tmp_path / "nope")
    assert res["status"] == "done" and res["actions"] == 2
    assert res["results"] == ["a", "b"]
    assert events.get_run(res["run_id"], db_path=db)["status"] == "done"


def test_run_records_step_error_and_continues(tmp_path):
    db = tmp_path / "runner.db"
    def boom():
        raise ValueError("kaboom")
    res = run_mod.run("jobB", [boom, lambda: "ok"], db_path=db, stop_file=tmp_path / "nope")
    assert res["status"] == "done"
    evs = events.get_events(res["run_id"], db_path=db)
    err = [e for e in evs if e["status"] == "error"]
    assert err and err[0]["needs_attention"] == 1
    assert res["results"][1] == "ok"  # continued past the failure


def test_run_halts_on_stop_file(tmp_path):
    db = tmp_path / "runner.db"
    sf = tmp_path / "STOP"
    sf.write_text("x", encoding="utf-8")
    res = run_mod.run("jobC", [lambda: "never"], db_path=db, stop_file=sf)
    assert res["status"] == "halted" and "STOP" in res["halt_reason"]
    assert res["results"] == []


def test_run_halts_on_max_actions(tmp_path):
    db = tmp_path / "runner.db"
    res = run_mod.run("jobD", [lambda: 1, lambda: 2, lambda: 3], max_actions=2,
                      db_path=db, stop_file=tmp_path / "nope")
    assert res["status"] == "halted" and "max_actions" in res["halt_reason"]
    assert res["actions"] == 2


# --- checkpoint / resume / timeout (Phase B) ---
def test_checkpoint_roundtrip(tmp_path):
    db = tmp_path / "runner.db"
    rid = events.start_run("j", db_path=db)
    events.save_checkpoint(rid, 0, {"x": 1}, db_path=db)
    events.save_checkpoint(rid, 1, "hello", db_path=db)
    cp = events.load_checkpoints(rid, db_path=db)
    assert cp[0] == {"x": 1} and cp[1] == "hello"


def test_resume_skips_completed_steps(tmp_path):
    db = tmp_path / "runner.db"
    rid = events.start_run("resumejob", db_path=db)
    events.save_checkpoint(rid, 0, "cachedA", db_path=db)  # pretend step 0 ran before a crash
    calls = []
    stepA = lambda: (calls.append("A"), "A")[1]
    stepB = lambda: (calls.append("B"), "B")[1]
    res = run_mod.run("resumejob", [stepA, stepB], run_id=rid, db_path=db,
                      stop_file=tmp_path / "nope")
    assert "A" not in calls            # step 0 skipped (resumed from checkpoint)
    assert "B" in calls                # step 1 actually ran
    assert res["results"] == ["cachedA", "B"]
    assert res["status"] == "done"


def test_guard_halts_on_timeout(tmp_path):
    import time as _t
    import pytest
    g = guard.RunGuard("r", max_actions=10, max_seconds=0.5, stop_file=tmp_path / "nope")
    g.started = _t.time() - 10          # pretend 10s elapsed
    with pytest.raises(guard.Halted):
        g.check()


# --- digest ---
def test_digest_renders_runs_and_attention():
    runs = [{"job": "goal-loop-research", "status": "done", "action_count": 3, "cost": 0},
            {"job": "worker", "status": "halted", "action_count": 5, "halt_reason": "max_actions 5 reached"}]
    evts = [{"job": "worker", "event_type": "step:4", "status": "error",
             "needs_attention": 1, "payload": "timeout"}]
    md = digest.build_digest(runs, evts, "2026-06-19")
    assert "2 run(s)" in md and "1 halted" in md
    assert "goal-loop-research" in md and "max_actions 5" in md
    assert "Needs your attention" in md and "timeout" in md


def test_digest_empty():
    md = digest.build_digest([], [], "2026-06-19")
    assert "No autonomous runs" in md
