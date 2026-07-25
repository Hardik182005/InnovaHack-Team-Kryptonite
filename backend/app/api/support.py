"""Cross-cutting helpers used by more than one router.

Three concerns live here:

* **Audit trail** — §6.3 requires an audit record for every user correction, and
  §20 lists ``AuditEvent`` as a first-class entity. Writing it from one helper
  means no route can forget.
* **Recalculation** — a correction must recompute downstream metrics (§6.3).
  Routes call ``recalculate`` rather than reaching into the pipeline.
* **AI access** — every model call is wrapped so a provider outage degrades the
  *wording* and nothing else (§3.21). Each helper returns a
  ``(text, provider, offline)`` shape with a deterministic fallback already
  applied, so no route contains a code path that fails when a provider is down.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import Request

from ..config import get_logger
from ..dependencies import ApiError, call_ai, conflict
from ..models.entities import AnalysisSession, AuditRecord, User, utc_now
from ..models.enums import PROTECTED_FROM_CANCELLATION
from ..repositories.base import Repositories
from ..services.pipeline import (
    STATE_RECOVERABLE,
    STATE_SUMMARY,
    AnalysisPipeline,
    PipelineError,
)

logger = get_logger(__name__)

DISCLAIMER = (
    "SafeSpare is not a licensed financial adviser and never executes an action "
    "on your behalf. Every figure comes from your own statement."
)

ILLUSTRATIVE = (
    "Illustrative simulation only. Actual returns may be higher, lower or negative."
)


# ---------------------------------------------------------------------------
# Audit + recalculation
# ---------------------------------------------------------------------------


def record_audit(
    repos: Repositories,
    analysis: AnalysisSession,
    user: User,
    entity_type: str,
    entity_id: str,
    action: str,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> AuditRecord:
    record = AuditRecord(
        analysis_id=analysis.id,
        user_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
        request_id=getattr(request.state, "request_id", None) if request else None,
        created_at=utc_now(),
    )
    return repos.audit.append(record)


def recalculate(
    repos: Repositories, settings: Any, analysis: AnalysisSession
) -> AnalysisSession:
    """Re-run the derived stages after a user change (§6.3)."""
    try:
        return AnalysisPipeline(repos, settings).recalculate(analysis)
    except PipelineError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message)


def confirm_extraction(
    repos: Repositories, settings: Any, analysis: AnalysisSession
) -> AnalysisSession:
    try:
        return AnalysisPipeline(repos, settings).confirm(analysis)
    except PipelineError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message)


def require_analysis_ready(analysis: AnalysisSession) -> None:
    from ..models.entities import AnalysisStatus

    if analysis.status is AnalysisStatus.FAILED:
        raise conflict(
            "ANALYSIS_FAILED",
            analysis.error_message or "That analysis could not be completed.",
        )
    if analysis.status is not AnalysisStatus.COMPLETED:
        raise conflict(
            "ANALYSIS_NOT_READY",
            "That analysis is still being prepared. Confirm the extracted "
            "transactions to finish it.",
        )


# ---------------------------------------------------------------------------
# Verified context for the AI layer (§6.11, §16)
# ---------------------------------------------------------------------------


def verified_facts(repos: Repositories, analysis: AnalysisSession) -> Dict[str, Any]:
    """The backend-calculated figures a model is permitted to restate."""
    facts = dict(repos.calculations.get_state(analysis.id, STATE_SUMMARY, {}) or {})
    totals = repos.calculations.get_state(analysis.id, STATE_RECOVERABLE, {}) or {}
    facts.update({("recoverable_" + k): v for k, v in totals.items()})
    facts["currency"] = analysis.currency

    # The Safe Spare breakdown. Without it the coach knows the *answer* to "how
    # much can I spare" but nothing about how it got there, so "why was it
    # capped?" — the question the page most invites — could only be answered with
    # "that figure is not available". The snapshot has carried `reason` and
    # `limiting_factor` all along; they were simply never handed over.
    snapshot = repos.calculations.get_safe_spare(analysis.id)
    if snapshot is not None:
        facts.update(
            {
                "safe_spare_reason": snapshot.reason,
                "safe_spare_limiting_factor": snapshot.limiting_factor,
                "safety_buffer": snapshot.safety_buffer,
                "volatility_reserve": snapshot.volatility_reserve,
                "upcoming_essential_outflows": snapshot.upcoming_essential_outflows,
                "projected_balance_before_next_income": (
                    snapshot.projected_balance_before_next_income
                ),
                "latest_verified_balance": snapshot.latest_verified_balance,
                "expected_income": snapshot.expected_income,
            }
        )
    return facts


def _decimal_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce the string-typed money facts back into Decimals for the validator."""
    out: Dict[str, Any] = {}
    for key, value in facts.items():
        if isinstance(value, str):
            try:
                out[key] = Decimal(value)
                continue
            except Exception:
                pass
        out[key] = value
    return out


