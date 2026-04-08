"""Structured audit logging for every screening decision.

Writes one JSON line per decision to the configured AUDIT_LOG_PATH.
Every decision is logged — approve, flag, and reject alike.
The log is append-only; nothing in this module reads or modifies existing records.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config
from api.schemas import AuditRecord, EntityResult, LegitimacyResult, ScreenRequest, SequenceResult

logger = logging.getLogger(__name__)

_audit_log_path = Path(config.AUDIT_LOG_PATH)


def _ensure_log_dir() -> None:
    """Create the audit log directory if it does not exist."""
    _audit_log_path.parent.mkdir(parents=True, exist_ok=True)


def _hash_request(request: ScreenRequest) -> str:
    """Compute a SHA-256 hash of the raw request for audit linkage.

    Hashes the JSON-serialised request body. The sequence itself is included
    in the hash but is not stored in the audit record.

    Args:
        request: The original ScreenRequest submitted to the API.

    Returns:
        Lowercase hex SHA-256 digest string.
    """
    raw = request.model_dump_json(exclude_none=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_audit_record(
    request: ScreenRequest,
    sequence_result: SequenceResult,
    entity_result: EntityResult,
    legitimacy_result: LegitimacyResult,
    decision: str,
    risk_score: int,
) -> AuditRecord:
    """Construct an AuditRecord from a completed screening run.

    Args:
        request: The original ScreenRequest (used for input hash and metadata).
        sequence_result: Output from core/sequence_screener.py.
        entity_result: Output from core/entity_screener.py.
        legitimacy_result: Output from core/legitimacy_rules.py.
        decision: Final decision string — "approve", "flag", or "reject".
        risk_score: Aggregated risk score (0–100).

    Returns:
        A fully populated AuditRecord ready for serialisation.
    """
    sequence_length = len(request.sequence) if request.format == "raw" else 0

    return AuditRecord(
        audit_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        input_hash=_hash_request(request),
        customer_country=request.customer.country,
        sequence_length=sequence_length,
        sequence_result=sequence_result,
        entity_result=entity_result,
        legitimacy_result=legitimacy_result,
        final_decision=decision,
        risk_score=risk_score,
    )


def write_audit_record(record: AuditRecord) -> None:
    """Append a single audit record to the JSONL log file.

    Each call writes exactly one line. The log directory is created on first
    write if it does not exist. Failures are logged as errors but do not
    propagate — the API response is not gated on audit write success, though
    operators should monitor for write errors.

    Args:
        record: The AuditRecord to persist.
    """
    try:
        _ensure_log_dir()
        line = record.model_dump_json(exclude_none=False) + "\n"
        with _audit_log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        logger.debug("Audit record written: audit_id=%s decision=%s", record.audit_id, record.final_decision)
    except OSError as exc:
        logger.error(
            "Failed to write audit record audit_id=%s: %s",
            record.audit_id,
            exc,
        )


def log_decision(
    request: ScreenRequest,
    sequence_result: SequenceResult,
    entity_result: EntityResult,
    legitimacy_result: LegitimacyResult,
    decision: str,
    risk_score: int,
) -> AuditRecord:
    """Build and persist an audit record for a completed screening decision.

    Convenience wrapper combining build_audit_record and write_audit_record.
    Returns the record so the caller can include audit_id in the API response.

    Args:
        request: The original ScreenRequest.
        sequence_result: Output from core/sequence_screener.py.
        entity_result: Output from core/entity_screener.py.
        legitimacy_result: Output from core/legitimacy_rules.py.
        decision: Final decision string — "approve", "flag", or "reject".
        risk_score: Aggregated risk score (0–100).

    Returns:
        The AuditRecord that was written to the log.
    """
    record = build_audit_record(
        request,
        sequence_result,
        entity_result,
        legitimacy_result,
        decision,
        risk_score,
    )
    write_audit_record(record)
    return record
