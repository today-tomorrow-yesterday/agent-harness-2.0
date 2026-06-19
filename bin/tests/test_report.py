from skill_forge.report import render_report


def _row(name, origin, trials, score, action, invocations):
    return {"name": name, "origin": origin, "trials": trials, "score": score,
            "action": action, "invocations": invocations}


def test_report_has_header_and_rows_and_is_readonly_labeled():
    rows = [
        _row("route-inbox", "authored", 120, -0.50, "retire-candidate", 130),
        _row("watch", "authored", 4, -0.20, "insufficient-evidence", 4),
        _row("compose-shorts", "skill-forge", 0, 0.0, "no-data", 0),
    ]
    md = render_report(rows, today="2026-05-30")
    assert "# Skill-Forge report — 2026-05-30" in md
    assert "READ-ONLY" in md                 # Phase 0 must label itself read-only
    assert "route-inbox" in md and "retire-candidate" in md
    assert "insufficient-evidence" in md     # the floor guard is visible
    assert "no-data" in md                   # zero-invocation skills read as no-data, not dead
    # the table must contain all three skills
    assert md.count("|") >= 12


def test_empty_report_states_no_skills():
    md = render_report([], today="2026-05-30")
    assert "no skills" in md.lower()
