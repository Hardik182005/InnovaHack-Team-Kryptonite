"""Entity -> JSON conversion for every §18 response.

Two rules hold everywhere in this module:

1. **Money is emitted as an exact decimal string.** ``Decimal("42.10")`` becomes
   ``"42.10"``. Passing the ``Decimal`` through FastAPI's encoder would produce
   ``42.1`` as a binary float, which is not the number the engine calculated.
   ``frontend/src/api/types.ts`` types money as ``string | number`` for exactly
   this reason.

2. **Nothing is recomputed here.** Every figure is read from a stored
   calculated record. A presentation layer that re-derives a total is a second
   source of truth, and §3.5 forbids that.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..models.entities import (
    AIInsight,
    AnalysisSession,
    AnalysisStatus,
    FinancialGoal,
    LeakFindingRecord,
    PriceChangeRecord,
    RecurrencePatternRecord,
    RoundUpCalculation,
    SafeSpareSnapshot,
    STATUS_LABELS,
    STATUS_ORDER,
    Simulation,
)
from ..models.enums import Category, Essentiality, ReviewStatus
from ..models.transaction import Transaction, money
from ..repositories.base import Repositories
from ..services import categorization, pipeline, projections, validation

ZERO = Decimal("0.00")

#: Engine band -> the four-value union declared in `frontend/src/api/types.ts`.
_BAND_UI = {
    "low_concern": "low_concern",
    "review": "review",
    "consider_downgrade_or_renegotiation": "consider_downgrade",
    "strong_cancellation_review_after_confirmation": "cancellation_review",
}

CATEGORY_LABELS = {
    category: category.value.replace("_", " ").title() for category in Category
}


def m(value: Optional[Decimal]) -> Optional[str]:
    """Exact decimal string, or ``None``. The only money formatter in the API."""
    if value is None:
        return None
    return str(money(value))


def _decimal_state(raw: Any, default: Decimal = ZERO) -> Decimal:
    try:
        return money(Decimal(str(raw)))
    except Exception:
        return default


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None else None


# ---------------------------------------------------------------------------
# Analysis status (§19)
# ---------------------------------------------------------------------------


def stage_list(analysis: AnalysisSession) -> List[Dict[str, Any]]:
    """The nine processing stages from §6.2, each with its current state."""
    reached = {entry["status"] for entry in analysis.history}
    reached.add(analysis.status.value)

    if analysis.status is AnalysisStatus.FAILED:
        failed_at = None
        for entry in reversed(analysis.history):
            if entry["status"] != AnalysisStatus.FAILED.value:
                failed_at = entry["status"]
                break
        stages = []
        hit_failure = False
        for status in STATUS_ORDER:
            if status.value == failed_at:
                state = "failed"
                hit_failure = True
            elif hit_failure or status.value not in reached:
                state = "pending"
            else:
                state = "done"
            stages.append(_stage(status, state, analysis))
        return stages

    try:
        current = STATUS_ORDER.index(analysis.status)
    except ValueError:  # pragma: no cover - all non-FAILED states are ordered
        current = 0
    stages = []
    for index, status in enumerate(STATUS_ORDER):
        if index < current:
            state = "done"
        elif index == current:
            state = "done" if analysis.status is AnalysisStatus.COMPLETED else "active"
        else:
            state = "pending"
        stages.append(_stage(status, state, analysis))
    return stages


def _stage(status: AnalysisStatus, state: str, analysis: AnalysisSession) -> Dict[str, Any]:
    return {
        "key": status.value,
        "label": STATUS_LABELS[status],
        "state": state,
        "detail": analysis.stage_message if status is analysis.status else None,
    }


def analysis_status(analysis: AnalysisSession) -> Dict[str, Any]:
    return {
        "analysis_id": analysis.id,
        "state": analysis.status.value,
        "progress_percent": analysis.progress_percent,
        "stages": stage_list(analysis),
        "message": analysis.error_message or analysis.stage_message,
        "error_code": analysis.error_code,
        "updated_at": analysis.updated_at,
        "currency": analysis.currency,
        "auto_confirm": analysis.auto_confirm,
    }


def document_meta(analysis: AnalysisSession, repos: Repositories) -> Dict[str, Any]:
    state = repos.calculations.get_state(analysis.id, pipeline.STATE_EXTRACTION, {}) or {}
    validation_state = (
        repos.calculations.get_state(analysis.id, pipeline.STATE_VALIDATION, {}) or {}
    )
    document = repos.documents.get(analysis.document_id) if analysis.document_id else None
    warnings = list(state.get("warnings") or []) + list(
        validation_state.get("statement_warnings") or []
    )
    return {
        "currency": state.get("currency", analysis.currency),
        "currency_confidence": 1.0 if state.get("currency") else 0.5,
        "date_range_start": state.get("date_range_start"),
        "date_range_end": state.get("date_range_end"),
        "transaction_count": state.get("rows_extracted", 0),
        "pages": state.get("pages"),
        "parser": state.get("parser", ""),
        "password_protected": bool(document.password_protected) if document else False,
        "delete_after_processing": analysis.delete_after_processing,
        "duplicates_removed": state.get("duplicates_removed", 0),
        "balance_reconciles": validation_state.get("balance_reconciles"),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Transactions (§6.3)
# ---------------------------------------------------------------------------


def review_status(txn: Transaction) -> ReviewStatus:
    """§14 banding applied to a single row's overall confidence."""
    if txn.user_overridden:
        return ReviewStatus.CONFIRMED
    score = validation.confidence_for(txn)
    if txn.validation_warnings:
        return ReviewStatus.NEEDS_REVIEW
    if score >= 0.9 and txn.category_confidence >= 0.8:
        return ReviewStatus.CONFIRMED
    if score >= 0.7:
        return ReviewStatus.LIKELY
    return ReviewStatus.NEEDS_REVIEW


