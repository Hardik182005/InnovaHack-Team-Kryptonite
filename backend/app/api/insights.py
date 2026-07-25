"""AI Coach, voice summary and privacy endpoints — §6.11, §6.12, §18, §22.

The rule that shapes all three: the backend composes verified text first, and a
provider may only rephrase or speak it. No provider is ever asked to produce a
figure, so none can invent one (§3.7, §3.8).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request

from ..config import get_logger
from ..dependencies import authorize_analysis, get_repositories, get_session
from ..models.entities import AIInsight, User, VoiceAsset, utc_now
from ..models.enums import ReviewStatus, UsageStatus
from ..repositories.base import Repositories
from . import serializers
from .schemas import ChatRequest, DeleteDataRequest, VoiceRequest
from .support import (
    DISCLAIMER,
    coach_reply,
    require_analysis_ready,
    validation_context,
    verified_facts,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["insights"])


@router.post("/insights/chat", summary="AI Coach (§6.11)")
def coach(
    payload: ChatRequest,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    analysis = authorize_analysis(repos, session, payload.analysis_id)
    require_analysis_ready(analysis)

    facts = verified_facts(repos, analysis)
    fallback = _deterministic_answer(payload.question, facts, repos, analysis)
    context = validation_context(repos, analysis)

    answer, provider, offline, rejected = coach_reply(
        context, payload.question, fallback, facts, _coach_evidence(repos, analysis)
    )

    record = AIInsight(
        analysis_id=analysis.id,
        insight_type="coach",
        title="Coach reply",
        explanation=answer,
        confidence=1.0 if offline else 0.9,
        review_status=ReviewStatus.CONFIRMED,
        source="deterministic" if offline else "llm",
        model=provider,
        values_are_backend_verified=True,
        created_at=utc_now(),
    )
    existing = list(repos.insights.list_insights(analysis.id))
    existing.append(record)
    repos.insights.set_insights(analysis.id, existing[-50:])

    return {
        "answer": answer,
        "provider": provider,
        "generated_offline": offline,
        "validation_rejected": rejected,
        "values_are_backend_verified": True,
        "disclaimer": DISCLAIMER,
        "evidence": _evidence(facts),
    }


def _coach_evidence(repos: Repositories, analysis) -> List[Dict[str, Any]]:
    """The largest spends, as citable rows.

    Totals alone cannot answer "what is my biggest expense?" — that needs the
    individual transactions. The prompt builder caps and redacts these, so the
    only decision here is which rows are worth the budget: the biggest debits,
    because those are what the questions are almost always about.
    """
    rows = [
        t for t in repos.transactions.list_for_analysis(analysis.id)
        if t.counts_toward_spending
    ]
    rows.sort(key=lambda t: t.amount, reverse=True)
    return [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "amount": str(t.amount),
            "merchant": t.normalized_merchant or t.description,
        }
        for t in rows[:8]
    ]


#: "how much can I spare / save / set aside", however the user phrases it.
_ASKS_HOW_MUCH_SPARE = re.compile(
    r"(?:how much|what).{0,30}\b(?:safe(?:ly)?|spare|save|set aside|put aside)\b"
    r"|\bsafe(?:ly)? spare\b",
    re.I,
)


def _rupees(value: Any) -> str:
    """Format a stored money fact for display. Facts arrive as strings."""
    return "₹%s" % value


def _deterministic_answer(question: str, facts: Dict[str, Any], repos, analysis) -> str:
    """The answer used when providers are down, or when their output is rejected.

    Deliberately good rather than a placeholder: §3.21 requires the product to
    keep working with every LLM API unavailable.
    """
    q = (question or "").lower()

    if any(w in q for w in ("guarantee", "guaranteed", "how much will i make", "returns")):
        return (
            "I cannot promise any return. Every projection SafeSpare shows is "
            "illustrative, and actual returns may be higher, lower or negative. "
            "SafeSpare does not invest money or recommend specific investments."
        )
    if any(w in q for w in ("which stock", "what stock", "which fund", "crypto", "should i buy")):
        return (
            "SafeSpare does not recommend specific stocks, funds or "
            "cryptocurrencies. It only shows how much you could safely set aside "
            "and simulates how that might grow under an illustrative assumption."
        )
    if "cancel" in q and any(w in q for w in ("rent", "insurance", "emi", "loan", "medical", "tax")):
        return (
            "SafeSpare never recommends cancelling an essential payment such as "
            "rent, an EMI, insurance, medical costs or tax, and it cannot cancel "
            "anything on your behalf."
        )
    if "account number" in q or "full account" in q:
        return (
            "I do not have your account number. SafeSpare masks account "
            "identifiers and never stores them."
        )
    if "gym" in q or "did i use" in q or "unused" in q:
        return _usage_answer(repos, analysis)
    # "how much can I safely spare?" is the question this whole product exists to
    # answer, and it is the wording the Coach's own suggestion chips use — but it
    # contains "safely spare", not the literal "safe spare", so it used to fall
    # past every branch here and land on the generic "open Spending Intelligence"
    # reply. Match the amount question first, and answer it with the amount.
    asks_reason = "why" in q or "capped" in q or "limit" in q
    if _ASKS_HOW_MUCH_SPARE.search(q) and not asks_reason:
        amount = facts.get("safe_spare_now")
        monthly = facts.get("safe_monthly_contribution")
        if amount is not None:
            answer = "You can safely spare %s right now." % _rupees(amount)
            if monthly is not None:
                answer += (
                    " Over a month that works out to %s." % _rupees(monthly)
                )
            reason = facts.get("safe_spare_reason")
            return "%s %s" % (answer, reason) if reason else answer

    if "safe spare" in q or "capped" in q or "why" in q:
        return facts.get("safe_spare_reason") or (
            "Your Safe Spare amount is what remains after protecting upcoming "
            "essential bills, your safety buffer and a volatility reserve."
        )
    if "round" in q:
        return facts.get("roundup_explanation") or (
            "Round-ups are capped by your Safe Spare amount, so they never take "
            "money that your upcoming bills need."
        )
    if "netflix" in q or "spend" in q or "how much" in q:
        return (
            "Every figure in SafeSpare is calculated from your own statement. "
            "Open Spending Intelligence to see each category with the "
            "transactions behind it."
        )
    return (
        "I can explain any figure SafeSpare has calculated from your statement — "
        "your Safe Spare amount, why round-ups were capped, your recurring "
        "payments, or a goal projection. I cannot change a calculated value."
    )


def _usage_answer(repos: Repositories, analysis) -> str:
    """§25.9: never state that a subscription is unused without confirmation."""
    unknown: List[str] = []
    confirmed: List[str] = []
    for leak in repos.calculations.get_leaks(analysis.id):
        if leak.usage_status is UsageStatus.UNKNOWN:
            unknown.append(leak.merchant)
        elif leak.usage_status is UsageStatus.CONFIRMED_NOT_USED:
            confirmed.append(leak.merchant)

    if confirmed:
        return (
            "You told us you have not used %s recently. Bank data alone cannot "
            "show whether a service is used, so that came from your confirmation."
            % ", ".join(confirmed[:3])
        )
    if unknown:
        return (
            "Usage is unknown. A bank statement shows that %s was charged, but not "
            "whether you used it. SafeSpare will not call a subscription unused "
            "until you confirm it." % unknown[0]
        )
    return "There are no optional subscriptions flagged for review right now."


def _evidence(facts: Dict[str, Any]) -> Dict[str, Any]:
    """Only backend-verified values are echoed back as evidence."""
    keys = (
        "safe_spare_now",
        "safe_monthly_contribution",
        "potential_round_ups",
        "allowed_round_ups",
        "total_income",
        "total_spending",
    )
    return {k: facts[k] for k in keys if k in facts}


@router.post("/voice/summary", summary="Voice summary (§6.12)")
def voice_summary(
    payload: VoiceRequest,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    from .support import synthesize_voice

    analysis = authorize_analysis(repos, session, payload.analysis_id)
    require_analysis_ready(analysis)

    transcript = _compose_transcript(repos, analysis)
    audio = synthesize_voice(transcript)

    repos.insights.put_voice(
        VoiceAsset(
            analysis_id=analysis.id,
            transcript=transcript,
            provider=audio.get("provider") or "unavailable",
            content_type=audio.get("content_type"),
            available=bool(audio.get("available")),
            created_at=utc_now(),
        )
    )
    return {
        "transcript": transcript,
        "audio_base64": audio.get("audio_base64"),
        "content_type": audio.get("content_type"),
        "provider": audio.get("provider"),
        "audio_available": bool(audio.get("available")),
        "fallback_reason": audio.get("fallback_reason"),
        "text_fallback": transcript,
        "values_are_backend_verified": True,
    }


def _compose_transcript(repos: Repositories, analysis) -> str:
    """Compose the spoken summary from verified values only (§6.12).

    Built here, before any provider is contacted, so the voice can only ever
    read figures the backend calculated.
    """
    patterns = repos.calculations.get_patterns(analysis.id)
    leaks = repos.calculations.get_leaks(analysis.id)
    snapshot = repos.calculations.get_safe_spare(analysis.id)
    changes = repos.calculations.get_price_changes(analysis.id)

    needs_review = [l for l in leaks if l.review_status is ReviewStatus.NEEDS_REVIEW]
    parts = ["I found %d recurring payments." % len(patterns)]
    if needs_review:
        parts.append("%d require review." % len(needs_review))
    if changes:
        change = changes[0]
        parts.append(
            "One optional subscription, %s, increased by %s percent."
            % (change.merchant, change.percentage_increase)
        )
    if snapshot is not None:
        if snapshot.safe_monthly_contribution > 0:
            parts.append(
                "Based on your safety settings, up to %s dollars may be redirected "
                "this month." % snapshot.safe_monthly_contribution
            )
        else:
            parts.append(
                "Based on your safety settings, nothing can be safely redirected "
                "this month because essential bills are due before your next income."
            )
    return " ".join(parts)


@router.post("/privacy/delete-data", summary="Delete the caller's data (§22)")
def delete_data(
    payload: DeleteDataRequest,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    if not payload.confirm:
        from ..dependencies import bad_request

        raise bad_request(
            "CONFIRMATION_REQUIRED", "Confirm that you want your data deleted."
        )

    if payload.analysis_id:
        analysis = authorize_analysis(repos, session, payload.analysis_id)
        repos.purge_analysis(analysis.id)
        deleted = [analysis.id]
    else:
        deleted = []
        for analysis in repos.analyses.list_for_user(session.id):
            repos.purge_analysis(analysis.id)
            deleted.append(analysis.id)

    logger.info("privacy_delete", extra={"event": "privacy_delete", "count": len(deleted)})
    return {
        "deleted": True,
        "analyses_deleted": len(deleted),
        "message": "Your uploaded statements and every value derived from them have been deleted.",
    }