def validation_context(repos: Repositories, analysis: AnalysisSession) -> Optional[Any]:
    """Build ``ai.validators.ValidationContext`` from stored calculated records.

    Returns ``None`` when the AI layer is not importable — callers then use their
    deterministic template, which is the required behaviour anyway (§3.21).
    """
    try:
        from ..ai.validators import ValidationContext
    except Exception:  # pragma: no cover - AI layer absent
        return None

    leaks = repos.calculations.get_leaks(analysis.id)
    patterns = repos.calculations.get_patterns(analysis.id)
    txns = repos.transactions.list_for_analysis(analysis.id)

    merchants = {p.merchant for p in patterns} | {leak.merchant for leak in leaks}
    protected = {
        leak.merchant
        for leak in leaks
        if leak.protected or leak.category in PROTECTED_FROM_CANCELLATION
    } | {p.merchant for p in patterns if p.is_essential}
    confirmed_unused = {
        leak.merchant
        for leak in leaks
        if leak.usage_status.value
        in ("user_confirms_not_used", "user_does_not_recognize_payment")
    }

    context = ValidationContext.from_facts(
        _decimal_facts(verified_facts(repos, analysis)),
        merchants=merchants,
        transaction_ids={t.id for t in txns},
        confirmed_unused=confirmed_unused,
        protected=protected,
    )
    # Per-record figures the model may also legitimately quote.
    for leak in leaks:
        context.add_amount(leak.monthly_cost)
        context.add_amount(leak.annual_cost)
    for pattern in patterns:
        context.add_amount(pattern.median_amount)
        context.add_amount(pattern.monthly_equivalent)
    for change in repos.calculations.get_price_changes(analysis.id):
        context.add_amount(change.previous_amount)
        context.add_amount(change.current_amount)
        context.add_amount(change.absolute_increase)
        context.add_percentage(change.percentage_increase)
    snapshot = repos.calculations.get_safe_spare(analysis.id)
    if snapshot is not None:
        for value in (
            snapshot.safe_spare_now,
            snapshot.safe_monthly_contribution,
            snapshot.safety_buffer,
            snapshot.volatility_reserve,
            snapshot.upcoming_essential_outflows,
            snapshot.latest_verified_balance,
            snapshot.expected_income,
        ):
            context.add_amount(value)
    return context


# ---------------------------------------------------------------------------
# Model calls — every one has a deterministic fallback already applied
# ---------------------------------------------------------------------------