def transaction(txn: Transaction) -> Dict[str, Any]:
    return {
        "id": txn.id,
        "date": txn.date.isoformat(),
        "description": txn.description,
        "raw_merchant": txn.raw_merchant,
        "normalized_merchant": txn.normalized_merchant,
        "merchant_method": txn.merchant_method,
        "merchant_confidence": txn.merchant_confidence,
        "debit": m(txn.amount) if txn.is_debit else None,
        "credit": m(txn.amount) if txn.is_credit else None,
        "amount": m(txn.amount),
        "direction": txn.direction.value,
        "balance": m(txn.balance),
        "currency": txn.currency,
        "category": txn.category.value,
        "category_confidence": txn.category_confidence,
        "category_method": txn.category_method,
        "essentiality": txn.essentiality.value,
        "source_page": txn.source_page,
        "source_row": txn.source_row,
        "parser": txn.parser,
        "extraction_confidence": txn.extraction_confidence,
        "validation_warnings": list(txn.validation_warnings),
        "external_model_used": txn.external_model_used,
        "excluded": txn.excluded,
        "is_internal_transfer": txn.is_internal_transfer,
        "is_reimbursement": txn.is_reimbursement,
        "user_overridden": txn.user_overridden,
        "status": review_status(txn).value,
        "reference": txn.reference,
        "duplicate_of": None,
    }


