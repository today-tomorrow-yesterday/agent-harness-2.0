"""Tests for three defects found in review of the goal-loop catch-up:

1. A research question that parked for approval could never run: approving it
   changed a row and nothing read the row, and every later run queued a duplicate.
2. Paused goals were only filtered by a helper nobody called.
3. The skill refiner exited 0 on an expired login, so a failure that needs a human
   was recorded as a successful run.
"""
import importlib.util
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

BIN = Path(__file__).resolve().parents[1]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from execution import approval  # noqa: E402
from execution import execute as ex  # noqa: E402
from goal_loop import assess, questions, recommend, research  # noqa: E402

RISKY = "Research how to sign up for a seller account"   # trips the risk floor -> PAUSE


@dataclass
class FakeAction:
    name: str = "fake"
    action_class: str = "read_external"
    blast_radius: str = "none"
    self_risk: str = "MED"            # MED read_external -> PAUSE
    _summary: str = "fetch a page"
    runs: int = 0

    def summary(self):
        return self._summary

    def run(self):
        self.runs += 1
        return "ok"


def _approvals(db):
    with sqlite3.connect(db) as c:
        return c.execute("SELECT id, status, summary FROM approvals ORDER BY id").fetchall()


# --------------------------------------------------------------------------- #
# 1. Approved actions resume
# --------------------------------------------------------------------------- #
def test_an_approved_action_runs_once_and_spends_the_approval(tmp_path):
    db = tmp_path / "runner.db"
    action = FakeAction()
    parked = ex.execute(action, db_path=db)
    assert parked["status"] == "pending" and action.runs == 0
    approval.resolve(parked["approval_id"], True, db_path=db)

    res = ex.execute(action, db_path=db, approved_id=parked["approval_id"])
    assert res["status"] == "done" and res["decision"] == "APPROVED" and action.runs == 1
    assert approval.get(parked["approval_id"], db_path=db)["status"] == "executed"

    # the same approval cannot authorize a second run
    again = ex.execute(action, db_path=db, approved_id=parked["approval_id"])
    assert again["status"] == "pending" and action.runs == 1


def test_an_approval_does_not_cover_a_different_action(tmp_path):
    db = tmp_path / "runner.db"
    parked = ex.execute(FakeAction(_summary="fetch page A"), db_path=db)
    approval.resolve(parked["approval_id"], True, db_path=db)
    other = FakeAction(_summary="fetch page B")
    res = ex.execute(other, db_path=db, approved_id=parked["approval_id"])
    assert res["status"] == "pending" and other.runs == 0
    assert approval.get(parked["approval_id"], db_path=db)["status"] == "approved"  # unspent


def test_a_pending_or_rejected_approval_authorizes_nothing(tmp_path):
    db = tmp_path / "runner.db"
    action = FakeAction()
    parked = ex.execute(action, db_path=db)
    assert ex.execute(action, db_path=db, approved_id=parked["approval_id"])["status"] == "pending"
    approval.resolve(parked["approval_id"], False, db_path=db)
    assert ex.execute(action, db_path=db, approved_id=parked["approval_id"])["status"] == "pending"
    assert action.runs == 0


def test_no_approval_overrides_never(tmp_path):
    db = tmp_path / "runner.db"
    paused = FakeAction()
    parked = ex.execute(paused, db_path=db)
    approval.resolve(parked["approval_id"], True, db_path=db)
    forbidden = FakeAction(action_class="external_mutate")   # same summary, NEVER class
    res = ex.execute(forbidden, db_path=db, approved_id=parked["approval_id"])
    assert res["status"] == "refused" and forbidden.runs == 0


def test_parked_research_runs_after_approval(tmp_path):
    db = tmp_path / "runner.db"
    calls = []

    def fetch(question, timeout):
        calls.append(question)
        return "the findings"

    assert research.run_research(RISKY, db_path=db, fetcher=fetch) is None
    rows = _approvals(db)
    assert len(rows) == 1 and rows[0][1] == "pending" and RISKY in rows[0][2]

    approval.resolve(rows[0][0], True, db_path=db)
    out = research.run_research(RISKY, db_path=db, fetcher=fetch)
    assert calls == [RISKY]
    assert out.startswith(research.Q_OPEN) and "the findings" in out
    assert _approvals(db)[0][1] == "executed"


