"""Cashflow Confidence — spec §6.7.

A transparent 0–100 score built from four weighted components:

    income regularity              30%
    essential-expense predictability  25%
    safety-buffer coverage         30%
    spending / balance stability   15%

This is **not a credit score** and must never be described as one, used to infer
creditworthiness, or computed from personal attributes (§6.7). It measures one
thing only: how predictable this person's cash flow is, and therefore how much
confidence the Safe Spare figure deserves.

Missing inputs *reduce* the score's confidence rather than inventing values
(testing prompt §18), so a thin statement produces a low-confidence score with
its gaps listed, never a fabricated one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from ..models.enums import INCOME_CATEGORIES, Category
from ..models.transaction import Transaction, money

CALCULATION_VERSION = "cashflow_confidence.v1"

ZERO = Decimal("0.00")

#: §6.7 component weights. They must sum to 1.0.
WEIGHTS = {
    "income_regularity": 0.30,
    "essential_predictability": 0.25,
    "buffer_coverage": 0.30,
    "spending_stability": 0.15,
}

#: Full buffer credit at three months of essential spending held in reserve.
TARGET_BUFFER_MONTHS = Decimal("3")


@dataclass
class ConfidenceComponent:
    """One scored component, with the evidence behind it."""

    name: str
    label: str
    weight: float
    value: float                      # 0.0-1.0
    points: float                     # value * weight * 100
    explanation: str
    evidence: Dict[str, str] = field(default_factory=dict)
    available: bool = True


@dataclass
class CashflowConfidence:
    score: int = 0
    band: str = "unknown"
    components: List[ConfidenceComponent] = field(default_factory=list)
    confidence: float = 0.0           # confidence in the score itself
    missing_inputs: List[str] = field(default_factory=list)
    improvement_suggestions: List[str] = field(default_factory=list)
    disclaimer: str = (
        "Cashflow Confidence is not a credit score. It measures how predictable "
        "your income and essential spending are, and is never used to assess "
        "creditworthiness."
    )
    calculation_version: str = CALCULATION_VERSION
    source_transaction_ids: List[str] = field(default_factory=list)


def _month_key(d: date) -> str:
    return "%04d-%02d" % (d.year, d.month)


def _mean(values: List[Decimal]) -> Decimal:
    if not values:
        return ZERO
    return money(sum(values, ZERO) / Decimal(len(values)))


def _coefficient_of_variation(values: List[Decimal]) -> Optional[float]:
    """Relative dispersion. None when there is too little data to judge."""
    if len(values) < 2:
        return None
    mean = _mean(values)
    if mean <= 0:
        return None
    variance = sum(((v - mean) ** 2 for v in values), ZERO) / Decimal(len(values) - 1)
    if variance <= 0:
        return 0.0
    return float(variance.sqrt() / mean)


def _stability_from_cv(cv: Optional[float], tolerance: float) -> float:
    """Map a coefficient of variation onto 0–1, where 0 variation scores 1.0."""
    if cv is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - cv / tolerance))


def compute(
    transactions: Iterable[Transaction],
    latest_balance: Optional[Decimal] = None,
    balance_is_estimated: bool = False,
) -> CashflowConfidence:
    """Score cash-flow predictability from verified transactions only."""
    txns = sorted(
        [t for t in transactions if not t.excluded], key=lambda t: t.date
    )
    result = CashflowConfidence()

    if not txns:
        result.missing_inputs.append("no_transactions")
        result.band = "unknown"
        result.improvement_suggestions.append(
            "Upload at least one statement so income and essential spending can be measured."
        )
        return result

    # --- monthly aggregates -------------------------------------------------
    monthly_income: Dict[str, Decimal] = {}
    monthly_essential: Dict[str, Decimal] = {}
    monthly_outflow: Dict[str, Decimal] = {}
    income_dates: List[date] = []

    for t in txns:
        key = _month_key(t.date)
        if t.counts_toward_income:
            monthly_income[key] = money(monthly_income.get(key, ZERO) + t.amount)
            if t.category in INCOME_CATEGORIES:
                income_dates.append(t.date)
        elif t.counts_toward_spending:
            monthly_outflow[key] = money(monthly_outflow.get(key, ZERO) + t.amount)
            if t.is_essential:
                monthly_essential[key] = money(
                    monthly_essential.get(key, ZERO) + t.amount
                )

    months = sorted(set(list(monthly_income) + list(monthly_outflow)))
    if len(months) < 2:
        result.missing_inputs.append("less_than_two_months_of_history")

    # --- 1. income regularity (30%) ----------------------------------------
    result.components.append(_income_regularity(income_dates, monthly_income, months))

    # --- 2. essential-expense predictability (25%) -------------------------
    result.components.append(_essential_predictability(monthly_essential, months))

    # --- 3. safety-buffer coverage (30%) -----------------------------------
    result.components.append(
        _buffer_coverage(latest_balance, monthly_essential, balance_is_estimated)
    )

    # --- 4. spending / balance stability (15%) -----------------------------
    result.components.append(_spending_stability(monthly_outflow, months))

    total_points = sum(c.points for c in result.components)
    result.score = int(round(max(0.0, min(100.0, total_points))))
    result.band = _band(result.score)

    for component in result.components:
        if not component.available:
            result.missing_inputs.append(component.name + "_unavailable")

    result.confidence = _confidence(result, len(months), balance_is_estimated)
    result.improvement_suggestions = _suggestions(result.components)
    result.source_transaction_ids = [t.id for t in txns[:200]]
    return result


def _income_regularity(
    income_dates: List[date],
    monthly_income: Dict[str, Decimal],
    months: List[str],
) -> ConfidenceComponent:
    """Regular income on a predictable date and in a predictable amount."""
    weight = WEIGHTS["income_regularity"]

    if not income_dates:
        return ConfidenceComponent(
            "income_regularity", "Income regularity", weight, 0.0, 0.0,
            "No salary or income deposits were identified, so income regularity "
            "cannot be measured.",
            available=False,
        )

    # Timing: how consistent are the gaps between income deposits?
    gaps = [
        float((b - a).days)
        for a, b in zip(income_dates, income_dates[1:])
        if (b - a).days > 0
    ]
    if gaps:
        mean_gap = sum(gaps) / len(gaps)
        spread = max(gaps) - min(gaps)
        timing = max(0.0, min(1.0, 1.0 - (spread / mean_gap) if mean_gap else 0.0))
    else:
        timing = 0.0

    # Amount: how consistent is the deposit size?
    amounts = [monthly_income[m] for m in months if m in monthly_income]
    amount_stability = _stability_from_cv(_coefficient_of_variation(amounts), 0.30)

    value = 0.6 * timing + 0.4 * amount_stability
    return ConfidenceComponent(
        "income_regularity",
        "Income regularity",
        weight,
        round(value, 3),
        round(value * weight * 100, 1),
        "Income arrived %d times with %s timing and %s amounts."
        % (
            len(income_dates),
            _describe(timing),
            _describe(amount_stability),
        ),
        {
            "income_deposits": str(len(income_dates)),
            "median_gap_days": ("%d" % int(sum(gaps) / len(gaps))) if gaps else "n/a",
            "timing_score": "%.2f" % timing,
            "amount_score": "%.2f" % amount_stability,
        },
    )


def _essential_predictability(
    monthly_essential: Dict[str, Decimal], months: List[str]
) -> ConfidenceComponent:
    """Stable essential outgoings make the Safe Spare projection reliable."""
    weight = WEIGHTS["essential_predictability"]
    values = [monthly_essential[m] for m in months if m in monthly_essential]

    if len(values) < 2:
        return ConfidenceComponent(
            "essential_predictability", "Essential-expense predictability", weight,
            0.0, 0.0,
            "Not enough months of essential spending to judge predictability.",
            available=False,
        )

    value = _stability_from_cv(_coefficient_of_variation(values), 0.35)
    return ConfidenceComponent(
        "essential_predictability",
        "Essential-expense predictability",
        weight,
        round(value, 3),
        round(value * weight * 100, 1),
        "Essential spending averaged %s per month and was %s."
        % (_fmt(_mean(values)), _describe(value)),
        {
            "months_observed": str(len(values)),
            "average_monthly_essential": str(_mean(values)),
            "lowest": str(min(values)),
            "highest": str(max(values)),
        },
    )


def _buffer_coverage(
    latest_balance: Optional[Decimal],
    monthly_essential: Dict[str, Decimal],
    balance_is_estimated: bool,
) -> ConfidenceComponent:
    """How many months of essential spending the current balance covers."""
    weight = WEIGHTS["buffer_coverage"]

    if latest_balance is None:
        return ConfidenceComponent(
            "buffer_coverage", "Safety-buffer coverage", weight, 0.0, 0.0,
            "No balance was available, so buffer coverage could not be measured. "
            "This lowers confidence rather than assuming a figure.",
            available=False,
        )

    values = list(monthly_essential.values())
    average_essential = _mean(values)
    if average_essential <= 0:
        return ConfidenceComponent(
            "buffer_coverage", "Safety-buffer coverage", weight, 0.0, 0.0,
            "No essential spending was identified, so buffer coverage cannot be "
            "expressed in months.",
            available=False,
        )

    months_covered = money(max(ZERO, money(latest_balance)) / average_essential)
    value = float(min(Decimal("1"), months_covered / TARGET_BUFFER_MONTHS))

    # An estimated balance is weaker evidence than a statement-verified one.
    if balance_is_estimated:
        value *= 0.6

    return ConfidenceComponent(
        "buffer_coverage",
        "Safety-buffer coverage",
        weight,
        round(value, 3),
        round(value * weight * 100, 1),
        "A balance of %s covers about %s months of essential spending "
        "(%s months is treated as full coverage).%s"
        % (
            _fmt(latest_balance),
            months_covered,
            TARGET_BUFFER_MONTHS,
            " The balance is estimated, so this component is discounted."
            if balance_is_estimated
            else "",
        ),
        {
            "latest_balance": str(money(latest_balance)),
            "average_monthly_essential": str(average_essential),
            "months_covered": str(months_covered),
            "balance_is_estimated": str(balance_is_estimated).lower(),
        },
    )


def _spending_stability(
    monthly_outflow: Dict[str, Decimal], months: List[str]
) -> ConfidenceComponent:
    """Volatile total spending makes any forward projection less reliable."""
    weight = WEIGHTS["spending_stability"]
    values = [monthly_outflow[m] for m in months if m in monthly_outflow]

    if len(values) < 2:
        return ConfidenceComponent(
            "spending_stability", "Spending stability", weight, 0.0, 0.0,
            "Not enough months of spending history to judge stability.",
            available=False,
        )

    value = _stability_from_cv(_coefficient_of_variation(values), 0.40)
    return ConfidenceComponent(
        "spending_stability",
        "Spending stability",
        weight,
        round(value, 3),
        round(value * weight * 100, 1),
        "Total monthly spending averaged %s and was %s."
        % (_fmt(_mean(values)), _describe(value)),
        {
            "months_observed": str(len(values)),
            "average_monthly_outflow": str(_mean(values)),
            "lowest": str(min(values)),
            "highest": str(max(values)),
        },
    )


def _band(score: int) -> str:
    if score >= 80:
        return "very_predictable"
    if score >= 60:
        return "predictable"
    if score >= 40:
        return "somewhat_predictable"
    if score >= 20:
        return "unpredictable"
    return "very_unpredictable"


def _confidence(
    result: CashflowConfidence, month_count: int, balance_is_estimated: bool
) -> float:
    """Confidence in the score itself, distinct from the score.

    Missing components and thin history reduce this rather than the score, so a
    user with two months of data is not told they are financially unstable — they
    are told we cannot yet be sure.
    """
    score = 1.0
    unavailable = [c for c in result.components if not c.available]
    score -= 0.2 * len(unavailable)
    if month_count < 3:
        score -= 0.2
    if month_count < 2:
        score -= 0.2
    if balance_is_estimated:
        score -= 0.15
    return round(max(0.0, min(1.0, score)), 2)


def _suggestions(components: List[ConfidenceComponent]) -> List[str]:
    """Actionable, non-judgemental improvements for the weakest components."""
    tips = {
        "income_regularity": (
            "Income timing varies. If some income is paid into another account, "
            "adding that statement will improve this score."
        ),
        "essential_predictability": (
            "Essential bills vary month to month. Reviewing variable bills such as "
            "utilities can make upcoming obligations easier to project."
        ),
        "buffer_coverage": (
            "Building the balance toward three months of essential spending would "
            "raise this component the most."
        ),
        "spending_stability": (
            "Total spending swings noticeably between months, which forces a larger "
            "volatility reserve and lowers the amount considered safely spare."
        ),
    }
    weakest = sorted(components, key=lambda c: c.value)
    out: List[str] = []
    for component in weakest:
        if component.value < 0.7 and component.name in tips:
            out.append(tips[component.name])
        if len(out) >= 3:
            break
    return out


def _describe(value: float) -> str:
    if value >= 0.85:
        return "highly consistent"
    if value >= 0.6:
        return "fairly consistent"
    if value >= 0.35:
        return "somewhat variable"
    return "highly variable"


def _fmt(value: Decimal) -> str:
    # Rupees. Every statement this product reads is INR, and these strings are
    # user-facing: a dollar sign on an Indian figure reads as a bug or, worse,
    # as a currency conversion that never happened.
    return "₹%s" % money(value)