def transaction_page(
    analysis: AnalysisSession,
    rows: List[Transaction],
    page: int,
    page_size: int,
    total: int,
) -> Dict[str, Any]:
    return {
        "analysis_id": analysis.id,
        "items": [transaction(t) for t in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "warning_count": len([t for t in rows if t.validation_warnings]),
        "needs_review_count": len(
            [t for t in rows if review_status(t) is ReviewStatus.NEEDS_REVIEW]
        ),
        "excluded_count": len([t for t in rows if t.excluded]),
    }


# ---------------------------------------------------------------------------
# Categories (§6.5)
# ---------------------------------------------------------------------------


def categories(analysis: AnalysisSession, repos: Repositories) -> Dict[str, Any]:
    txns = repos.transactions.list_for_analysis(analysis.id)
    by_id = {t.id: t for t in txns}
    breakdown = categorization.category_breakdown(txns)

    items = []
    for category, entry in sorted(
        breakdown.items(), key=lambda kv: kv[1]["total"], reverse=True
    ):
        evidence_ids = entry["evidence_transaction_ids"][:5]
        items.append(
            {
                "category": category.value,
                "label": CATEGORY_LABELS[category],
                "total": m(entry["total"]),
                "percent_of_spending": entry["percentage"],
                "transaction_count": entry["count"],
                "previous_period_total": None,
                "change_amount": None,
                "change_percent": None,
                "essentiality": entry["essentiality"].value,
                "confidence": entry["confidence"],
                "review_status": (
                    ReviewStatus.CONFIRMED.value
                    if entry["confidence"] >= 0.8
                    else ReviewStatus.NEEDS_REVIEW.value
                ),
                "evidence": [
                    {
                        "transaction_id": tid,
                        "date": by_id[tid].date.isoformat(),
                        "description": by_id[tid].description,
                        "amount": m(by_id[tid].amount),
                    }
                    for tid in evidence_ids
                    if tid in by_id
                ],
            }
        )

    insights = []
    for record in repos.insights.list_insights(analysis.id):
        if record.insight_type in ("leak", "price_increase"):
            insights.append(
                {
                    "id": record.id,
                    "category": Category.SUBSCRIPTION.value,
                    "headline": record.title,
                    "detail": record.explanation,
                    "evidence_transaction_ids": list(record.evidence_transaction_ids),
                    "releasable_amount": None,
                    "confidence": record.confidence,
                }
            )

    return {
        "analysis_id": analysis.id,
        "currency": analysis.currency,
        "items": items,
        "insights": insights,
        "calculation_version": categorization.CALCULATION_VERSION,
    }


# ---------------------------------------------------------------------------
# Recurring and price changes (§11, §12)
# ---------------------------------------------------------------------------


def price_change(record: Optional[PriceChangeRecord]) -> Optional[Dict[str, Any]]:
    if record is None:
        return None
    return {
        "previous_amount": m(record.previous_amount),
        "current_amount": m(record.current_amount),
        "absolute_increase": m(record.absolute_increase),
        "percent_increase": float(record.percentage_increase),
        "annualized_increase": m(record.annualized_increase),
        "first_date_of_new_price": _iso(record.first_date_of_new_price),
        "evidence_transaction_ids": list(
            record.prov.source_transaction_ids if record.prov else []
        ),
        "confidence": record.prov.confidence if record.prov else 0.0,
    }


def recurrence_pattern(
    record: RecurrencePatternRecord, change: Optional[PriceChangeRecord]
) -> Dict[str, Any]:
    return {
        "id": record.id,
        "merchant": record.merchant,
        "category": record.category.value,
        "frequency": record.frequency.value,
        "occurrence_count": record.occurrences,
        "median_amount": m(record.median_amount),
        "latest_amount": m(record.latest_amount),
        "monthly_cost": m(record.monthly_equivalent),
        "annual_cost": m(record.monthly_equivalent * Decimal("12")),
        "amount_varies": record.amount_varies,
        "first_seen": _iso(record.first_date),
        "last_seen": _iso(record.latest_date),
        "next_expected_date": _iso(record.next_expected_date),
        "confidence": round((record.prov.confidence if record.prov else 0.0) * 100, 1),
        "review_status": record.status.value,
        "essentiality": (
            Essentiality.ESSENTIAL.value
            if record.is_essential
            else Essentiality.DISCRETIONARY.value
        ),
        "interval_regularity": record.components.get("interval_regularity", 0.0),
        "merchant_similarity": record.components.get("merchant_similarity", 0.0),
        "amount_stability": record.components.get("amount_stability", 0.0),
        "occurrence_strength": record.components.get("occurrence_strength", 0.0),
        "price_change": price_change(change),
        "evidence_transaction_ids": list(
            record.prov.source_transaction_ids if record.prov else []
        ),
    }


def recurring(analysis: AnalysisSession, repos: Repositories) -> Dict[str, Any]:
    patterns = repos.calculations.get_patterns(analysis.id)
    changes = {c.merchant: c for c in repos.calculations.get_price_changes(analysis.id)}
    total = sum((p.monthly_equivalent for p in patterns), ZERO)
    return {
        "analysis_id": analysis.id,
        "currency": analysis.currency,
        "items": [recurrence_pattern(p, changes.get(p.merchant)) for p in patterns],
        "total_monthly_recurring": m(total),
        "price_changes": [price_change(c) for c in changes.values()],
        "calculation_version": "recurrence.v1",
    }


# ---------------------------------------------------------------------------
# Leak Radar (§6.9, §13)
# ---------------------------------------------------------------------------


def leak(record: LeakFindingRecord, change: Optional[PriceChangeRecord]) -> Dict[str, Any]:
    return {
        "id": record.id,
        "merchant": record.merchant,
        "category": record.category.value,
        "frequency": record.frequency.value,
        "monthly_cost": m(record.monthly_cost),
        "annual_cost": m(record.annual_cost),
        "leak_score": record.leak_score,
        "band": _BAND_UI.get(record.band, "review"),
        "band_detail": record.band,
        "usage_status": record.usage_status.value,
        "review_status": record.review_status.value,
        "decision": record.decision.value if record.decision else None,
        "recommended_actions": [a.value for a in record.recommended_actions],
        "components": dict(record.components),
        "duplicate_group": record.duplicate_group,
        "price_change": price_change(change),
        "evidence_transaction_ids": list(
            record.prov.source_transaction_ids if record.prov else []
        ),
        "explanation": record.explanation,
        "protected": record.protected,
        "protection_reason": (
            "This is an essential expense. SafeSpare never recommends cancelling it."
            if record.protected
            else None
        ),
        "calculation_version": record.prov.calculation_version if record.prov else "",
    }


def leaks(analysis: AnalysisSession, repos: Repositories) -> Dict[str, Any]:
    records = repos.calculations.get_leaks(analysis.id)
    changes = {c.merchant: c for c in repos.calculations.get_price_changes(analysis.id)}
    totals = repos.calculations.get_state(analysis.id, pipeline.STATE_RECOVERABLE, {}) or {}
    return {
        "analysis_id": analysis.id,
        "currency": analysis.currency,
        "items": [leak(r, changes.get(r.merchant)) for r in records],
        "potential_recoverable_monthly": m(
            _decimal_state(totals.get("potential_recoverable", "0"))
        ),
        "high_confidence_recoverable_monthly": m(
            _decimal_state(totals.get("high_confidence_recoverable", "0"))
        ),
        "user_confirmed_recoverable_monthly": m(
            _decimal_state(totals.get("user_confirmed_recoverable", "0"))
        ),
        "calculation_version": "leak_score.v1",
    }


# ---------------------------------------------------------------------------
# Safe Spare and Cashflow Confidence (§6.6, §6.7)
# ---------------------------------------------------------------------------


def safe_spare_settings_dict(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    settings = pipeline._safe_spare_settings(state)
    return {
        "user_minimum_buffer": m(settings.user_minimum_buffer),
        "buffer_percentage": float(settings.buffer_percentage),
        "volatility_multiplier": float(settings.volatility_multiplier),
        "user_monthly_cap": m(settings.user_monthly_cap),
    }


def safe_spare(analysis: AnalysisSession, repos: Repositories) -> Dict[str, Any]:
    snapshot = repos.calculations.get_safe_spare(analysis.id)
    if snapshot is None:
        return {}
    inputs = (
        repos.calculations.get_state(analysis.id, pipeline.STATE_SAFE_SPARE_INPUTS, {})
        or {}
    )
    settings_state = repos.calculations.get_state(
        analysis.id, pipeline.STATE_SAFE_SPARE_SETTINGS, {}
    )
    return {
        "analysis_id": analysis.id,
        "currency": analysis.currency,
        "latest_verified_balance": m(snapshot.latest_verified_balance),
        "balance_is_estimated": snapshot.balance_is_estimated,
        "expected_income": m(snapshot.expected_income),
        "upcoming_essential_outflows": m(snapshot.upcoming_essential_outflows),
        "projected_balance_before_next_income": m(
            snapshot.projected_balance_before_next_income
        ),
        "safety_buffer": m(snapshot.safety_buffer),
        "volatility_reserve": m(snapshot.volatility_reserve),
        "safe_spare_now": m(snapshot.safe_spare_now),
        "safe_monthly_contribution": m(snapshot.safe_monthly_contribution),
        "confirmed_recovery_included": m(snapshot.confirmed_recovery_included),
        "calculated_monthly_surplus": inputs.get("calculated_monthly_surplus"),
        "average_monthly_essential_spending": inputs.get(
            "average_monthly_essential_spending"
        ),
        "confidence": snapshot.prov.confidence if snapshot.prov else 0.0,
        "limiting_factor": snapshot.limiting_factor,
        "reason": snapshot.reason,
        "missing_inputs": list(snapshot.missing_inputs),
        "next_income_date": _iso(snapshot.next_income_date),
        "settings": safe_spare_settings_dict(settings_state),
        "source_transaction_ids": list(
            snapshot.prov.source_transaction_ids if snapshot.prov else []
        ),
        "calculation_version": snapshot.prov.calculation_version if snapshot.prov else "",
    }


_CONFIDENCE_COMPONENTS = [
    ("income_regularity", "Income regularity", 30),
    ("essential_predictability", "Essential-expense predictability", 25),
    ("buffer_coverage", "Safety-buffer coverage", 30),
    ("stability", "Spending and balance stability", 15),
]

_CONFIDENCE_EVIDENCE = {
    "income_regularity": "Measured from the spacing between the income credits in your statement.",
    "essential_predictability": "Measured from how steady your detected essential recurring charges are.",
    "buffer_coverage": "Your latest balance compared with one month of essential spending.",
    "stability": "Dispersion of your monthly outflows across the statement period.",
}


def cashflow_confidence(analysis: AnalysisSession, repos: Repositories) -> Dict[str, Any]:
    snapshot = repos.calculations.get_safe_spare(analysis.id)
    if snapshot is None:
        return {}
    components = snapshot.cashflow_components or {}
    score = snapshot.cashflow_confidence
    band = "strong" if score >= 75 else "moderate" if score >= 45 else "developing"

    suggestions: List[str] = []
    if components.get("buffer_coverage", 0.0) < 0.75:
        suggestions.append(
            "Building your balance towards one month of essential spending would raise this score."
        )
    if components.get("income_regularity", 0.0) < 0.6:
        suggestions.append(
            "Your income arrives at uneven intervals; a longer statement would sharpen this estimate."
        )
    if components.get("stability", 0.0) < 0.6:
        suggestions.append("Your monthly outflows vary; SafeSpare holds back a larger reserve.")
    if snapshot.balance_is_estimated:
        suggestions.append(
            "Your statement had no running balance, so the balance used here is an estimate."
        )

    return {
        "analysis_id": analysis.id,
        "score": score,
        "band": band,
        "components": [
            {
                "key": key,
                "label": label,
                "weight_percent": weight,
                "score": round(components.get(key, 0.0), 3),
                "weighted_points": round(components.get(key, 0.0) * weight, 1),
                "evidence": _CONFIDENCE_EVIDENCE[key],
            }
            for key, label, weight in _CONFIDENCE_COMPONENTS
        ],
        "confidence": snapshot.prov.confidence if snapshot.prov else 0.0,
        "improvement_suggestions": suggestions,
        "disclaimer": "This is not a credit score and says nothing about creditworthiness.",
        "calculation_version": "cashflow_confidence.v1",
    }


# ---------------------------------------------------------------------------
# Round-ups (§6.8)
# ---------------------------------------------------------------------------


def roundup_rules_dict(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    rules = pipeline._roundup_rules(state)
    return {
        "increment": m(rules.increment),
        "monthly_cap": m(rules.monthly_cap),
        "per_transaction_cap": m(rules.per_transaction_cap),
        "excluded_categories": sorted(c.value for c in rules.excluded_categories),
        "excluded_merchants": sorted(rules.excluded_merchants),
        "large_transaction_threshold": m(rules.large_transaction_threshold),
        "paused": rules.paused,
    }


def roundups(analysis: AnalysisSession, repos: Repositories) -> Dict[str, Any]:
    record = repos.calculations.get_roundups(analysis.id)
    if record is None:
        return {}
    snapshot = repos.calculations.get_safe_spare(analysis.id)
    lines = repos.calculations.get_state(analysis.id, "roundup_lines", []) or []
    by_id = {t.id: t for t in repos.transactions.list_for_analysis(analysis.id)}
    rules_state = repos.calculations.get_state(analysis.id, pipeline.STATE_ROUNDUP_RULES, {})

    return {
        "analysis_id": analysis.id,
        "currency": analysis.currency,
        "rules": roundup_rules_dict(rules_state),
        "lines": [
            {
                "transaction_id": line["transaction_id"],
                "date": by_id[line["transaction_id"]].date.isoformat()
                if line["transaction_id"] in by_id
                else None,
                "merchant": line["merchant"],
                "category": by_id[line["transaction_id"]].category.value
                if line["transaction_id"] in by_id
                else Category.UNKNOWN.value,
                "amount": line["amount"],
                "round_up": line["round_up"],
                "eligible": line["eligible"],
                "reason": line["reason"],
            }
            for line in lines
        ],
        "historical_round_up_total": m(record.historical_round_up_total),
        "allowed_round_up_total": m(record.allowed_round_up_total),
        "safe_monthly_contribution": m(
            snapshot.safe_monthly_contribution if snapshot else ZERO
        ),
        "limiting_factor": record.limiting_factor,
        "explanation": record.explanation,
        "eligible_count": record.eligible_count,
        "excluded_count": record.excluded_count,
        "per_merchant": {k: m(v) for k, v in record.per_merchant.items()},
        "exclusion_reasons": dict(record.exclusion_reasons),
        "calculation_version": record.prov.calculation_version if record.prov else "",
    }


# ---------------------------------------------------------------------------
# Goals and simulations (§6.10)
# ---------------------------------------------------------------------------


def goal(record: FinancialGoal) -> Dict[str, Any]:
    return {
        "id": record.id,
        "analysis_id": record.analysis_id,
        "name": record.name,
        "kind": record.goal_type,
        "target_amount": m(record.target_amount),
        "target_date": _iso(record.target_date),
        "months": record.months,
        "starting_principal": m(record.starting_principal),
        "include_round_ups": record.include_roundups,
        "include_confirmed_recovered": record.include_confirmed_recovery,
        "annual_return_rate": float(record.annual_return_rate),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def simulation_response(
    record: Simulation,
    goal_record: FinancialGoal,
    currency: str,
    monthly_contribution: Decimal,
    roundup_contribution: Decimal,
    confirmed_recovered: Decimal,
    timeline: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "id": record.id,
        "goal_id": record.goal_id,
        "analysis_id": record.analysis_id,
        "currency": currency,
        "months": goal_record.months,
        "monthly_contribution": m(monthly_contribution),
        "safe_monthly_contribution": m(record.safe_monthly_contribution),
        "round_up_contribution": m(roundup_contribution),
        "confirmed_recovered_amount": m(confirmed_recovered),
        "user_contributions": m(record.user_contributions),
        "illustrative_growth": m(record.illustrative_growth),
        "projected_value": m(record.projected_value),
        "goal_gap": m(record.goal_gap),
        "estimated_completion_months": record.estimated_completion_months,
        "estimated_completion_date": _iso(record.estimated_completion_date),
        "required_monthly_contribution": m(record.required_monthly_contribution),
        "contribution_shortfall": m(record.contribution_shortfall),
        "achievable": record.achievable,
        "scenarios": record.scenarios,
        "timeline": timeline,
        "disclaimer": record.disclaimer,
        "calculation_version": projections.CALCULATION_VERSION,
    }


# ---------------------------------------------------------------------------
# Insights (§6.11)
# ---------------------------------------------------------------------------


def insight(record: AIInsight) -> Dict[str, Any]:
    return {
        "id": record.id,
        "insight_type": record.insight_type,
        "title": record.title,
        "explanation": record.explanation,
        "suggested_action": record.suggested_action,
        "evidence_transaction_ids": list(record.evidence_transaction_ids),
        "confidence": record.confidence,
        "review_status": record.review_status.value,
        "source": record.source,
        "model": record.model,
        "values_are_backend_verified": record.values_are_backend_verified,
        "created_at": record.created_at,
    }


# ---------------------------------------------------------------------------
# Dashboard summary (§6.4)
# ---------------------------------------------------------------------------


def summary(analysis: AnalysisSession, repos: Repositories) -> Dict[str, Any]:
    txns = repos.transactions.list_for_analysis(analysis.id)
    patterns = repos.calculations.get_patterns(analysis.id)
    snapshot = repos.calculations.get_safe_spare(analysis.id)
    roundup_record = repos.calculations.get_roundups(analysis.id)
    totals = repos.calculations.get_state(analysis.id, pipeline.STATE_RECOVERABLE, {}) or {}
    inputs = (
        repos.calculations.get_state(analysis.id, pipeline.STATE_SAFE_SPARE_INPUTS, {}) or {}
    )
    extraction_state = (
        repos.calculations.get_state(analysis.id, pipeline.STATE_EXTRACTION, {}) or {}
    )

    spending_rows = [t for t in txns if t.counts_toward_spending]
    income_rows = [t for t in txns if t.counts_toward_income]
    total_spending = sum((t.amount for t in spending_rows), ZERO)
    total_income = sum((t.amount for t in income_rows), ZERO)
    essential = sum((t.amount for t in spending_rows if t.is_essential), ZERO)
    discretionary = money(total_spending - essential)
    recurring_total = sum((p.monthly_equivalent for p in patterns), ZERO)
    recurring_ids = {tid for p in patterns for tid in (p.prov.source_transaction_ids if p.prov else [])}

    months = sorted({"%04d-%02d" % (t.date.year, t.date.month) for t in txns})
    monthly_income: Dict[str, Decimal] = {}
    monthly_spend: Dict[str, Decimal] = {}
    for txn in txns:
        key = "%04d-%02d" % (txn.date.year, txn.date.month)
        if txn.counts_toward_spending:
            monthly_spend[key] = money(monthly_spend.get(key, ZERO) + txn.amount)
        elif txn.counts_toward_income:
            monthly_income[key] = money(monthly_income.get(key, ZERO) + txn.amount)

    breakdown = categorization.category_breakdown(txns)
    goals = repos.goals.list_for_analysis(analysis.id)
    latest_goal = goals[-1] if goals else None
    latest_sim = repos.goals.latest_simulation(latest_goal.id) if latest_goal else None

    percent_complete = None
    contributed = None
    if latest_goal is not None and latest_sim is not None and latest_goal.target_amount > 0:
        contributed = latest_sim.user_contributions
        percent_complete = round(
            float(min(Decimal("1"), contributed / latest_goal.target_amount)) * 100, 1
        )

    return {
        "analysis_id": analysis.id,
        "currency": analysis.currency,
        "period_start": extraction_state.get("date_range_start"),
        "period_end": extraction_state.get("date_range_end"),
        "months_covered": len(months),
        "transaction_count": len(txns),
        "total_income": m(total_income),
        "total_spending": m(total_spending),
        "essential_spending": m(essential),
        "discretionary_spending": m(discretionary),
        "recurring_spending": m(recurring_total),
        "recurring_payment_count": len(patterns),
        "average_monthly_surplus": inputs.get("calculated_monthly_surplus", "0.00"),
        "potential_round_ups": m(
            roundup_record.historical_round_up_total if roundup_record else ZERO
        ),
        "safe_round_up_allowance": m(
            roundup_record.allowed_round_up_total if roundup_record else ZERO
        ),
        "potential_recoverable_spending": m(
            _decimal_state(totals.get("potential_recoverable", "0"))
        ),
        "confirmed_recoverable_spending": m(
            _decimal_state(totals.get("user_confirmed_recoverable", "0"))
        ),
        "high_confidence_recoverable_spending": m(
            _decimal_state(totals.get("high_confidence_recoverable", "0"))
        ),
        "safe_spare_amount": m(snapshot.safe_spare_now if snapshot else ZERO),
        "safe_monthly_contribution": m(
            snapshot.safe_monthly_contribution if snapshot else ZERO
        ),
        "safe_spare_confidence": snapshot.prov.confidence
        if snapshot and snapshot.prov
        else 0.0,
        "cashflow_confidence_score": snapshot.cashflow_confidence if snapshot else 0,
        "balance_is_estimated": snapshot.balance_is_estimated if snapshot else True,
        "goal_progress": {
            "goal_id": latest_goal.id if latest_goal else None,
            "goal_name": latest_goal.name if latest_goal else None,
            "target_amount": m(latest_goal.target_amount) if latest_goal else None,
            "contributed_to_date": m(contributed) if contributed is not None else None,
            "percent_complete": percent_complete,
        },
        "charts": {
            "income_vs_spending": [
                {
                    "label": key,
                    "income": m(monthly_income.get(key, ZERO)),
                    "spending": m(monthly_spend.get(key, ZERO)),
                }
                for key in months
            ],
            "category_breakdown": [
                {
                    "label": CATEGORY_LABELS[category],
                    "category": category.value,
                    "value": m(entry["total"]),
                    "percent": entry["percentage"],
                }
                for category, entry in sorted(
                    breakdown.items(), key=lambda kv: kv[1]["total"], reverse=True
                )
            ],
            "essential_vs_discretionary": [
                {"label": "Essential", "value": m(essential)},
                {"label": "Discretionary", "value": m(discretionary)},
            ],
            "recurring_vs_one_time": [
                {
                    "label": "Recurring",
                    "value": m(
                        sum(
                            (t.amount for t in spending_rows if t.id in recurring_ids),
                            ZERO,
                        )
                    ),
                },
                {
                    "label": "One-time",
                    "value": m(
                        sum(
                            (t.amount for t in spending_rows if t.id not in recurring_ids),
                            ZERO,
                        )
                    ),
                },
            ],
            "monthly_surplus_trend": [
                {
                    "label": key,
                    "value": m(
                        money(monthly_income.get(key, ZERO) - monthly_spend.get(key, ZERO))
                    ),
                }
                for key in months
            ],
            "safe_spare_trend": [
                {
                    "label": months[-1] if months else "",
                    "value": m(snapshot.safe_spare_now if snapshot else ZERO),
                }
            ],
            "upcoming_obligations": [
                {
                    "label": p.merchant,
                    "value": m(p.median_amount),
                    "due": _iso(p.next_expected_date),
                }
                for p in patterns
                if p.is_essential
            ],
            "principal_vs_growth": (
                [
                    {"label": "Your contributions", "value": m(latest_sim.user_contributions)},
                    {
                        "label": "Illustrative growth",
                        "value": m(latest_sim.illustrative_growth),
                    },
                ]
                if latest_sim is not None
                else []
            ),
        },
        "calculation_version": pipeline.PIPELINE_VERSION,
        "generated_at": analysis.completed_at or analysis.updated_at,
    }
