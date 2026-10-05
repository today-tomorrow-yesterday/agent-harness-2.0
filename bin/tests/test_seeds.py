"""The Idea Cultivation seedbank (goal_loop/seeds.py), its CLI and the Slack nudge.
Every test uses a tmp seedbank and an injected clock — nothing reads the real date."""
import importlib.util
import json
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parents[1]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from goal_loop import seeds  # noqa: E402

DAY = 86400
NOW = 100 * DAY            # a fixed instant; no test depends on today's date


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_under_test",
                                                  BIN / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_capture_and_list(tmp_path):
    db = tmp_path / "seedbank.json"
    sid = seeds.capture("a scroll-driven story site", detail="a long read as a site",
                        source="session", now_ts=1000, path=db)
    rows = seeds.list_seeds(path=db)
    assert len(rows) == 1
    s = rows[0]
    assert s["id"] == sid and s["text"] == "a scroll-driven story site"
    assert s["status"] == "new" and s["surface_count"] == 0
    assert s["last_surfaced_at"] is None and s["captured_at"] == 1000


def test_missing_or_corrupt_seedbank_reads_as_empty(tmp_path):
    assert seeds.list_seeds(path=tmp_path / "absent.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert seeds.list_seeds(path=bad) == []
    bad.write_text("[1, 2]", encoding="utf-8")       # valid JSON, wrong shape
    assert seeds.list_seeds(path=bad) == []


def test_save_is_atomic_and_leaves_no_tmp(tmp_path):
    db = tmp_path / "seedbank.json"
    seeds.capture("x", now_ts=1, path=db)
    assert json.loads(db.read_text(encoding="utf-8"))["seeds"][0]["text"] == "x"
    assert not (tmp_path / "seedbank.json.tmp").exists()


def test_due_for_review_cadence(tmp_path):
    db = tmp_path / "seedbank.json"
    fresh = seeds.capture("never surfaced", now_ts=NOW, path=db)
    recent = seeds.capture("surfaced yesterday", now_ts=NOW, path=db)
    old = seeds.capture("surfaced last week", now_ts=NOW, path=db)
    seeds.mark_surfaced([recent], now_ts=NOW - 1 * DAY, path=db)
    seeds.mark_surfaced([old], now_ts=NOW - 7 * DAY, path=db)
    due_ids = {s["id"] for s in seeds.due_for_review(NOW, cadence_days=3.5, path=db)}
    assert fresh in due_ids and old in due_ids
    assert recent not in due_ids


def test_let_go_seed_never_resurfaces(tmp_path):
    db = tmp_path / "seedbank.json"
    sid = seeds.capture("dead idea", now_ts=NOW, path=db)
    seeds.resolve(sid, "let_go", now_ts=NOW, path=db)
    assert seeds.due_for_review(NOW + 30 * DAY, cadence_days=1, path=db) == []
    assert seeds.list_seeds(status="let_go", path=db)[0]["id"] == sid


def test_resolve_transitions_and_logs(tmp_path):
    db = tmp_path / "seedbank.json"
    a = seeds.capture("water me", now_ts=10, path=db)
    b = seeds.capture("refine me", now_ts=10, path=db)
    c = seeds.capture("snooze me", now_ts=10, path=db)
    d = seeds.capture("graduate me", now_ts=10, path=db)
    assert seeds.resolve(a, "water", note="go", now_ts=20, path=db) is True
    seeds.resolve(b, "refine", now_ts=20, path=db)
    seeds.resolve(c, "snooze", now_ts=20, path=db)
    seeds.resolve(d, "graduate", now_ts=20, path=db)
    by_id = {s["id"]: s for s in seeds.list_seeds(path=db)}
    assert by_id[a]["status"] == "growing"
    assert by_id[b]["status"] == "refining"
    assert by_id[c]["status"] == "new"          # snooze keeps status, resets the clock
    assert by_id[c]["last_surfaced_at"] == 20
    assert by_id[d]["status"] == "graduated"
    assert by_id[a]["verdicts"][0] == {"ts": 20, "verdict": "water", "note": "go"}


def test_resolve_unknown_id_or_verdict(tmp_path):
    db = tmp_path / "seedbank.json"
    sid = seeds.capture("x", now_ts=1, path=db)
    assert seeds.resolve("nope", "water", path=db) is False
    assert seeds.resolve(sid, "obliterate", path=db) is False
    assert seeds.list_seeds(path=db)[0]["verdicts"] == []


def test_render_review_has_seed_and_prompt():
    rows = [{"id": "ab12", "text": "scroll story-site", "detail": "d",
             "status": "new", "surface_count": 0}]
    md = seeds.render_review(rows, today="2026-01-15")
    assert md.startswith("## Seed Review — 2026-01-15")
    assert "scroll story-site" in md and "ab12" in md
    assert "water / refine / let go" in md


def test_render_review_empty():
    assert "seedbank is quiet" in seeds.render_review([])


# --------------------------------------------------------------- seeds-cli
def test_cli_add_list_and_decide(tmp_path, capsys):
    cli = _load_script("seeds-cli")
    db = tmp_path / "seedbank.json"
    assert cli.main(["add", "a weekly newsletter", "short, one topic"], path=db) == 0
    sid = seeds.list_seeds(path=db)[0]["id"]
    assert cli.main(["list"], path=db) == 0
    assert sid in capsys.readouterr().out
    assert cli.main(["letgo", sid, "not now"], path=db) == 0
    assert seeds.list_seeds(path=db)[0]["status"] == "let_go"
    assert cli.main(["water", "missing"], path=db) == 1


# --------------------------------------------------------------- seed-nudge
def test_nudge_with_nothing_due_posts_nothing(tmp_path):
    nudge = _load_script("seed-nudge")
    calls = []
    assert nudge.main([], now_ts=NOW, path=tmp_path / "s.json",
                      post=lambda *a, **k: calls.append(1)) == 0
    assert calls == []


def test_nudge_posts_to_the_digest_route_and_marks_surfaced(tmp_path):
    nudge = _load_script("seed-nudge")
    db = tmp_path / "s.json"
    sid = seeds.capture("idea", now_ts=NOW - DAY, path=db)
    sent = []

    def post(text, title=None, route="alerts"):
        sent.append((route, text))
        return True
    assert nudge.main([], now_ts=NOW, path=db, post=post) == 0
    assert sent and sent[0][0] == "digest" and sid in sent[0][1]
    s = seeds.list_seeds(path=db)[0]
    assert s["surface_count"] == 1 and s["last_surfaced_at"] == NOW


def test_nudge_does_not_mark_when_slack_is_absent_or_failing(tmp_path):
    nudge = _load_script("seed-nudge")
    db = tmp_path / "s.json"
    seeds.capture("idea", now_ts=NOW - DAY, path=db)
    assert nudge.main([], now_ts=NOW, path=db, post=lambda *a, **k: None) == 2
    assert nudge.main([], now_ts=NOW, path=db, post=lambda *a, **k: False) == 1
    assert seeds.list_seeds(path=db)[0]["surface_count"] == 0   # still due


def test_nudge_dry_run_changes_nothing(tmp_path, capsys):
    nudge = _load_script("seed-nudge")
    db = tmp_path / "s.json"
    seeds.capture("idea", now_ts=NOW - DAY, path=db)

    def never(*_a, **_k):
        raise AssertionError("posted during dry-run")
    assert nudge.main(["--dry-run"], now_ts=NOW, path=db, post=never) == 0
    assert "Seed Review" in capsys.readouterr().out
    assert seeds.list_seeds(path=db)[0]["surface_count"] == 0
