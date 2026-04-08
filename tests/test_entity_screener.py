"""Tests for core/entity_screener.py.

Each test group covers: true positive, true negative, edge cases.
Watchlist entries referenced here are synthetic — see data/watchlist_sample.csv.
"""

import pytest

from core.entity_screener import screen_entity


# ---------------------------------------------------------------------------
# True positive — watchlist hit (non-embargoed country)
# ---------------------------------------------------------------------------


def test_exact_watchlist_name_flagged():
    # "Alpha Biopharma Ltd" is in watchlist_sample.csv (BIS_Entity, CN).
    # CN is not in the embargo list, so fuzzy matching runs.
    result = screen_entity("Alpha Biopharma Ltd", None, "GB")
    assert result.flagged is True
    assert result.matched_entity is not None
    assert result.list_source == "BIS_Entity"
    assert result.match_score > 0.8


def test_institution_match_flagged():
    # The customer name is clean but the institution matches the watchlist.
    result = screen_entity("John Doe", "Alpha Biopharma Ltd", "GB")
    assert result.flagged is True
    assert result.list_source == "BIS_Entity"


def test_near_match_name_flagged():
    # Slight variation on a watchlist name — fuzzy matching should still catch it.
    result = screen_entity("Alpha BioPharma Limited", None, "GB")
    assert result.flagged is True


# ---------------------------------------------------------------------------
# True negative — name clearly not on watchlist
# ---------------------------------------------------------------------------


def test_clean_name_not_flagged():
    result = screen_entity("Jane Smith", "University of Edinburgh", "GB")
    assert result.flagged is False
    assert result.matched_entity is None
    assert result.list_source is None
    assert result.match_score == 0.0


def test_clean_institution_not_flagged():
    result = screen_entity("Jane Smith", "NHS Scotland", "GB")
    assert result.flagged is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_embargoed_country_hard_blocks():
    # Country embargo check fires before fuzzy matching regardless of name.
    result = screen_entity("Jane Smith", "University of Edinburgh", "IR")
    assert result.flagged is True
    assert result.list_source == "EMBARGO"
    assert result.match_score == 1.0


def test_embargoed_country_kp():
    result = screen_entity("Completely Innocent Name", None, "KP")
    assert result.flagged is True
    assert result.list_source == "EMBARGO"


def test_country_code_case_insensitive():
    # "ir" should be treated the same as "IR".
    result_lower = screen_entity("Jane Smith", None, "ir")
    result_upper = screen_entity("Jane Smith", None, "IR")
    assert result_lower.flagged == result_upper.flagged


def test_none_institution_does_not_error():
    result = screen_entity("Jane Smith", None, "GB")
    assert result.flagged is False


def test_custom_threshold_raises_bar():
    # At threshold=100, only exact matches flag. Near-match should not flag.
    result = screen_entity("Alpha BioPharma Limited", None, "GB", threshold=100.0)
    assert result.flagged is False


def test_match_score_normalised():
    # match_score must always be in [0.0, 1.0].
    result = screen_entity("Alpha Biopharma Ltd", None, "GB")
    assert 0.0 <= result.match_score <= 1.0
