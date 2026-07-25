"""Leak Radar actions — §6.9, §18.

The two guardrails this module exists to enforce:

* A usage status only changes because the *user* said so. Nothing here infers
  "unused" from transaction data (§3.12, §25.9).
* A decision drafts a message and updates a projection. It never contacts a
  merchant, and the response says so explicitly (§3.13, §25.20).
"""

from __future__ import annotations

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
from ..models.entities import User, utc_now
from ..models.enums import LeakDecision, UsageStatus
from ..repositories.base import Repositories
from . import serializers
from .schemas import DraftActionRequest, LeakDecisionRequest, UsageConfirmationRequest
from .support import (
    DISCLAIMER,
    draft_action,
    recalculate,
    record_audit,
    validation_context,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/leaks", tags=["leaks"])

#: Stated on every decision response. A "cancel" here is a draft, not an action.
SIMULATED_NOTICE = (
    "This is a proposed action only. SafeSpare has not contacted this merchant "
    "and has not cancelled anything on your behalf."
)


#: Timestamped history lives in calculation state rather than in a dedicated
#: repository method, which keeps the storage interface narrow while still
#: satisfying "user confirmation must be stored with timestamp" (§15.6).
STATE_USAGE_CONFIRMATIONS = "usage_confirmations"
STATE_DECISIONS = "action_decisions"


def _append_state(repos: Repositories, analysis_id: str, key: str, entry: Dict[str, Any]) -> None:
    history = list(repos.calculations.get_state(analysis_id, key, []) or [])
    history.append(entry)
    repos.calculations.set_state(analysis_id, key, history)


def _replace_leak(repos: Repositories, analysis_id: str, record) -> None:
    repos.calculations.set_leaks(
        analysis_id,
        [
            record if existing.id == record.id else existing
            for existing in repos.calculations.get_leaks(analysis_id)
        ],
    )


def _load(repos: Repositories, session, leak_id: str):
    parse_uuid(leak_id, "leak_id")
    record = repos.calculations.get_leak(leak_id)
    if record is None:
        raise not_found("LEAK_NOT_FOUND", "We could not find that finding.")
    analysis = authorize_analysis(repos, session, record.analysis_id)
    return record, analysis


@router.post("/{leak_id}/usage-confirmation", summary="Record the user's usage answer (§6.9)")
def usage_confirmation(
    leak_id: str,
    payload: UsageConfirmationRequest,
    request: Request,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    record, analysis = _load(repos, session, leak_id)
    before = record.usage_status

    record.usage_status = payload.usage_status
    _replace_leak(repos, analysis.id, record)
    _append_state(
        repos,
        analysis.id,
        STATE_USAGE_CONFIRMATIONS,
        {
            "leak_id": record.id,
            "merchant": record.merchant,
            "usage_status": payload.usage_status.value,
            "note": payload.note,
            "confirmed_at": utc_now(),
        },
    )
    record_audit(
        repos,
        analysis,
        session,
        entity_type="leak",
        entity_id=record.id,
        action="usage_confirmation",
        before={"usage_status": before.value},
        after={"usage_status": payload.usage_status.value},
        request=request,
    )

    # Re-score: confirming non-usage raises the leak score and may unlock the
    # cancel action; reversing it must take both away again (§20 requirement).
    recalculate(repos, request.app.state.settings, analysis)
    updated = repos.calculations.get_leak(record.id) or record
    change = None
    if updated.price_change_id:
        change = next(
            (
                c
                for c in repos.calculations.get_price_changes(analysis.id)
                if c.id == updated.price_change_id
            ),
            None,
        )
    return {
        "leak": serializers.leak(updated, change),
        "recoverable": serializers.leaks(analysis, repos).get("totals", {}),
        "notice": SIMULATED_NOTICE,
    }


@router.post("/{leak_id}/decision", summary="Record a keep/cancel/downgrade decision (§6.9)")
def leak_decision(
    leak_id: str,
    payload: LeakDecisionRequest,
    request: Request,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    record, analysis = _load(repos, session, leak_id)

    # An essential expense can never be cancelled on our recommendation (§25.5-8).
    if record.protected and payload.decision is LeakDecision.CANCEL:
        raise ApiError(
            422,
            "PROTECTED_EXPENSE",
            "%s is an essential expense. SafeSpare does not recommend cancelling it."
            % record.merchant,
        )
    if payload.decision not in record.recommended_actions:
        raise ApiError(
            422,
            "ACTION_NOT_AVAILABLE",
            "That action is not available for this finding yet. Confirm whether you "
            "use the service first.",
        )

    before = record.decision
    record.decision = payload.decision
    _replace_leak(repos, analysis.id, record)
    _append_state(
        repos,
        analysis.id,
        STATE_DECISIONS,
        {
            "leak_id": record.id,
            "merchant": record.merchant,
            "decision": payload.decision.value,
            "note": payload.note,
            "decided_at": utc_now(),
            "executed": False,
        },
    )
    record_audit(
        repos,
        analysis,
        session,
        entity_type="leak",
        entity_id=record.id,
        action="decision",
        before={"decision": before.value if before else None},
        after={"decision": payload.decision.value},
        request=request,
    )

    recalculate(repos, request.app.state.settings, analysis)
    return {
        "leak_id": record.id,
        "decision": payload.decision.value,
        "executed": False,
        "notice": SIMULATED_NOTICE,
        "safe_spare": serializers.safe_spare(analysis, repos),
        "recoverable": serializers.leaks(analysis, repos).get("totals", {}),
    }


@router.post("/{leak_id}/draft-action", summary="Draft a cancellation or downgrade message")
def leak_draft_action(
    leak_id: str,
    payload: DraftActionRequest,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    record, analysis = _load(repos, session, leak_id)

    if record.protected and payload.action_type == "cancel":
        raise ApiError(
            422,
            "PROTECTED_EXPENSE",
            "%s is an essential expense. SafeSpare will not draft a cancellation for it."
            % record.merchant,
        )

    fallback_subject = "%s request for %s" % (
        payload.action_type.capitalize(),
        record.merchant,
    )
    fallback_body = _deterministic_draft(record, payload.action_type)

    context = validation_context(repos, analysis)
    subject, body, provider, offline = draft_action(
        context,
        {
            "action_type": payload.action_type,
            "merchant": record.merchant,
            "monthly_cost": str(record.monthly_cost),
            "annual_cost": str(record.annual_cost),
            "usage_status": record.usage_status.value,
        },
        fallback_subject,
        fallback_body,
    )
    return {
        "leak_id": record.id,
        "action_type": payload.action_type,
        "subject": subject,
        "body": body,
        "provider": provider,
        "generated_offline": offline,
        "executed": False,
        "notice": SIMULATED_NOTICE,
        "disclaimer": DISCLAIMER,
    }


def _deterministic_draft(record, action_type: str) -> str:
    """The always-available draft. Works with every provider down (§3.21)."""
    usage = ""
    if record.usage_status is UsageStatus.CONFIRMED_NOT_USED:
        usage = " I have not used the service recently."
    elif record.usage_status is UsageStatus.NOT_RECOGNIZED:
        usage = " I do not recognise this charge."

    verb = {
        "cancel": "cancel my subscription",
        "downgrade": "move to a cheaper plan",
        "renegotiate": "review the price of my plan",
    }[action_type]

    return (
        "Hello,\n\n"
        "I would like to %s with %s. I am currently charged %s per month "
        "(about %s per year).%s\n\n"
        "Could you confirm what options are available and what the next step is?\n\n"
        "Thank you."
        % (verb, record.merchant, record.monthly_cost, record.annual_cost, usage)
    )
