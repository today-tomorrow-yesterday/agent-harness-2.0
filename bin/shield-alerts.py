#!/usr/bin/env python3
"""
shield-alerts.py — view recent shield-watch.ps1 alerts.

Usage:
    python Z:\\agent-os\\bin\\shield-alerts.py              # last 20 HIGH/CRITICAL entries
    python Z:\\agent-os\\bin\\shield-alerts.py --all        # full log
    python Z:\\agent-os\\bin\\shield-alerts.py --tail N     # last N entries (any severity)
    python Z:\\agent-os\\bin\\shield-alerts.py --since 24h  # entries in the last 24 hours

The log is written by shield-watch.ps1 at Z:\\agent-os\\agentshield-watch.log.
Anything tagged CRITICAL or HIGH means a real-time scan found a new finding
worth reviewing. INFO/DEBUG lines are operational noise.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

LOG = Path(r"Z:\agent-os\agentshield-watch.log")

# Matches:  2026-05-23T14:30:00Z [HIGH] ALERT title // detail
LINE_RE = re.compile(r"^(?P<ts>\S+)\s+\[(?P<level>[A-Z]+)\]\s+(?P<msg>.*)$")


def parse_since(text: str) -> dt.timedelta:
    """Parse '24h', '30m', '7d' into a timedelta."""
    m = re.match(r"^(\d+)([hdm])$", text.strip().lower())
    if not m:
        raise argparse.ArgumentTypeError(f"--since must be like '24h', '30m', '7d', got {text!r}")
    n, unit = int(m.group(1)), m.group(2)
    if unit == "h": return dt.timedelta(hours=n)
    if unit == "m": return dt.timedelta(minutes=n)
    if unit == "d": return dt.timedelta(days=n)
    raise argparse.ArgumentTypeError(f"unknown unit {unit!r}")


def parse_line(line: str) -> tuple[dt.datetime, str, str] | None:
    m = LINE_RE.match(line.strip())
    if not m:
        return None
    try:
        ts = dt.datetime.strptime(m.group("ts"), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None
    return ts, m.group("level"), m.group("msg")


def main():
    ap = argparse.ArgumentParser(description="View recent shield-watch alerts")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="show entire log")
    g.add_argument("--tail", type=int, default=None, help="show last N lines, any severity")
    g.add_argument("--since", type=parse_since, default=None, help="show entries newer than e.g. 24h, 30m, 7d")
    ap.add_argument("--severity", default="HIGH", help="minimum severity (HIGH, CRITICAL, WARN, INFO). Ignored with --tail.")
    args = ap.parse_args()

    if not LOG.exists():
        print(f"No log yet at {LOG} — shield-watch hasn't run, or hasn't found anything.")
        return 0

    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()

    # No filtering for --all / --tail (--tail shows verbatim last N)
    if args.all:
        for line in lines:
            print(line)
        return 0

    if args.tail is not None:
        for line in lines[-args.tail:]:
            print(line)
        return 0

    # Default mode: filter for severity, optionally by time
    severity_order = ["DEBUG", "INFO", "WARN", "HIGH", "CRITICAL", "ERROR"]
    min_idx = severity_order.index(args.severity.upper()) if args.severity.upper() in severity_order else severity_order.index("HIGH")

    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - args.since if args.since else None

    matched = []
    for line in lines:
        parsed = parse_line(line)
        if not parsed:
            continue
        ts, level, msg = parsed
        if level not in severity_order:
            continue
        if severity_order.index(level) < min_idx:
            continue
        if cutoff and ts < cutoff:
            continue
        matched.append((ts, level, msg, line))

    if not matched:
        if cutoff:
            print(f"No {args.severity}+ entries since {args.since}.")
        else:
            print(f"No {args.severity}+ entries in the log.")
        return 0

    # Show last 20 by default
    if args.since is None:
        matched = matched[-20:]

    for ts, level, msg, raw in matched:
        print(raw)

    return 0


if __name__ == "__main__":
    sys.exit(main())
