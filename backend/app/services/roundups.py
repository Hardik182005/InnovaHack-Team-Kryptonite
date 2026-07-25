"""Smart Round-Up Engine — spec §6.8.

Deterministic. No LLM may participate in any calculation here (§3.7, §14).

The single most important line in this module is the `min()` in
`calculate_roundups`: the allowed contribution is clamped by the Safe Spare
budget, which is what separates SafeSpare from an ordinary round-up app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from typing import Dict, Iterable, List, Optional, Sequence

from ..models.enums import (
    ROUNDUP_EXCLUDED_CATEGORIES,
    Category,
    Essentiality,
)
from ..models.transaction import Transaction, money

CALCULATION_VERSION = "roundups.v1"

#: A debit far larger than the user's normal spending is treated as uncertain and
#: excluded by default (§6.8 "large uncertain transactions").
DEFAULT_LARGE_TRANSACTION_THRESHOLD = Decimal("2000.00")


@dataclass
class RoundUpRules:
    """User-configurable rules (§6.8). Every field maps to a UI control."""

    increment: Decimal = Decimal("1.00")
    monthly_cap: Optional[Decimal] = None
    per_transaction_cap: Optional[Decimal] = None
    excluded_categories: frozenset = ROUNDUP_EXCLUDED_CATEGORIES
    excluded_merchants: frozenset = frozenset()
    large_transaction_threshold: Decimal = DEFAULT_LARGE_TRANSACTION_THRESHOLD
    paused: bool = False

    def __post_init__(self) -> None:
        self.increment = money(self.increment)
        if self.increment <= 0:
            raise ValueError("round-up increment must be positive")
        if self.monthly_cap is not None:
            self.monthly_cap = money(self.monthly_cap)
        if self.per_transaction_cap is not None:
            self.per_transaction_cap = money(self.per_transaction_cap)


@dataclass
class RoundUpLine:
    """Per-transaction result, including *why* it was skipped."""

    transaction_id: str
    merchant: str
    amount: Decimal
    round_up: Decimal
    eligible: bool
    reason: Optional[str] = None


@dataclass
class RoundUpResult:
    lines: List[RoundUpLine] = field(default_factory=list)
    historical_round_up_total: Decimal = Decimal("0.00")
    allowed_round_up_total: Decimal = Decimal("0.00")
    limiting_factor: str = "none"
    explanation: str = ""
    eligible_count: int = 0
    excluded_count: int = 0
    calculation_version: str = CALCULATION_VERSION

    @property
    def source_transaction_ids(self) -> List[str]:
        return [line.transaction_id for line in self.lines if line.eligible]


def round_up_for_amount(amount: Decimal, increment: Decimal) -> Decimal:
    """`ceil(amount / increment) * increment - amount`, spec §6.8 verbatim.

    Exact multiples yield 0.00, which is correct: there is no spare change on a
    $5.00 purchase when rounding to $5.
    """
    amount = money(amount)
    increment = money(increment)
    if increment <= 0:
        raise ValueError("increment must be positive")
    steps = (amount / increment).to_integral_value(rounding=ROUND_CEILING)
    return money(steps * increment - amount)


def _ineligibility_reason(txn: Transaction, rules: RoundUpRules) -> Optional[str]:
    """Return why this transaction cannot be rounded up, or None if it can."""
    if txn.excluded:
        return "excluded_by_user"
    if not txn.is_debit:
        return "not_a_debit"
    if txn.is_internal_transfer or txn.category is Category.INTERNAL_TRANSFER:
        return "internal_transfer"
    if txn.is_reimbursement:
        return "reimbursement"
    if txn.category in rules.excluded_categories:
        return "excluded_category:%s" % txn.category.value
    # Essential spending is protected even if its category is not on the list —
    # e.g. a user marking a specific grocery run essential (§25.4).
    if txn.essentiality is Essentiality.ESSENTIAL:
        return "essential_spending"
    if txn.category is Category.UNKNOWN and txn.category_confidence < 0.7:
        return "low_confidence_category"
    key = (txn.normalized_merchant or txn.raw_merchant or "").lower()
    if key and key in {m.lower() for m in rules.excluded_merchants}:
        return "excluded_merchant"
    if txn.amount >= rules.large_transaction_threshold:
        return "large_uncertain_transaction"
    return None


def calculate_roundups(
    transactions: Iterable[Transaction],
    rules: Optional[RoundUpRules] = None,
    safe_monthly_contribution: Optional[Decimal] = None,
    user_round_up_cap: Optional[Decimal] = None,
) -> RoundUpResult:
    """Compute historical and *allowed* round-ups.

    `allowed_round_up_total = min(historical, safe_monthly_contribution, cap)`
    per §6.8. When the result is zero we always explain why (§6.8 last rule),
    because a silent zero reads as a bug to the user.
    """
    rules = rules or RoundUpRules()
    result = RoundUpResult()

    if rules.paused:
        result.limiting_factor = "paused"
        result.explanation = "Round-ups are paused. No contribution is being calculated."
        return result

    total = Decimal("0.00")
    for txn in transactions:
        reason = _ineligibility_reason(txn, rules)
        if reason is not None:
            result.lines.append(
                RoundUpLine(
                    transaction_id=txn.id,
                    merchant=txn.normalized_merchant or txn.description,
                    amount=txn.amount,
                    round_up=Decimal("0.00"),
                    eligible=False,
                    reason=reason,
                )
            )
            result.excluded_count += 1
            continue

        ru = round_up_for_amount(txn.amount, rules.increment)
        if rules.per_transaction_cap is not None and ru > rules.per_transaction_cap:
            ru = rules.per_transaction_cap

        total += ru
        result.lines.append(
            RoundUpLine(
                transaction_id=txn.id,
                merchant=txn.normalized_merchant or txn.description,
                amount=txn.amount,
                round_up=ru,
                eligible=True,
            )
        )
        result.eligible_count += 1

    result.historical_round_up_total = money(total)

    # Clamp chain. Order matters only for reporting the limiting factor.
    allowed = result.historical_round_up_total
    limiting = "historical_round_ups"

    if rules.monthly_cap is not None and rules.monthly_cap < allowed:
        allowed = rules.monthly_cap
        limiting = "monthly_cap"
    if user_round_up_cap is not None and user_round_up_cap < allowed:
        allowed = money(user_round_up_cap)
        limiting = "user_round_up_cap"
    if safe_monthly_contribution is not None and money(safe_monthly_contribution) < allowed:
        allowed = money(safe_monthly_contribution)
        limiting = "safe_monthly_contribution"

    result.allowed_round_up_total = money(max(Decimal("0.00"), allowed))
    result.limiting_factor = limiting
    result.explanation = _explain(result, safe_monthly_contribution)
    return result


def _explain(result: RoundUpResult, safe_monthly_contribution: Optional[Decimal]) -> str:
    """Deterministic explanation text.

    This is a template, not a model call — the app must keep working with every
    LLM provider down (§3.21, §14).
    """
    hist = result.historical_round_up_total
    allowed = result.allowed_round_up_total

    if hist == 0:
        return (
            "No eligible transactions produced round-ups. "
            "Essential payments, transfers and withdrawals are excluded by default."
        )
    if allowed == 0:
        if safe_monthly_contribution is not None and money(safe_monthly_contribution) <= 0:
            return (
                "Your transactions created %s in potential round-ups, but none can be "
                "redirected right now because upcoming essential bills leave no safely "
                "spare balance before your next expected income." % _fmt(hist)
            )
        return (
            "Your transactions created %s in potential round-ups, but your current "
            "settings allow %s." % (_fmt(hist), _fmt(allowed))
        )
    if allowed < hist:
        reasons = {
            "safe_monthly_contribution": (
                "only %s is considered safely redirectable because essential bills are "
                "due before your next expected income" % _fmt(allowed)
            ),
            "monthly_cap": "your monthly cap limits this to %s" % _fmt(allowed),
            "user_round_up_cap": "your round-up cap limits this to %s" % _fmt(allowed),
        }
        tail = reasons.get(result.limiting_factor, "the allowance is %s" % _fmt(allowed))
        return "Your transactions created %s in potential round-ups, but %s." % (
            _fmt(hist),
            tail,
        )
    return (
        "Your transactions created %s in potential round-ups, all of which is within "
        "your safe contribution limit." % _fmt(hist)
    )


def _fmt(value: Decimal) -> str:
    return "$%s" % money(value)


def group_by_merchant(result: RoundUpResult) -> Dict[str, Decimal]:
    """Round-up totals per merchant, for the dashboard breakdown."""
    out: Dict[str, Decimal] = {}
    for line in result.lines:
        if line.eligible:
            out[line.merchant] = money(out.get(line.merchant, Decimal("0.00")) + line.round_up)
    return out


def excluded_reasons_summary(result: RoundUpResult) -> Dict[str, int]:
    """Counts per exclusion reason — powers the "why was this skipped" UI."""
    out: Dict[str, int] = {}
    for line in result.lines:
        if not line.eligible and line.reason:
            key = line.reason.split(":")[0]
            out[key] = out.get(key, 0) + 1
    return out


def eligible_lines(result: RoundUpResult) -> Sequence[RoundUpLine]:
    return [line for line in result.lines if line.eligible]
