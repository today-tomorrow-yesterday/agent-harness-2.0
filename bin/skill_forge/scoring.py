"""Contribution scoring and (report-only) action classification.

Score: c(s) = (helped - hurt) / trials, where trials = helped+hurt+neutral.
'inapplicable' verdicts are excluded from trials (the window didn't show the
skill's outcome). Action classification is ADVISORY in Phase 0 — the refiner
only reports these labels; it never acts. The evidence floor (Nmin) is the
load-bearing guard from Library Drift (arxiv 2605.19576): acting below it
provably harms, so sub-floor skills are 'insufficient-evidence', never retired.
"""
from __future__ import annotations


def contribution_score(verdicts: list[str]) -> float:
    helped = verdicts.count("helped")
    hurt = verdicts.count("hurt")
    neutral = verdicts.count("neutral")
    trials = helped + hurt + neutral
    if trials == 0:
        return 0.0
    return (helped - hurt) / trials


def classify_action(trials: int, score: float, n_min: int, tau: float) -> str:
    """Advisory label (Phase 0 reports only):
      'no-data'               -> 0 tracked invocations. NOT a retire signal. Means
                                 "nothing recorded yet" — during the tracking
                                 warm-up, OR for skills driven by scheduled farmers
                                 / typed slash commands that never hit the Skill
                                 tool, this says NOTHING about real usage. A genuine
                                 "unused" verdict needs a MATURED tracking window
                                 (spec §6 maturity gate), not just trials==0.
      'insufficient-evidence' -> 0 < trials < n_min (DO NOT act — below floor)
      'retire-candidate'      -> trials >= n_min AND score <= -tau
      'healthy'               -> trials >= n_min AND score > -tau
    """
    if trials == 0:
        return "no-data"
    if trials < n_min:
        return "insufficient-evidence"
    if score <= -tau:
        return "retire-candidate"
    return "healthy"
