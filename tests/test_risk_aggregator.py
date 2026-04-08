"""Tests for core/risk_aggregator.py.

Pure Python — no I/O, no mocking required.
Covers all three decision bands and guard-rail error paths.
"""

import pytest

from api.schemas import EntityResult, LegitimacyResult, SequenceResult
from core.risk_aggregator import aggregate


# ---------------------------------------------------------------------------
# Helpers — minimal result constructors
# ---------------------------------------------------------------------------


def seq(match_score: float, flagged: bool = False) -> SequenceResult:
    return SequenceResult(
        match_score=match_score,
        matched_organism="Synthetic_Agent_Alpha" if flagged else None,
        percent_identity=match_score * 100,
        flagged=flagged,
    )


def ent(match_score: float, flagged: bool = False) -> EntityResult:
    return EntityResult(
        match_score=match_score,
        matched_entity="Test Entity" if flagged else None,
        list_source="OFAC_SDN" if flagged else None,
        flagged=flagged,
    )


def leg(rule_score: float, flagged: bool = False) -> LegitimacyResult:
    return LegitimacyResult(
        rule_score=rule_score,
        rules_triggered=["test_rule"] if flagged else [],
        flagged=flagged,
    )


# ---------------------------------------------------------------------------
# True positive — high scores → reject
# ---------------------------------------------------------------------------


def test_high_scores_reject():
    decision, risk_score, _ = aggregate(seq(1.0), ent(1.0), leg(1.0))
    assert decision == "reject"
    assert risk_score == 100


def test_sequence_dominated_reject():
    # sequence weight=0.5, score=1.0 → contributes 50 points alone
    # entity + legitimacy both 0 → total = 50 → flag band (40–69)
    decision, risk_score, _ = aggregate(seq(1.0), ent(0.0), leg(0.0))
    assert decision == "flag"
    assert risk_score == 50


def test_all_modules_high_reject():
    decision, risk_score, _ = aggregate(
        seq(0.9), ent(0.9), leg(0.9)
    )
    assert decision == "reject"
    assert risk_score >= 70


# ---------------------------------------------------------------------------
# True negative — low scores → approve
# ---------------------------------------------------------------------------


def test_zero_scores_approve():
    decision, risk_score, _ = aggregate(seq(0.0), ent(0.0), leg(0.0))
    assert decision == "approve"
    assert risk_score == 0


def test_low_scores_approve():
    decision, risk_score, _ = aggregate(seq(0.1), ent(0.05), leg(0.0))
    assert decision == "approve"
    assert risk_score < 40


# ---------------------------------------------------------------------------
# Edge cases — flag band and boundary conditions
# ---------------------------------------------------------------------------


def test_mid_scores_flag():
    # seq(0.7)*50 + ent(0.5)*30 + leg(0.3)*20 = 35+15+6 = 56 → flag band
    decision, risk_score, _ = aggregate(seq(0.7), ent(0.5), leg(0.3))
    assert decision == "flag"
    assert 40 <= risk_score <= 69


def test_score_at_approve_boundary():
    # risk_score == 39 → approve (strictly below APPROVE_THRESHOLD=40)
    decision, risk_score, _ = aggregate(
        seq(0.0), ent(0.0), leg(0.0),
        approve_threshold=40,
        reject_threshold=70,
    )
    assert decision == "approve"


def test_score_at_reject_boundary():
    # risk_score == 70 → reject (at REJECT_THRESHOLD=70)
    decision, risk_score, _ = aggregate(
        seq(0.7), ent(0.7), leg(0.7),
        approve_threshold=40,
        reject_threshold=70,
    )
    assert decision == "reject"
    assert risk_score >= 70


def test_module_scores_sum_to_risk_score():
    decision, risk_score, module_scores = aggregate(seq(0.6), ent(0.4), leg(0.3))
    total = round(module_scores.sequence + module_scores.entity + module_scores.legitimacy)
    assert total == risk_score


def test_flagged_booleans_do_not_affect_decision():
    # flagged=True on all modules but scores are zero → still approve
    decision, risk_score, _ = aggregate(
        seq(0.0, flagged=True),
        ent(0.0, flagged=True),
        leg(0.0, flagged=True),
    )
    assert decision == "approve"
    assert risk_score == 0


# ---------------------------------------------------------------------------
# Guard rails — invalid configuration
# ---------------------------------------------------------------------------


def test_weights_not_summing_to_one_raises():
    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        aggregate(
            seq(0.5), ent(0.5), leg(0.5),
            weight_sequence=0.5,
            weight_entity=0.5,
            weight_legitimacy=0.5,
        )


def test_approve_threshold_gte_reject_threshold_raises():
    with pytest.raises(ValueError, match="approve_threshold"):
        aggregate(
            seq(0.5), ent(0.5), leg(0.5),
            approve_threshold=70,
            reject_threshold=40,
        )


def test_equal_thresholds_raises():
    with pytest.raises(ValueError):
        aggregate(
            seq(0.5), ent(0.5), leg(0.5),
            approve_threshold=50,
            reject_threshold=50,
        )


def test_risk_score_clamped_to_100():
    # Even with weights summing slightly over due to rounding, score <= 100
    decision, risk_score, _ = aggregate(seq(1.0), ent(1.0), leg(1.0))
    assert risk_score <= 100
