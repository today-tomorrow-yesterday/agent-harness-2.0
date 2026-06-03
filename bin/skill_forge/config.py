"""Skill-Forge configuration: paths and lifecycle thresholds.

Threshold provenance: Library Drift (arxiv 2605.19576) — contribution score,
evidence floor Nmin=100, retirement tau=0.10, bounded active-cap. Phase 0 only
COMPUTES these; it never acts on them.
"""
from __future__ import annotations
from pathlib import Path

AGENT_OS = Path(r"Z:\agent-os")
BRAIN_DB = AGENT_OS / "claude-brain" / "claude-brain.db"
SKILLS_DIR = AGENT_OS / "skills"          # canonical source skills (Tre-authored)
FORGE_DIR = AGENT_OS / "forge"
REPORT_PATH = FORGE_DIR / "report-latest.md"
EVOLUTION_LOG = FORGE_DIR / "evolution.jsonl"
LOG_PATH = AGENT_OS / "skill-forge.log"

# Lifecycle thresholds (computed in Phase 0, acted on in Phase 2+)
N_MIN = 100          # evidence floor: trials required before retire/revise is eligible
TAU = 0.10           # retirement threshold: retire when contribution <= -TAU
ACTIVE_CAP = 25      # bounded active-cap for Forge-minted skills (not enforced in P0)

# Signal-extraction window
LOOKBACK_DAYS = 90   # how far back to scan transcripts for invocations
AFTER_WINDOW = 6     # messages after an invocation the judge inspects for outcome

VERDICTS = ("helped", "hurt", "neutral", "inapplicable")
