import json
from skill_forge.usage_log import read_invocations


def test_reads_matching_skill_since(tmp_path):
    p = tmp_path / "skill-usage.jsonl"
    p.write_text("\n".join([
        json.dumps({"ts": "2026-05-01T00:00:00Z", "skill": "clone-route", "session_id": "a"}),
        json.dumps({"ts": "2026-05-10T00:00:00Z", "skill": "clone-route", "session_id": "b"}),
        json.dumps({"ts": "2026-05-10T00:00:00Z", "skill": "watch", "session_id": "c"}),
        "garbage line",
    ]), encoding="utf-8")
    inv = read_invocations(p, "clone-route", since="2026-05-05T00:00:00Z")
    assert [i["session_id"] for i in inv] == ["b"]


def test_missing_file_returns_empty(tmp_path):
    assert read_invocations(tmp_path / "nope.jsonl", "x", since="t") == []
