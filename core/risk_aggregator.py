"""Weighted risk aggregation across all three screening modules.

Combines scores from sequence, entity, and legitimacy screeners into a single
risk_score (0–100) and maps it to a decision: approve / flag / reject.

The module-level `flagged` booleans from each screener are NOT used to derive
the decision; they flow into the audit record only. The decision is determined
solely by the weighted numeric score and the configured band thresholds.
"""

import logging
from typing import Literal

import config
from api.schemas import (
    EntityResult,
    LegitimacyResult,
    ModuleScores,
    SequenceResult,
)

logger = logging.getLogger(__name__)


def _weighted_score(
    sequence_result: SequenceResult,
    entity_result: EntityResult,
    legitimacy_result: LegitimacyResult,
    weight_sequence: float,
    weight_entity: float,
    weight_legitimacy: float,
) -> tuple[int, ModuleScores]:
    """Compute weighted risk score and per-module contributions.

    Args:
        sequence_result: Output from core/sequence_screener.py.
        entity_result: Output from core/entity_screener.py.
        legitimacy_result: Output from core/legitimacy_rules.py.
        weight_sequence: Fractional weight for the sequence module (0–1).
        weight_entity: Fractional weight for the entity module (0–1).
        weight_legitimacy: Fractional weight for the legitimacy module (0–1).

    Returns:
        Tuple of (risk_score, ModuleScores) where risk_score is an int 0–100
        and ModuleScores holds each module's weighted contribution.
    """
    seq_raw = sequence_result.match_score * 100.0
    ent_raw = entity_result.match_score * 100.0
    leg_raw = legitimacy_result.rule_score * 100.0

    seq_contribution = seq_raw * weight_sequence
    ent_contribution = ent_raw * weight_entity
    leg_contribution = leg_raw * weight_legitimacy

    raw_score = seq_contribution + ent_contribution + leg_contribution
    risk_score = min(100, max(0, round(raw_score)))

    module_scores = ModuleScores(
        sequence=round(seq_contribution, 2),
        entity=round(ent_contribution, 2),
        legitimacy=round(leg_contribution, 2),
    )

    return risk_score, module_scores


def _band_to_decision(
    risk_score: int,
    approve_threshold: int,
    reject_threshold: int,
) -> Literal["approve", "flag", "reject"]:
    """Map a numeric risk score to a decision string.

    Args:
        risk_score: Aggregated score in range 0–100.
        approve_threshold: Scores strictly below this → approve.
        reject_threshold: Scores at or above this → reject.

    Returns:
        One of "approve", "flag", or "reject".
    """
    if risk_score < approve_threshold:
        return "approve"
    if risk_score >= reject_threshold:
        return "reject"
    return "flag"


def aggregate(
    sequence_result: SequenceResult,
    entity_result: EntityResult,
    legitimacy_result: LegitimacyResult,
    *,
    weight_sequence: float = config.WEIGHT_SEQUENCE,
    weight_entity: float = config.WEIGHT_ENTITY,
    weight_legitimacy: float = config.WEIGHT_LEGITIMACY,
    approve_threshold: int = config.APPROVE_THRESHOLD,
    reject_threshold: int = config.REJECT_THRESHOLD,
) -> tuple[Literal["approve", "flag", "reject"], int, ModuleScores]:
    """Aggregate three module results into a final risk decision.

    Weights are applied to each module's normalized score (0–100), summed,
    and rounded to produce risk_score. The decision is derived from score
    bands — the per-module `flagged` booleans are ignored here.

    Args:
        sequence_result: Output from core/sequence_screener.py.
        entity_result: Output from core/entity_screener.py.
        legitimacy_result: Output from core/legitimacy_rules.py.
        weight_sequence: Fractional weight for sequence module (default from config).
        weight_entity: Fractional weight for entity module (default from config).
        weight_legitimacy: Fractional weight for legitimacy module (default from config).
        approve_threshold: risk_score below this → approve (default from config).
        reject_threshold: risk_score at or above this → reject (default from config).

    Returns:
        Tuple of (decision, risk_score, module_scores).

    Raises:
        ValueError: If weights do not sum to approximately 1.0 (±0.01 tolerance).
    """
    total_weight = weight_sequence + weight_entity + weight_legitimacy
    if not (0.99 <= total_weight <= 1.01):
        raise ValueError(
            f"Weights must sum to 1.0, got {total_weight:.4f} "
            f"(sequence={weight_sequence}, entity={weight_entity}, "
            f"legitimacy={weight_legitimacy})"
        )

    if approve_threshold >= reject_threshold:
        raise ValueError(
            f"approve_threshold ({approve_threshold}) must be less than "
            f"reject_threshold ({reject_threshold})"
        )

    risk_score, module_scores = _weighted_score(
        sequence_result,
        entity_result,
        legitimacy_result,
        weight_sequence,
        weight_entity,
        weight_legitimacy,
    )

    decision = _band_to_decision(risk_score, approve_threshold, reject_threshold)

    logger.debug(
        "aggregate: risk_score=%d decision=%s seq=%.2f ent=%.2f leg=%.2f",
        risk_score,
        decision,
        module_scores.sequence,
        module_scores.entity,
        module_scores.legitimacy,
    )

    return decision, risk_score, module_scores
