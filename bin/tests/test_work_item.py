"""Per-item progress in runner.db (runner/events.py work_item table).

A kill partway through a batch must not discard the items already finished, and a
permanently broken item must stop consuming a slot on every future run.
"""
import importlib.util
import sys
from pathlib import Path

import pytest


def _load_events():
    p = Path(__file__).resolve().parents[1] / "runner" / "events.py"
    s = importlib.util.spec_from_file_location("runner_events_work_item", p)
    m = importlib.util.module_from_spec(s)
    sys.modules["runner_events_work_item"] = m
    s.loader.exec_module(m)
    return m


events = _load_events()


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "runner.db")


def test_unknown_item_is_processable(db):
    assert events.should_process("j", "a", db_path=db) is True


def test_completed_item_is_skipped_on_rerun(db):
    events.start_item("j", "a", db_path=db)
    events.complete_item("j", "a", {"v": 1}, db_path=db)
    assert events.should_process("j", "a", db_path=db) is False


def test_failed_item_is_retried(db):
    events.start_item("j", "a", db_path=db)
    events.fail_item("j", "a", "boom", db_path=db)
    assert events.should_process("j", "a", db_path=db) is True


def test_item_quarantines_after_three_attempts_and_stops_being_retried(db):
    for expected in ("failed", "failed", "quarantined"):
        events.start_item("j", "a", db_path=db)
        assert events.fail_item("j", "a", "always broken", db_path=db) == expected
    assert events.should_process("j", "a", db_path=db) is False


def test_permanent_failure_quarantines_immediately(db):
    events.start_item("j", "a", db_path=db)
    assert events.fail_item("j", "a", "refused", permanent=True, db_path=db) == "quarantined"
    assert events.should_process("j", "a", db_path=db) is False


def test_partial_batch_survives_a_kill(db):
    """Kill after item 2 of 5; the resumed run must only do 3, 4, 5."""
    items = ["i1", "i2", "i3", "i4", "i5"]
    for it in items[:2]:
        events.start_item("j", it, batch_id="b1", db_path=db)
        events.complete_item("j", it, {"ok": True}, db_path=db)
    # ---- process killed here ----
    remaining = [it for it in items if events.should_process("j", it, db_path=db)]
    assert remaining == ["i3", "i4", "i5"], remaining


def test_attempts_accumulate_across_runs(db):
    events.start_item("j", "a", db_path=db)
    events.fail_item("j", "a", "e1", db_path=db)
    assert events.start_item("j", "a", db_path=db) == 2


def test_a_recurring_job_reruns_next_batch(db):
    events.start_item("j", "alpha", batch_id="2026-W30", db_path=db)
    events.complete_item("j", "alpha", db_path=db)
    assert events.should_process("j", "alpha", db_path=db, batch_id="2026-W30") is False
    assert events.should_process("j", "alpha", db_path=db, batch_id="2026-W31") is True


def test_three_failures_across_three_batches_quarantine(db):
    """Quarantine must outlive the cycle; folding the week into item_id would reset it."""
    st = ""
    for wk in ("2026-W30", "2026-W31", "2026-W32"):
        assert events.should_process("j", "bravo", db_path=db, batch_id=wk) is True
        events.start_item("j", "bravo", batch_id=wk, db_path=db)
        st = events.fail_item("j", "bravo", "boom", db_path=db)
    assert st == "quarantined"
    assert events.should_process("j", "bravo", db_path=db, batch_id="2026-W33") is False


def test_success_resets_the_attempt_count(db):
    """Three failures spread out over time are not the same signal as three in a row."""
    for wk in ("2026-W30", "2026-W31"):
        events.start_item("j", "charlie", batch_id=wk, db_path=db)
        events.fail_item("j", "charlie", "flaky", db_path=db)
    events.start_item("j", "charlie", batch_id="2026-W32", db_path=db)
    events.complete_item("j", "charlie", db_path=db)
    events.start_item("j", "charlie", batch_id="2026-W33", db_path=db)
    assert events.fail_item("j", "charlie", "one bad week", db_path=db) == "failed"


def test_batchless_callers_keep_done_once_semantics(db):
    events.start_item("j", "session-abc", db_path=db)
    events.complete_item("j", "session-abc", db_path=db)
    assert events.should_process("j", "session-abc", db_path=db) is False


def test_same_item_id_in_two_jobs_does_not_collide(db):
    events.start_item("jobA", "shared-id", db_path=db)
    events.complete_item("jobA", "shared-id", db_path=db)
    assert events.should_process("jobA", "shared-id", db_path=db) is False
    assert events.should_process("jobB", "shared-id", db_path=db) is True


def test_item_counts_and_quarantined_listing(db):
    events.start_item("j", "ok1", db_path=db)
    events.complete_item("j", "ok1", db_path=db)
    events.start_item("j", "bad", db_path=db)
    events.fail_item("j", "bad", "nope", permanent=True, db_path=db)
    counts = events.item_counts("j", db_path=db)
    assert counts.get("done") == 1 and counts.get("quarantined") == 1
    q = events.quarantined_items("j", db_path=db)
    assert len(q) == 1 and q[0]["item_id"] == "bad" and "nope" in q[0]["error"]


def test_unserializable_result_does_not_lose_the_done_status(db):
    """The work DID happen; only its payload could not be stored. Re-running would
    repeat a completed side effect, so the item stays done."""
    events.start_item("j", "a", db_path=db)
    events.complete_item("j", "a", object(), db_path=db)
    assert events.should_process("j", "a", db_path=db) is False
