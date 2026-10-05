import pytest
from skill_forge.scoring import contribution_score, classify_action


@pytest.mark.parametrize("verdicts,expected", [
    (["helped", "helped", "hurt"], pytest.approx((2 - 1) / 3)),     # trials=3
    (["helped", "helped"], pytest.approx(1.0)),
    (["hurt", "hurt"], pytest.approx(-1.0)),
    (["inapplicable", "inapplicable"], 0.0),   # no real trials -> 0
    ([], 0.0),
])
def test_contribution_score(verdicts, expected):
    assert contribution_score(verdicts) == expected


def test_inapplicable_excluded_from_trials():
    # 1 helped, 1 hurt, 5 inapplicable -> trials=2, score=0.0
    verdicts = ["helped", "hurt"] + ["inapplicable"] * 5
    assert contribution_score(verdicts) == pytest.approx(0.0)


def test_classify_action_no_data_when_zero_trials():
    # zero tracked invocations is 'no-data', NOT a retire signal — a heavily-used
    # but newly-tracked (or scheduler-driven) skill must never read as dead/unused
    assert classify_action(trials=0, score=0.0, n_min=100, tau=0.10) == "no-data"


def test_classify_action_insufficient_evidence_below_floor():
    # bad score but not enough trials -> must NOT recommend acting
    assert classify_action(trials=10, score=-0.9, n_min=100, tau=0.10) == "insufficient-evidence"


def test_classify_action_retire_when_floor_met_and_below_tau():
    assert classify_action(trials=120, score=-0.5, n_min=100, tau=0.10) == "retire-candidate"


def test_classify_action_healthy():
    assert classify_action(trials=120, score=0.4, n_min=100, tau=0.10) == "healthy"
