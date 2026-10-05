#!/usr/bin/env python3
"""
source-ledger.py — deterministic source dedup + reliability tiering for research-swarm.

WHY THIS EXISTS
  research-swarm just shipped a data-density confidence meter ("5/6 angles well-sourced").
  But that meter LIES if three parallel agents all cite the same syndicated press release
  via three different URLs — it reads as three independent confirmations when it's one.
  This collapses sources to a canonical key, dedups across agents, and tags each domain a
  reliability tier, so "how many INDEPENDENT sources" is computed, not eyeballed. Zero model
  calls — pure string work (pattern: STORM/DeepEra source ledger).

  Run between map and reduce: feed it every {url, claim, agent} the swarm collected; it
  returns the deduped ledger + an independence count the synthesizer can trust.

USAGE
  echo '{"citations":[{"url":"...","agent":"a1","claim":"..."}, ...]}' | python source-ledger.py
  python source-ledger.py --demo
"""
import argparse, json, sys
from urllib.parse import urlsplit, parse_qsl, urlunsplit, urlencode

# Domain reliability tiers — coarse, deterministic, editable. Tier drives how much weight
# a citation carries; it is NOT a truth oracle, just a prior. (Anti-pattern guard: a tier
# is a prior on the SOURCE, never a verification of the CLAIM — see research-swarm verify stage.)
TIER_RULES = {
    "primary": [   # primary / authoritative
        ".gov", ".edu", ".gov.uk", "who.int", "europa.eu",
        "arxiv.org", "nature.com", "science.org", "nih.gov", "sec.gov",
    ],
    "reputable": [  # established secondary
        "reuters.com", "apnews.com", "bloomberg.com", "wsj.com", "ft.com",
        "nytimes.com", "economist.com", "github.com", "stackoverflow.com",
        "anthropic.com", "openai.com",
    ],
    "tertiary": [   # aggregators / wikis / vendor blogs (useful, not load-bearing alone)
        "wikipedia.org", "medium.com", "substack.com", "reddit.com",
        "quora.com", "linkedin.com", "youtube.com",
    ],
}
# Tracking params to strip so the same page via different campaigns collapses to one key.
# Prefixes match a family (utm_source, utm_medium, ...); exact keys match one name only, so a
# real parameter such as `reference=` or `spmode=` is never stripped by accident.
TRACKING_PREFIXES = ("utm_", "mc_")
TRACKING_KEYS = {"fbclid", "gclid", "msclkid", "ref", "ref_src", "spm"}


def _is_tracking(key):
    k = key.lower()
    return k in TRACKING_KEYS or k.startswith(TRACKING_PREFIXES)


def _host_matches(host, needle):
    """`.gov` is a suffix rule; `nature.com` matches itself or a subdomain, never `fakenature.com`."""
    if needle.startswith("."):
        return host.endswith(needle) or host == needle.lstrip(".")
    return host == needle or host.endswith("." + needle)


def tier_of(host):
    host = host.lower()
    for tier, needles in TIER_RULES.items():
        if any(_host_matches(host, n) for n in needles):
            return tier
    return "unknown"


def canonical(url):
    """Collapse a URL to a dedup key: lowercase host, drop www/scheme/fragment/tracking, sort query."""
    try:
        s = urlsplit(url.strip())
        host = (s.hostname or "").lower()
    except ValueError:
        fallback = url.strip().lower()
        return fallback, fallback
    if host.startswith("www."):
        host = host[4:]
    path = s.path.rstrip("/") or "/"
    q = [(k, v) for k, v in parse_qsl(s.query) if not _is_tracking(k)]
    q.sort()
    return urlunsplit(("", host, path, urlencode(q), "")).lstrip("/") or host, host


def build_ledger(citations):
    by_key = {}
    for c in citations:
        url = c.get("url", "")
        if not url:
            continue
        key, host = canonical(url)
        entry = by_key.setdefault(key, {
            "canonical": key, "host": host, "tier": tier_of(host),
            "urls": set(), "agents": set(), "claims": [],
        })
        entry["urls"].add(url)
        if c.get("agent"):
            entry["agents"].add(c["agent"])
        if c.get("claim"):
            entry["claims"].append(c["claim"])

    ledger = []
    for e in by_key.values():
        ledger.append({
            "canonical": e["canonical"], "host": e["host"], "tier": e["tier"],
            "url_variants": sorted(e["urls"]),
            "cited_by_agents": sorted(e["agents"]),
            "n_agents": len(e["agents"]),
            "claims": e["claims"],
        })
    ledger.sort(key=lambda x: (-x["n_agents"], x["host"]))

    # Independence: distinct canonical sources, and how many are NOT tertiary/unknown.
    distinct = len(ledger)
    load_bearing = sum(1 for e in ledger if e["tier"] in ("primary", "reputable"))
    # Flag echo-chamber risk: a "confirmation" that is really one source cited by many agents.
    echoes = [e for e in ledger if e["n_agents"] >= 2]

    return {
        "distinct_sources": distinct,
        "load_bearing_sources": load_bearing,
        "tier_breakdown": {t: sum(1 for e in ledger if e["tier"] == t)
                           for t in ("primary", "reputable", "tertiary", "unknown")},
        "multi_agent_sources": [
            {"host": e["host"], "tier": e["tier"], "n_agents": e["n_agents"]}
            for e in echoes
        ],
        "note": ("Independence = distinct_sources, NOT total citations. "
                 "multi_agent_sources are single sources several agents leaned on — "
                 "they are ONE confirmation, not several; weight accordingly in the confidence meter."),
        "ledger": ledger,
    }


DEMO = {"citations": [
    {"url": "https://www.reuters.com/tech/ai-report?utm_source=tw", "agent": "a1", "claim": "X grew 40%"},
    {"url": "https://reuters.com/tech/ai-report/", "agent": "a2", "claim": "X grew 40%"},  # same source, diff agent
    {"url": "https://reuters.com/tech/ai-report?gclid=zz", "agent": "a3", "claim": "X grew 40%"},
    {"url": "https://arxiv.org/abs/2401.12345", "agent": "a2", "claim": "method Y is SOTA"},
    {"url": "https://somerandomblog.io/post", "agent": "a4", "claim": "speculative take"},
]}


def main():
    ap = argparse.ArgumentParser(description="Deterministic source dedup + reliability tiering.")
    ap.add_argument("--input", help="JSON file; omit to read stdin.")
    ap.add_argument("--demo", action="store_true", help="Run on a built-in fixture.")
    args = ap.parse_args()
    if args.demo:
        payload = DEMO
    elif args.input:
        with open(args.input, encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = json.load(sys.stdin)
    print(json.dumps(build_ledger(payload.get("citations", [])), indent=2))


if __name__ == "__main__":
    main()
