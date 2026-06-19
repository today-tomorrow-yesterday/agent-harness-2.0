"""Tests for the pure diff logic of bin/security_watch.py."""
import importlib.util
import sys
from pathlib import Path


def _load():
    p = Path(__file__).resolve().parents[1] / "security_watch.py"
    s = importlib.util.spec_from_file_location("security_watch", p)
    m = importlib.util.module_from_spec(s)
    sys.modules["security_watch"] = m
    s.loader.exec_module(m)
    return m


sw = _load()


def test_diff_added_removed_changed():
    old = {"a": "1", "b": "2", "c": "3"}
    new = {"b": "2", "c": "X", "d": "4"}
    d = sw.diff_manifests(old, new)
    assert d["added"] == ["d"]
    assert d["removed"] == ["a"]
    assert d["changed"] == ["c"]


def test_diff_no_changes():
    m = {"a": "1", "b": "2"}
    d = sw.diff_manifests(m, dict(m))
    assert d == {"added": [], "removed": [], "changed": []}


def test_scan_hashes_watched_files(tmp_path):
    prof = tmp_path / ".claude"
    (prof / "skills").mkdir(parents=True)
    (prof / "skills" / "s.md").write_text("hi", encoding="utf-8")
    (prof / "settings.json").write_text("{}", encoding="utf-8")
    (prof / "ignored.txt").write_text("x", encoding="utf-8")  # not watched
    man = sw.scan([prof])
    keys = {Path(k).name for k in man}
    assert "s.md" in keys and "settings.json" in keys
    assert "ignored.txt" not in keys
