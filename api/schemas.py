"""Pydantic models for API request/response, internal module outputs, and audit logging."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Inbound (API request)
# ---------------------------------------------------------------------------


class CustomerIn(BaseModel):
    """Customer metadata submitted with a screening request."""

    name: str
    institution: str | None = None
    country: str  # ISO 3166-1 alpha-2
    customer_type: Literal["academic", "biotech", "pharma", "government", "individual", "commercial", "unknown"] = "unknown"
    end_use: str
    address_type: Literal["institutional", "residential", "po_box", "unknown"]
    institution_verified: bool = False

    @field_validator("country")
    @classmethod
    def country_must_be_alpha2(cls, v: str) -> str:
        """Validate that country is a two-letter ISO 3166-1 alpha-2 code."""
        if len(v) != 2 or not v.isalpha():
            raise ValueError("country must be a 2-letter ISO 3166-1 alpha-2 code")
        return v.upper()


class ScreenRequest(BaseModel):
    """Top-level screening request submitted to POST /screen."""

    customer: CustomerIn
    sequence: str
    format: Literal["raw", "fasta", "accession"] = "raw"
    quantity_bp: int | None = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# Module outputs (internal, passed to risk aggregator)
# ---------------------------------------------------------------------------


class SequenceResult(BaseModel):
    """Output from core/sequence_screener.py."""

    match_score: float = Field(ge=0.0, le=1.0)
    matched_organism: str | None
    percent_identity: float = Field(ge=0.0, le=100.0)
    flagged: bool


class EntityResult(BaseModel):
    """Output from core/entity_screener.py."""

    match_score: float = Field(ge=0.0, le=1.0)
    matched_entity: str | None
    list_source: str | None  # e.g. "OFAC_SDN", "BIS_Entity", "UN"
    flagged: bool


class LegitimacyResult(BaseModel):
    """Output from core/legitimacy_rules.py."""

    rule_score: float = Field(ge=0.0, le=1.0)
    rules_triggered: list[str]  # human-readable rule names
    flagged: bool


# ---------------------------------------------------------------------------
# Aggregated decision + API response
# ---------------------------------------------------------------------------


class ModuleScores(BaseModel):
    """Weighted contribution scores from each screening module (0–100 each)."""

    sequence: float = Field(ge=0.0, le=100.0)
    entity: float = Field(ge=0.0, le=100.0)
    legitimacy: float = Field(ge=0.0, le=100.0)


class ScreenResponse(BaseModel):
    """Response returned by POST /screen."""

    decision: Literal["approve", "flag", "reject"]
    risk_score: int = Field(ge=0, le=100)
    module_scores: ModuleScores
    rules_triggered: list[str]
    audit_id: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# Audit log record (written to file/DB for every decision)
# ---------------------------------------------------------------------------


class AuditRecord(BaseModel):
    """Immutable record written to the audit log for every screening decision."""

    audit_id: str
    timestamp: datetime
    input_hash: str  # sha256 of the raw request body, not the sequence itself
    customer_country: str
    sequence_length: int = Field(ge=0)
    sequence_result: SequenceResult
    entity_result: EntityResult
    legitimacy_result: LegitimacyResult
    final_decision: Literal["approve", "flag", "reject"]
    risk_score: int = Field(ge=0, le=100)
