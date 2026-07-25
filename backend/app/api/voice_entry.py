"""Spoken expense entry — voice as a first-class input.

For users who cannot upload a bank statement, or cannot read one. The endpoint
parses a phrase deterministically and returns what it *heard*; nothing becomes a
transaction until the user confirms it (§3.14).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict

from fastapi import APIRouter, Depends

from ..config import get_logger
from ..dependencies import authorize_analysis, get_repositories, get_session
from ..models.entities import User
from ..models.enums import Category, Direction
from ..repositories.base import Repositories
from ..services import spoken_expenses
from .schemas import ConfirmSpokenExpenseRequest, SpokenExpenseRequest

logger = get_logger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice-entry"])


@router.post("/parse-expense", summary="Parse a spoken expense (no side effects)")
def parse_expense(payload: SpokenExpenseRequest) -> Dict[str, Any]:
    parsed = spoken_expenses.parse(payload.transcript, payload.language)
    return {
        "transcript": parsed.transcript,
        "amount": str(parsed.amount) if parsed.amount is not None else None,
        "description": parsed.description,
        "category": parsed.category.value,
        "direction": parsed.direction.value,
        "confidence": parsed.confidence,
        "language": parsed.language,
        # Always true — a heard amount is never trusted without confirmation.
        "needs_confirmation": True,
        "warnings": parsed.warnings,
        "calculation_version": parsed.calculation_version,
    }


@router.post("/confirm-expense", summary="Store a confirmed spoken expense")
def confirm_expense(
    payload: ConfirmSpokenExpenseRequest,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    expense = spoken_expenses.SpokenExpense(
        transcript=payload.transcript,
        amount=Decimal(payload.amount),
        description=payload.description,
        category=payload.category or Category.UNKNOWN,
        direction=Direction(payload.direction),
        confidence=1.0,          # the user confirmed it
        language=payload.language,
    )
    txn = spoken_expenses.to_transaction(expense, on=date.today(), currency=payload.currency)

    stored_to = None
    if payload.analysis_id:
        analysis = authorize_analysis(repos, session, payload.analysis_id)
        rows = repos.transactions.list_for_analysis(analysis.id)
        rows.append(txn)
        repos.transactions.replace_all(analysis.id, rows)
        stored_to = analysis.id

    return {
        "transaction_id": txn.id,
        "amount": str(txn.amount),
        "description": txn.description,
        "category": txn.category.value,
        "direction": txn.direction.value,
        "date": txn.date.isoformat(),
        "analysis_id": stored_to,
        "message": "Recorded. Nothing has been invested or moved.",
    }
