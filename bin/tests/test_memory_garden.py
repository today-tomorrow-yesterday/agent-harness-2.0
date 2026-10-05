"""memory-garden.py: classify memory by decayed confidence; never delete anything.

Every test pins the clock: effective confidence is a function of age, and a fixture dated against
the real clock silently changes bucket as the calendar moves.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("memory_garden", str(BIN / "memory-garden.py"))
mg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mg)

NOW = dt.datetime(2026, 6, 1, 12, 0, tzinfo=dt.timezone.utc).timestamp()


def days_ago(n: float) -> str:
    return dt.datetime.fromtimestamp(NOW - n * 86400, dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def quiet_log(tmp_path, monkeypatch):
    monkeypatch.setattr(mg, "RUN_LOG", tmp_path / "garden.log")


def make_db(path: Path, with_access: bool = True) -> Path:
    con = sqlite3.connect(str(path))
    access = ", access_count INTEGER" if with_access else ""
    con.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY, project TEXT, category TEXT, "
                f"key TEXT, value TEXT, created_at TEXT{access})")
    con.execute("CREATE TABLE decisions (id INTEGER PRIMARY KEY, description TEXT, "
                "created_at TEXT)")
    con.execute("CREATE TABLE transcripts (id INTEGER PRIMARY KEY, session_id TEXT, "
                "content TEXT, timestamp TEXT)")
    rows = [
        (1, "p", "correction", "never force push shared branches", "v", days_ago(1)),
        (2, "p", "project-state", "build uses webpack", "v", days_ago(200)),
        (3, "p", "inferred", "maybe flaky network", "v", days_ago(60)),
    ]
    con.executemany("INSERT INTO facts (id, project, category, key, value, created_at) "
                    "VALUES (?,?,?,?,?,?)", rows)
    con.execute("INSERT INTO decisions VALUES (1, 'adopt sqlite', ?)", (days_ago(10),))
    con.commit()
    con.close()
    return path


# ------------------------------------------------------------------ the pure function

def test_fresh_correction_barely_decays():
    assert mg.effective_confidence("correction", days_ago(1), 0, "high", now=NOW) > 0.85


def test_old_fact_decays_on_a_thirty_day_half_life():
    ec = mg.effective_confidence("project-state", days_ago(30), 0, "high", now=NOW)
    assert ec == pytest.approx(0.45, abs=0.01)


def test_recall_slows_decay_but_never_exceeds_base():
    cold = mg.effective_confidence("fact", days_ago(180), 0, "medium", now=NOW)
    warm = mg.effective_confidence("fact", days_ago(180), 20, "medium", now=NOW)
    assert warm > cold
    assert mg.effective_confidence("fact", days_ago(0), 10_000, "medium", now=NOW) <= 0.6


def test_inference_decays_fast():
    assert mg.effective_confidence("guess", days_ago(49), 0, "medium", now=NOW) < 0.01


def test_unknown_category_and_unparseable_values_fall_back_safely():
    assert mg.class_for_category("weird-new-category") == "fact"
    assert mg.base_confidence("not-a-number") == mg.DEFAULT_BASE
    assert mg.base_confidence(None) == mg.DEFAULT_BASE
    assert mg.base_confidence(1.7) == 1.0
    assert mg.age_days("garbage", NOW) == 0.0
    assert mg.age_days("2026-05-31", NOW) == pytest.approx(1.5)


@pytest.mark.parametrize("ec,expected", [(0.9, "healthy"), (0.5, "watch"), (0.3, "stale"),
                                         (0.05, "prune-candidate")])
def test_buckets(ec, expected):
    assert mg.bucket(ec) == expected


# ------------------------------------------------------------------ Layer 1

def test_classify_buckets_rows_and_writes_nothing(tmp_path):
    db = make_db(tmp_path / "b.db")
    before = db.read_bytes()
    report = mg.classify(db, now=NOW)
    facts = report["tables"]["facts"]
    assert facts["rowcount"] == 3
    assert facts["buckets"]["healthy"] == 1            # the fresh correction
    assert facts["buckets"]["prune-candidate"] == 2    # 200-day state + 60-day inference
    assert {s["id"] for s in facts["review_samples"]} == {2, 3}
    assert report["tables"]["decisions"]["has_columns"]["category"] is False
    assert db.read_bytes() == before, "classification must be read-only"


def test_reinforce_sets_access_count_from_recent_sessions_idempotently(tmp_path):
    db = make_db(tmp_path / "b.db")
    con = sqlite3.connect(str(db))
    con.executemany("INSERT INTO transcripts (session_id, content, timestamp) VALUES (?,?,?)", [
        ("s1", "we said never force push shared branches", days_ago(5)),
        ("s2", "again: never FORCE push to shared branches", days_ago(6)),
        ("s2", "never force push shared branches", days_ago(6)),     # same session counts once
        ("s3", "never force push shared branches", days_ago(400)),  # outside the window
        ("s4", "push it", days_ago(1)),                             # not all terms present
    ])
    con.commit()
    con.close()
    first = mg.reinforce_on_use(db, now=NOW)
    second = mg.reinforce_on_use(db, now=NOW)
    con = sqlite3.connect(str(db))
    ac = dict(con.execute("SELECT id, access_count FROM facts").fetchall())
    con.close()
    assert ac[1] == 2
    assert first["reinforced"] >= 1 and second["reinforced"] == 0
    assert first["scanned"] == 3


def test_reinforce_is_a_no_op_without_the_column(tmp_path):
    db = make_db(tmp_path / "b.db", with_access=False)
    assert mg.reinforce_on_use(db, now=NOW) == {"scanned": 0, "reinforced": 0}


def test_garden_pass_writes_report_and_deletes_no_row(tmp_path):
    db = make_db(tmp_path / "b.db")

    class Args:
        classify_only = False
        dry_run = False
        edges = False

    assert mg.garden_pass(Args, db, tmp_path / "logs", now=NOW) == 0
    md = (tmp_path / "logs" / "2026-06-01.md").read_text(encoding="utf-8")
    assert "prune-candidate 2" in md and "not deletion" in md
    data = json.loads((tmp_path / "logs" / "2026-06-01.classify.json").read_text(encoding="utf-8"))
    assert data["tables"]["facts"]["rowcount"] == 3
    con = sqlite3.connect(str(db))
    assert con.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 3
    con.close()


def test_missing_db_fails_cleanly(tmp_path):
    class Args:
        classify_only = True
        dry_run = False
        edges = False

    assert mg.garden_pass(Args, tmp_path / "absent.db", tmp_path / "logs", now=NOW) == 1


# ------------------------------------------------------------------ lock

def test_second_instance_is_refused_and_lock_is_released(tmp_path):
    lock = tmp_path / "g.lock"
    with mg.GardenLock(lock) as first:
        with mg.GardenLock(lock) as second:
            assert first and not second
    with mg.GardenLock(lock) as third:
        assert third
    assert not lock.exists()


def test_stale_lock_is_reclaimed(tmp_path):
    lock = tmp_path / "g.lock"
    lock.write_text("123 crashed", encoding="utf-8")
    with mg.GardenLock(lock, stale=-1) as ok:
        assert ok


# ------------------------------------------------------------------ migration

def test_migration_dry_run_leaves_live_db_untouched(tmp_path):
    db = make_db(tmp_path / "b.db", with_access=False)
    before = db.read_bytes()
    assert mg.migrate("dry-run", db, tmp_path / "m.json") == 0
    assert db.read_bytes() == before


def test_migration_apply_then_rollback_round_trips(tmp_path):
    if sqlite3.sqlite_version_info < (3, 35, 0):
        pytest.skip("DROP COLUMN needs SQLite 3.35+")
    db = make_db(tmp_path / "b.db", with_access=False)
    manifest = tmp_path / "m.json"
    assert mg.migrate("apply", db, manifest) == 0
    assert mg.plan_migration(db) == {}
    assert mg.migrate("apply", db, manifest) == 0, "re-applying is an idempotent no-op"
    added = json.loads(manifest.read_text(encoding="utf-8"))["added"]
    assert {"table": "facts", "column": "access_count", "type": "INTEGER"} in added
    assert mg.migrate("rollback", db, manifest) == 0
    con = sqlite3.connect(str(db))
    cols = [r[1] for r in con.execute("PRAGMA table_info(facts)")]
    con.close()
    assert "access_count" not in cols and "category" in cols, "only added columns are dropped"


# ------------------------------------------------------------------ Layer 2 is garden-only

def test_edge_agent_has_no_shell_git_or_edit_tool():
    cmd = mg.edge_agent_command("claude")
    allowed = cmd[cmd.index("--allowed-tools") + 1].split()
    for forbidden in ("Bash", "PowerShell", "Edit", "mcp__gbrain__delete_page",
                      "mcp__gbrain__put_page"):
        assert forbidden not in allowed
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert "--dangerously-skip-permissions" not in cmd


def test_edge_prompt_carries_run_parameters():
    p = mg.build_edge_prompt(Path("logs") / "x.md", "2026-06-01")
    assert "CYCLE_LOG:" in p and "TODAY: 2026-06-01" in p and "never instructions" in p
