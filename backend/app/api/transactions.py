"""Transaction corrections — §6.3, §18.

Every correction writes an audit record and re-derives downstream metrics, which
is what makes the extraction-review screen meaningful rather than cosmetic.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from ..config import get_logger
from ..dependencies import (
    ApiError,
    authorize_analysis,
    get_repositories,
    get_session,
    not_found,
    parse_uuid,
)
from ..models.enums import Direction
from ..models.entities import User
from ..models.transaction import money
from ..repositories.base import Repositories
from . import serializers
from .schemas import BulkConfirmRequest, TransactionPatch
from .support import confirm_extraction, record_audit, recalculate

logger = get_logger(__name__)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.patch("/{transaction_id}", summary="Correct one transaction (§6.3)")
def patch_transaction(
    transaction_id: str,
    payload: TransactionPatch,
    request: Request,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    parse_uuid(transaction_id, "transaction_id")
    analysis_id = repos.transactions.analysis_id_for(transaction_id)
    if analysis_id is None:
        raise not_found("TRANSACTION_NOT_FOUND", "We could not find that transaction.")
    analysis = authorize_analysis(repos, session, analysis_id)

    txn = repos.transactions.get(transaction_id)
    if txn is None:
        raise not_found("TRANSACTION_NOT_FOUND", "We could not find that transaction.")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise ApiError(400, "NO_CHANGES", "No changes were supplied.")

    applied: Dict[str, Dict[str, str]] = {}
    for field, value in changes.items():
        before = getattr(txn, field, None)
        if field == "amount":
            new_value = money(Decimal(str(value)))
        elif field == "direction":
            new_value = Direction(value)
        else:
            new_value = value
        if before == new_value:
            continue
        setattr(txn, field, new_value)
        applied[field] = {"before": str(before), "after": str(new_value)}

    if not applied:
        return serializers.transaction(txn)

    # A human correction is the highest-confidence signal available, and it must
    # survive the re-normalization and re-categorization that follow.
    txn.user_overridden = True
    if "category" in applied:
        txn.category_confidence = 1.0
        txn.category_method = "user_override"
    if "normalized_merchant" in applied:
        txn.merchant_confidence = 1.0
        txn.merchant_method = "user_override"
    repos.transactions.save(analysis.id, txn)

    for field, delta in applied.items():
        record_audit(
            repos,
            analysis,
            session,
            entity_type="transaction",
            entity_id=txn.id,
            action="correct:" + field,
            before={field: delta["before"]},
            after={field: delta["after"]},
            request=request,
        )

    settings = request.app.state.settings
    recalculate(repos, settings, analysis)
    return serializers.transaction(repos.transactions.get(transaction_id) or txn)


@router.post("/bulk-confirm", summary="Confirm the extraction (§6.3)")
def bulk_confirm(
    payload: BulkConfirmRequest,
    request: Request,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    analysis = authorize_analysis(repos, session, payload.analysis_id)
    settings = request.app.state.settings

    if payload.transaction_ids:
        for txn_id in payload.transaction_ids:
            txn = repos.transactions.get(txn_id)
            if txn is not None and repos.transactions.analysis_id_for(txn_id) == analysis.id:
                for warning in ("possible_duplicate", "balance_does_not_reconcile"):
                    if warning in txn.validation_warnings:
                        txn.validation_warnings.remove(warning)
                repos.transactions.save(analysis.id, txn)

    record_audit(
        repos,
        analysis,
        session,
        entity_type="analysis",
        entity_id=analysis.id,
        action="confirm_extraction",
        request=request,
    )
    updated = confirm_extraction(repos, settings, analysis)
    return serializers.analysis_status(updated)
