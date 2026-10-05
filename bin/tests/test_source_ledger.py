"""skills/research-swarm/source-ledger.py: independence is counted, not eyeballed.

Three agents citing one article through three URLs must collapse to ONE source, or the
synthesis's confidence meter reports three confirmations that are really one.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "skills" / "research-swarm" / "source-ledger.py"
spec = importlib.util.spec_from_file_location("source_ledger", str(LEDGER))
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)


def test_tracking_params_www_slash_and_fragment_collapse_to_one_key():
    keys = {sl.canonical(u)[0] for u in (
        "https://www.example.org/a/b?utm_source=x#frag",
        "http://example.org/a/b/",
        "https://example.org/a/b?gclid=1&fbclid=2",
    )}
    assert keys == {"example.org/a/b"}


def test_real_query_params_are_kept_and_sorted():
    assert sl.canonical("https://example.org/p?b=2&a=1&utm_medium=m")[0] == "example.org/p?a=1&b=2"


def test_param_that_merely_starts_like_a_tracker_is_kept():
    assert "reference=7" in sl.canonical("https://example.org/p?reference=7")[0]


def test_tiers_match_whole_domains_not_lookalikes():
    assert sl.tier_of("nature.com") == "primary"
    assert sl.tier_of("www.nature.com") == "primary"
    assert sl.tier_of("fakenature.com") == "unknown"
    assert sl.tier_of("data.agency.gov") == "primary"
    assert sl.tier_of("en.wikipedia.org") == "tertiary"


def test_echo_across_agents_counts_once_and_is_flagged():
    out = sl.build_ledger(sl.DEMO["citations"])
    assert out["distinct_sources"] == 3
    assert out["load_bearing_sources"] == 2
    echo = out["multi_agent_sources"]
    assert echo == [{"host": "reuters.com", "tier": "reputable", "n_agents": 3}]


def test_empty_and_urlless_citations():
    assert sl.build_ledger([])["distinct_sources"] == 0
    assert sl.build_ledger([{"agent": "a1", "claim": "no url"}])["distinct_sources"] == 0


def test_cli_reads_stdin_json():
    payload = json.dumps({"citations": [{"url": "https://arxiv.org/abs/1", "agent": "a"}]})
    r = subprocess.run([sys.executable, str(LEDGER)], input=payload, capture_output=True,
                       text=True, encoding="utf-8", check=True)
    assert json.loads(r.stdout)["tier_breakdown"]["primary"] == 1
