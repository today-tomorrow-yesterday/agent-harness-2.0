"""Tests for the digest's self-test verdict line (runner/digest.selftest_line)."""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path


def _load():
    p = Path(__file__).resolve().parents[1] / "runner" / "digest.py"
    s = importlib.util.spec_from_file_location("digest_under_test", p)
    m = importlib.util.module_from_spec(s)
    sys.modules["digest_under_test"] = m
    s.loader.exec_module(m)
    return m


digest = _load()


def _report(tmp_path: Path, verdict: str) -> Path:
    p = tmp_path / "self-test-report.md"
    p.write_text(f"# Self-test report\n\n**VERDICT: {verdict}**\n", encoding="utf-8")
    return p


def test_missing_report_nudges(tmp_path):
    line = digest.selftest_line(tmp_path / "not-here" / "self-test-report.md")
    assert "not run yet" in line


def test_pass_verdict(tmp_path):
    line = digest.selftest_line(_report(tmp_path, "PASS"), age_h=2)
    assert "PASS" in line and "STALE" not in line and "unknown" not in line


def test_fail_verdict(tmp_path):
    line = digest.selftest_line(_report(tmp_path, "FAIL"), age_h=2)
    assert "FAIL" in line


def test_stale_report_is_flagged(tmp_path):
    line = digest.selftest_line(_report(tmp_path, "PASS"), age_h=48)
    assert "STALE" in line, "a report that stopped updating means the job died — must be flagged"


def test_age_comes_from_the_recorded_run_not_the_file(tmp_path):
    import os
    p = _report(tmp_path, "PASS")
    old = time.time() - 48 * 3600
    os.utime(p, (old, old))            # an old file with a fresh recorded run is fresh
    assert "STALE" not in digest.selftest_line(p, age_h=1)
    fresh = _report(tmp_path, "PASS")  # a just-written file with no recorded run is NOT vouched for
    assert "age unknown" in digest.selftest_line(fresh)
