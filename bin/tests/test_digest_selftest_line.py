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


def test_missing_report_nudges():
    line = digest.selftest_line(Path("Z:/definitely/not/here/self-test-report.md"))
    assert "not run yet" in line


def test_pass_verdict(tmp_path):
    line = digest.selftest_line(_report(tmp_path, "PASS"))
    assert "PASS" in line and "STALE" not in line


def test_fail_verdict(tmp_path):
    line = digest.selftest_line(_report(tmp_path, "FAIL"))
    assert "FAIL" in line


def test_stale_report_is_flagged(tmp_path):
    import os
    p = _report(tmp_path, "PASS")
    old = time.time() - 48 * 3600
    os.utime(p, (old, old))
    line = digest.selftest_line(p)
    assert "STALE" in line, "a report that stopped updating means the job died — must be flagged"
