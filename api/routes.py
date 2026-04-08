"""API route definitions.

Single endpoint: POST /screen

The three screening modules run concurrently in a thread pool (they are all
blocking/CPU-bound). The risk aggregator and audit logger run after both
results are available.
"""

import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from api.schemas import ScreenRequest, ScreenResponse
from audit.logger import log_decision
from core.entity_screener import screen_entity
from core.legitimacy_rules import screen_legitimacy
from core.risk_aggregator import aggregate
from core.sequence_screener import screen_sequence

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/screen",
    response_model=ScreenResponse,
    summary="Screen a DNA synthesis order",
    description=(
        "Runs sequence, entity, and legitimacy screens in parallel and returns "
        "a risk decision (approve / flag / reject) with a full audit trail."
    ),
)
async def screen(request: ScreenRequest) -> ScreenResponse:
    """Screen a DNA synthesis order and return a risk decision.

    Args:
        request: ScreenRequest containing customer metadata and sequence.

    Returns:
        ScreenResponse with decision, risk_score, module_scores, and audit_id.

    Raises:
        HTTPException 400: Sequence is empty or malformed.
        HTTPException 502: Entrez accession fetch failed.
        HTTPException 503: blastn binary not found on PATH.
    """
    customer = request.customer

    # Run sequence and entity screens concurrently in the default thread pool.
    # Legitimacy is pure Python with no I/O so it runs inline after.
    try:
        sequence_result, entity_result = await asyncio.gather(
            run_in_threadpool(screen_sequence, request.sequence, request.format),
            run_in_threadpool(
                screen_entity,
                customer.name,
                customer.institution,
                customer.country,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # blastn not installed
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch sequence from Entrez: {exc}",
        ) from exc

    legitimacy_result = screen_legitimacy(
        end_use=customer.end_use,
        customer_type=customer.customer_type,
        quantity_bp=request.quantity_bp or 0,
        address_type=customer.address_type,
        institution_verified=customer.institution_verified,
    )

    decision, risk_score, module_scores = aggregate(
        sequence_result,
        entity_result,
        legitimacy_result,
    )

    # Audit log is written synchronously; failures are logged internally
    # and do not affect the response (see audit/logger.py).
    audit_record = await run_in_threadpool(
        log_decision,
        request,
        sequence_result,
        entity_result,
        legitimacy_result,
        decision,
        risk_score,
    )

    # Collect all triggered rules across modules for the response surface.
    all_rules_triggered = legitimacy_result.rules_triggered.copy()
    if entity_result.flagged:
        source = entity_result.list_source or "watchlist"
        all_rules_triggered.append(f"entity_match:{source}")
    if sequence_result.flagged and sequence_result.matched_organism:
        all_rules_triggered.append(f"sequence_match:{sequence_result.matched_organism}")

    logger.info(
        "Screen complete: audit_id=%s decision=%s risk_score=%d",
        audit_record.audit_id,
        decision,
        risk_score,
    )

    return ScreenResponse(
        decision=decision,
        risk_score=risk_score,
        module_scores=module_scores,
        rules_triggered=all_rules_triggered,
        audit_id=audit_record.audit_id,
        timestamp=audit_record.timestamp,
    )