def _first_str(payload: Optional[Dict[str, Any]], *keys: str) -> Optional[str]:
    if not payload:
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _provider_of(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    if not payload:
        return None
    value = payload.get("provider") or payload.get("model")
    return value if isinstance(value, str) else None


def _is_offline(payload: Optional[Dict[str, Any]]) -> bool:
    """A router result counts as offline unless it names a live provider."""
    if not payload:
        return True
    for key in ("generated_offline", "fallback", "offline", "used_template"):
        if bool(payload.get(key)):
            return True
    provider = _provider_of(payload)
    return provider in (None, "", "deterministic_template", "unavailable", "template")


def coach_reply(
    context: Any,
    question: str,
    fallback_answer: str,
    facts: Optional[Dict[str, Any]] = None,
    evidence_rows: Optional[Sequence[Dict[str, Any]]] = None,
) -> Tuple[str, Optional[str], bool, bool]:
    """Return ``(answer, provider, generated_offline, validation_rejected)``.

    `facts` is the whole point of the call. The router signature is
    ``coach_reply(context, question, facts=None, evidence_rows=None)`` and this
    wrapper used to pass only the first two, so the model received an empty
    VERIFIED_BACKEND_FACTS block and truthfully answered "that figure is not
    available" to every question — including ones whose answer the endpoint was
    simultaneously returning to the browser in `evidence`. The coach cannot know
    anything about the dashboard unless the figures are actually handed to it.
    """
    payload = call_ai("coach_reply", context, question, facts, evidence_rows)
    answer = _first_str(payload, "answer", "text", "reply", "explanation", "message")
    rejected = bool(payload.get("validation_rejected")) if payload else False
    if not answer or rejected:
        return fallback_answer, _provider_of(payload), True, rejected

    offline = _is_offline(payload)
    refusal = bool(payload.get("refusal_reason")) if payload else False
    if offline and not refusal:
        # The router always produces *something*, and with no provider available
        # that something is its last-resort composer: every verified fact, joined
        # by semicolons — "allowed round ups: 26.64; average monthly surplus:
        # ₹6921.80; ..." — which is accurate and unreadable. `fallback_answer` is
        # the same information written for a person to read, so it wins whenever
        # no model actually answered.
        #
        # A refusal is the exception and passes through untouched: those are the
        # §24 guardrail replies, and a deterministic fallback must never be able
        # to talk over one.
        return fallback_answer, _provider_of(payload), True, rejected
    return answer, _provider_of(payload), offline, rejected


def draft_action(
    context: Any, payload_in: Dict[str, Any], fallback_subject: str, fallback_body: str
) -> Tuple[str, str, Optional[str], bool]:
    """Return ``(subject, body, provider, generated_offline)``."""
    payload = call_ai("draft_action", context, payload_in)
    subject = _first_str(payload, "subject", "title")
    body = _first_str(payload, "body", "message", "text", "draft")
    if not subject or not body:
        return fallback_subject, fallback_body, _provider_of(payload), True
    return subject, body, _provider_of(payload), _is_offline(payload)


def explain_insight(
    context: Any, payload_in: Dict[str, Any], fallback_text: str
) -> Tuple[str, Optional[str], bool]:
    payload = call_ai("explain_insight", context, payload_in)
    text = _first_str(payload, "explanation", "text", "answer", "summary")
    if not text:
        return fallback_text, _provider_of(payload), True
    return text, _provider_of(payload), _is_offline(payload)


def synthesize_voice(transcript: str) -> Dict[str, Any]:
    """Text-to-speech for a transcript the backend already composed (§6.12).

    The provider is handed finished text. It cannot produce a figure because it
    is never asked to produce content at all.
    """
    result = call_ai("synthesize_voice", transcript)
    if result is None:
        return {
            "audio_base64": None,
            "content_type": None,
            "provider": "unavailable",
            "available": False,
            "fallback_reason": "voice_provider_unavailable",
        }
    value = result.get("value", result)
    audio = _attr(value, "audio_base64")
    return {
        "audio_base64": audio,
        "content_type": _attr(value, "mime_type") or _attr(value, "content_type"),
        "provider": _attr(value, "provider") or "unavailable",
        "available": bool(audio),
        "fallback_reason": None if audio else (_attr(value, "fallback_text") and "voice_provider_unavailable")
        or "voice_provider_unavailable",
    }


def _attr(obj: Any, name: str) -> Optional[Any]:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
