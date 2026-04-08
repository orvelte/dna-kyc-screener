"""Tests for core/sequence_screener.py.

BLAST calls are mocked — these tests do not require blastn to be installed.
All sequences used are synthetic. See tests/fixtures/synthetic_sequences.py.
"""

import pytest
from unittest.mock import patch

from api.schemas import SequenceResult
from core.sequence_screener import screen_sequence
from tests.fixtures.synthetic_sequences import (
    SYNTHETIC_AGENT_ALPHA_MATCH,
    SYNTHETIC_BENIGN,
    SYNTHETIC_BENIGN_FASTA,
    SYNTHETIC_SHORT,
)


# ---------------------------------------------------------------------------
# Shared mock results
# ---------------------------------------------------------------------------

_FLAGGED_RESULT = SequenceResult(
    match_score=0.95,
    matched_organism="Synthetic_Agent_Alpha",
    percent_identity=95.0,
    flagged=True,
)

_CLEAN_RESULT = SequenceResult(
    match_score=0.0,
    matched_organism=None,
    percent_identity=0.0,
    flagged=False,
)


# ---------------------------------------------------------------------------
# True positive — BLAST returns a high-identity hit
# ---------------------------------------------------------------------------


def test_high_identity_hit_flagged():
    with patch("core.sequence_screener._run_blast", return_value=_FLAGGED_RESULT):
        result = screen_sequence(SYNTHETIC_AGENT_ALPHA_MATCH, "raw")
    assert result.flagged is True
    assert result.matched_organism == "Synthetic_Agent_Alpha"
    assert result.percent_identity >= 85.0
    assert 0.0 <= result.match_score <= 1.0


def test_flagged_result_match_score_normalised():
    with patch("core.sequence_screener._run_blast", return_value=_FLAGGED_RESULT):
        result = screen_sequence(SYNTHETIC_AGENT_ALPHA_MATCH, "raw")
    assert result.match_score == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# True negative — BLAST returns no qualifying hits
# ---------------------------------------------------------------------------


def test_no_blast_hits_not_flagged():
    with patch("core.sequence_screener._run_blast", return_value=_CLEAN_RESULT):
        result = screen_sequence(SYNTHETIC_BENIGN, "raw")
    assert result.flagged is False
    assert result.matched_organism is None
    assert result.match_score == 0.0


# ---------------------------------------------------------------------------
# Edge cases — input validation
# ---------------------------------------------------------------------------


def test_empty_sequence_raises():
    with pytest.raises(ValueError, match="empty"):
        screen_sequence("", "raw")


def test_whitespace_only_raises():
    with pytest.raises(ValueError, match="empty"):
        screen_sequence("   \n\t", "raw")


def test_invalid_characters_raises():
    with pytest.raises(ValueError, match="invalid characters"):
        screen_sequence("ATGCXYZ123", "raw")


def test_short_sequence_skips_blast_and_returns_unflagged():
    # Sequences below MIN_ALIGN_BP are returned early without calling BLAST.
    with patch("core.sequence_screener._run_blast") as mock_blast:
        result = screen_sequence(SYNTHETIC_SHORT, "raw")
        mock_blast.assert_not_called()
    assert result.flagged is False
    assert result.match_score == 0.0


# ---------------------------------------------------------------------------
# Edge cases — format handling
# ---------------------------------------------------------------------------


def test_fasta_format_accepted():
    with patch("core.sequence_screener._run_blast", return_value=_CLEAN_RESULT):
        result = screen_sequence(SYNTHETIC_BENIGN_FASTA, "fasta")
    assert result is not None
    assert result.flagged is False


def test_empty_fasta_raises():
    with pytest.raises(ValueError, match="No valid FASTA"):
        screen_sequence(">only_header\n", "fasta")


def test_unknown_format_raises():
    with pytest.raises(ValueError, match="Unknown sequence format"):
        screen_sequence(SYNTHETIC_BENIGN, "xml")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Edge cases — blastn not installed
# ---------------------------------------------------------------------------


def test_missing_blastn_raises_runtime_error():
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="blastn not found"):
            screen_sequence(SYNTHETIC_BENIGN, "raw")


# ---------------------------------------------------------------------------
# Edge cases — custom threshold override
# ---------------------------------------------------------------------------


def test_custom_threshold_prevents_flag():
    # Same 95% identity result but threshold raised to 99 — should not flag.
    below_threshold = SequenceResult(
        match_score=0.95,
        matched_organism="Synthetic_Agent_Alpha",
        percent_identity=95.0,
        flagged=False,  # _run_blast respects the threshold passed to it
    )
    with patch("core.sequence_screener._run_blast", return_value=below_threshold):
        result = screen_sequence(
            SYNTHETIC_AGENT_ALPHA_MATCH,
            "raw",
            identity_threshold=99.0,
        )
    assert result.flagged is False
