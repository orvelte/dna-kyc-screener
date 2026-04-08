"""Tests for core/legitimacy_rules.py.

Pure Python — no mocking required.
Rules referenced by name correspond to entries in data/legitimacy_matrix.json.
"""

import pytest

from core.legitimacy_rules import screen_legitimacy


# ---------------------------------------------------------------------------
# True positive — rules triggered
# ---------------------------------------------------------------------------


def test_individual_residential_flagged():
    result = screen_legitimacy(
        end_use="hobby",
        customer_type="individual",
        quantity_bp=500,
        address_type="residential",
        institution_verified=False,
    )
    assert result.flagged is True
    assert "individual_residential" in result.rules_triggered
    assert result.rule_score > 0.0


def test_unknown_end_use_flagged():
    result = screen_legitimacy(
        end_use="unknown",
        customer_type="academic",
        quantity_bp=300,
        address_type="institutional",
        institution_verified=True,
    )
    assert result.flagged is True
    assert "unknown_end_use" in result.rules_triggered


def test_personal_end_use_flagged():
    result = screen_legitimacy(
        end_use="personal",
        customer_type="individual",
        quantity_bp=200,
        address_type="residential",
        institution_verified=False,
    )
    assert result.flagged is True
    assert "personal_end_use" in result.rules_triggered


def test_unverified_academic_flagged():
    result = screen_legitimacy(
        end_use="research",
        customer_type="academic",
        quantity_bp=500,
        address_type="institutional",
        institution_verified=False,
    )
    assert result.flagged is True
    assert "unverified_academic" in result.rules_triggered


# ---------------------------------------------------------------------------
# True negative — no rules triggered
# ---------------------------------------------------------------------------


def test_verified_academic_research_clean():
    result = screen_legitimacy(
        end_use="research",
        customer_type="academic",
        quantity_bp=500,
        address_type="institutional",
        institution_verified=True,
    )
    assert result.flagged is False
    assert result.rules_triggered == []
    assert result.rule_score == 0.0


def test_verified_pharma_commercial_clean():
    result = screen_legitimacy(
        end_use="commercial",
        customer_type="pharma",
        quantity_bp=1000,
        address_type="institutional",
        institution_verified=True,
    )
    assert result.flagged is False
    assert result.rule_score == 0.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_rule_score_capped_at_one():
    # Multiple high-score rules triggered simultaneously should not exceed 1.0.
    result = screen_legitimacy(
        end_use="personal",        # personal_end_use: 0.65
        customer_type="individual",  # individual_residential: 0.60, individual_po_box would also apply
        quantity_bp=25000,         # very_large_order: 0.25
        address_type="residential",
        institution_verified=False,
    )
    assert result.rule_score <= 1.0
    assert len(result.rules_triggered) > 1


def test_large_order_unverified_triggers():
    result = screen_legitimacy(
        end_use="research",
        customer_type="academic",
        quantity_bp=6000,  # > 5000 threshold
        address_type="institutional",
        institution_verified=False,
    )
    assert "large_order_unverified" in result.rules_triggered


def test_very_large_order_triggers_regardless_of_verification():
    result = screen_legitimacy(
        end_use="research",
        customer_type="pharma",
        quantity_bp=25000,  # > 20000 threshold
        address_type="institutional",
        institution_verified=True,
    )
    assert "very_large_order" in result.rules_triggered


def test_zero_quantity_does_not_trigger_quantity_rules():
    result = screen_legitimacy(
        end_use="research",
        customer_type="biotech",
        quantity_bp=0,
        address_type="institutional",
        institution_verified=True,
    )
    assert "large_order_unverified" not in result.rules_triggered
    assert "very_large_order" not in result.rules_triggered


def test_rules_triggered_is_list_of_strings():
    result = screen_legitimacy(
        end_use="unknown",
        customer_type="unknown",
        quantity_bp=100,
        address_type="unknown",
        institution_verified=False,
    )
    assert isinstance(result.rules_triggered, list)
    assert all(isinstance(r, str) for r in result.rules_triggered)