def test_a_waiting_question_is_not_queued_twice(tmp_path):
    db = tmp_path / "runner.db"

    def never(question, timeout):
        raise AssertionError("fetched without approval")

    for _ in range(3):   # three weekly runs, operator has not answered yet
        assert research.run_research(RISKY, db_path=db, fetcher=never) is None
    assert len(_approvals(db)) == 1


def test_a_rejected_question_is_not_asked_again(tmp_path):
    db = tmp_path / "runner.db"

    def never(question, timeout):
        raise AssertionError("fetched a rejected question")

    research.run_research(RISKY, db_path=db, fetcher=never)
    approval.resolve(_approvals(db)[0][0], False, db_path=db)
    assert research.run_research(RISKY, db_path=db, fetcher=never) is None
    rows = _approvals(db)
    assert len(rows) == 1 and rows[0][1] == "rejected"


# --------------------------------------------------------------------------- #
# 2. Paused goals are skipped by the APIs themselves
# --------------------------------------------------------------------------- #
GOALS = [
    {"id": "G1", "title": "Active", "status": "stalled", "last_moved": "2026-06-01",
     "next_step": "Research the launch checklist"},
    {"id": "G2", "title": "Set aside", "status": "paused (owner's call)",
     "last_moved": "2026-06-01", "next_step": "Research pricing"},
]


def test_paused_goals_get_no_verdict_question_recommendation_or_research():
    verdicts = assess.assess_progress(GOALS, {})
    assert [v["id"] for v in verdicts] == ["G1"]
    assert all(q.startswith("G1 ") for q in questions.generate_questions(verdicts, GOALS))
    assert [r["id"] for r in recommend.recommend_actions(GOALS, verdicts)] == ["G1"]
    assert [g["id"] for g in research.select_for_research(GOALS, cap=5)] == ["G1"]
    assert list(research.research_dispatch(GOALS, cap=5, dry_run=True)) == ["G1"]


# --------------------------------------------------------------------------- #
# 3. An expired login fails the refiner run
# --------------------------------------------------------------------------- #
def _load_refiner(tmp_path, monkeypatch, status):
    spec = importlib.util.spec_from_file_location("skill_refiner_under_test", BIN / "skill-refiner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    db = tmp_path / "brain.db"
    sqlite3.connect(db).close()
    monkeypatch.setattr(mod.config, "BRAIN_DB", db)
    monkeypatch.setattr(mod.config, "LOG_PATH", tmp_path / "skill-forge.log")
    monkeypatch.setattr(mod.config, "REPORT_PATH", tmp_path / "report-latest.md")
    monkeypatch.setattr(mod.config, "EVOLUTION_LOG", tmp_path / "evolution.jsonl")
    monkeypatch.setattr(mod, "list_skills", lambda _dir: [{"name": "some-skill"}])

    def boom(*_args, **_kwargs):
        raise mod.SessionPoolExhausted(status, "3pm" if status == "rate_limited" else None)
    monkeypatch.setattr(mod, "score_skill", boom)
    monkeypatch.setattr(mod, "make_claude_invoker", lambda: (lambda prompt: None))

    sent = []

    class FakeSlack:
        @staticmethod
        def post_slack(text, title=None):
            sent.append((title, text))
            return True
    monkeypatch.setitem(sys.modules, "notify_slack", FakeSlack)
    monkeypatch.setattr(sys, "argv", ["skill-refiner.py"])
    return mod, sent


def test_expired_login_is_a_failed_run_and_says_so(tmp_path, monkeypatch):
    mod, sent = _load_refiner(tmp_path, monkeypatch, "auth_failed")
    assert mod.main() == 1
    assert len(sent) == 1 and "re-auth" in sent[0][0]
    assert not (tmp_path / "report-latest.md").exists()   # no partial report written
    assert "[ERROR]" in (tmp_path / "skill-forge.log").read_text(encoding="utf-8")


def test_rate_limit_is_a_clean_skip(tmp_path, monkeypatch):
    mod, sent = _load_refiner(tmp_path, monkeypatch, "rate_limited")
    assert mod.main() == 0
    assert sent == []
    assert not (tmp_path / "report-latest.md").exists()
