"""Safe Spare Engine — spec §6.6. The product's central innovation.

An ordinary round-up app asks "what is the spare change?". This module asks
"what can this person's life actually spare before the next salary lands?" —
income timing, essential obligations, a safety buffer and a volatility reserve
are all subtracted first.

Every value here is computed in Python from verified transactions. No LLM is
consulted, and `safe_spare_now` can never be negative (§6.6 last line, §25.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence

from ..models.enums import INCOME_CATEGORIES, Category, Essentiality
from ..models.transaction import Transaction, money

CALCULATION_VERSION = "safe_spare.v1"

ZERO = Decimal("0.00")


@dataclass
class SafeSpareSettings:
    """User-controlled safety settings (§6.6, §6.8)."""

    user_minimum_buffer: Decimal = Decimal("200.00")
    buffer_percentage: Decimal = Decimal("0.25")  # of avg monthly essential spend
    volatility_multiplier: Decimal = Decimal("0.50")
    user_monthly_cap: Optional[Decimal] = None

    def __post_init__(self) -> None:
        self.user_minimum_buffer = money(self.user_minimum_buffer)
        if self.user_monthly_cap is not None:
            self.user_monthly_cap = money(self.user_monthly_cap)
        if self.buffer_percentage < 0 or self.volatility_multiplier < 0:
            raise ValueError("buffer percentage and volatility multiplier must be >= 0")


@dataclass
class SafeSpareInputs:
    """Everything the formula needs, all of it derived from transactions."""

    latest_verified_balance: Optional[Decimal] = None
    balance_is_estimated: bool = False
    expected_income_before_next_income: Decimal = ZERO
    expected_essential_outflows_before_next_income: Decimal = ZERO
    average_monthly_essential_spending: Decimal = ZERO
    recent_monthly_outflows: List[Decimal] = field(default_factory=list)
    calculated_monthly_surplus: Decimal = ZERO
    next_income_date: Optional[date] = None
    missing_inputs: List[str] = field(default_factory=list)
    source_transaction_ids: List[str] = field(default_factory=list)


@dataclass
class SafeSpareResult:
    """Display contract for §6.6 — every intermediate value is exposed.

    The UI shows all of these so the user can see *why* the number is what it is.
    A single opaque figure would defeat the point of the product.
    """

    latest_verified_balance: Decimal = ZERO
    balance_is_estimated: bool = False
    expected_income: Decimal = ZERO
    upcoming_essential_outflows: Decimal = ZERO
    projected_balance_before_next_income: Decimal = ZERO
    safety_buffer: Decimal = ZERO
    volatility_reserve: Decimal = ZERO
    safe_spare_now: Decimal = ZERO
    safe_monthly_contribution: Decimal = ZERO
    confidence: float = 0.0
    limiting_factor: str = "none"
    reason: str = ""
    missing_inputs: List[str] = field(default_factory=list)
    next_income_date: Optional[date] = None
    calculation_version: str = CALCULATION_VERSION
    source_transaction_ids: List[str] = field(default_factory=list)


def _stdev(values: Sequence[Decimal]) -> Decimal:
    """Population-free sample standard deviation in Decimal.

    Kept in Decimal rather than `statistics.stdev` so no float rounding can leak
    into a figure that reduces someone's contribution.
    """
    n = len(values)
    if n < 2:
        return ZERO
    mean = sum(values, ZERO) / Decimal(n)
    variance = sum(((v - mean) ** 2 for v in values), ZERO) / Decimal(n - 1)
    if variance <= 0:
        return ZERO
    return money(variance.sqrt())


def compute_safe_spare(
    inputs: SafeSpareInputs,
    settings: Optional[SafeSpareSettings] = None,
) -> SafeSpareResult:
    """Apply the §6.6 formulas exactly.

    projected = balance + expected_income - expected_essential_outflows
    buffer    = max(user_minimum_buffer, pct * avg_monthly_essential_spending)
    reserve   = multiplier * stdev(recent_monthly_outflows)
    spare     = max(0, projected - buffer - reserve)
    monthly   = min(spare, monthly_surplus, user_monthly_cap)
    """
    settings = settings or SafeSpareSettings()

    balance = inputs.latest_verified_balance
    missing = list(inputs.missing_inputs)
    if balance is None:
        balance = ZERO
        if "latest_verified_balance" not in missing:
            missing.append("latest_verified_balance")

    projected = money(
        money(balance)
        + money(inputs.expected_income_before_next_income)
        - money(inputs.expected_essential_outflows_before_next_income)
    )

    buffer_from_pct = money(
        settings.buffer_percentage * money(inputs.average_monthly_essential_spending)
    )
    safety_buffer = max(settings.user_minimum_buffer, buffer_from_pct)

    volatility_reserve = money(
        settings.volatility_multiplier * _stdev(inputs.recent_monthly_outflows)
    )

    # Clamped at zero: Safe Spare must never be negative (§6.6, §25.1).
    safe_spare_now = max(ZERO, money(projected - safety_buffer - volatility_reserve))

    # min() over the three ceilings, tracking which one bound the result.
    monthly = safe_spare_now
    limiting = "safe_spare_now"

    surplus = money(inputs.calculated_monthly_surplus)
    if surplus < monthly:
        monthly, limiting = surplus, "monthly_surplus"
    if settings.user_monthly_cap is not None and settings.user_monthly_cap < monthly:
        monthly, limiting = settings.user_monthly_cap, "user_monthly_cap"

    safe_monthly_contribution = max(ZERO, money(monthly))
    if safe_monthly_contribution == ZERO:
        limiting = "no_safe_capacity" if safe_spare_now == ZERO else limiting

    result = SafeSpareResult(
        latest_verified_balance=money(balance),
        balance_is_estimated=inputs.balance_is_estimated or balance is None,
        expected_income=money(inputs.expected_income_before_next_income),
        upcoming_essential_outflows=money(
            inputs.expected_essential_outflows_before_next_income
        ),
        projected_balance_before_next_income=projected,
        safety_buffer=safety_buffer,
        volatility_reserve=volatility_reserve,
        safe_spare_now=safe_spare_now,
        safe_monthly_contribution=safe_monthly_contribution,
        limiting_factor=limiting,
        missing_inputs=missing,
        next_income_date=inputs.next_income_date,
        source_transaction_ids=list(inputs.source_transaction_ids),
    )
    result.confidence = _confidence(inputs, result)
    result.reason = _explain(result)
    return result


def _confidence(inputs: SafeSpareInputs, result: SafeSpareResult) -> float:
    """Confidence degrades with missing or estimated inputs (§6.6).

    Starts at 1.0 and is penalised; never reported above 0.6 when the balance was
    estimated rather than read from the statement.
    """
    score = 1.0
    if inputs.balance_is_estimated or inputs.latest_verified_balance is None:
        score -= 0.4
    if not inputs.recent_monthly_outflows:
        score -= 0.15
    elif len(inputs.recent_monthly_outflows) < 3:
        score -= 0.08
    if inputs.next_income_date is None:
        score -= 0.15
    if inputs.average_monthly_essential_spending <= 0:
        score -= 0.1
    score -= 0.05 * len(
        [m for m in result.missing_inputs if m != "latest_verified_balance"]
    )
    return round(max(0.0, min(1.0, score)), 2)


def _explain(result: SafeSpareResult) -> str:
    """Deterministic explanation of why the contribution was limited or paused."""
    if result.safe_spare_now == ZERO:
        return (
            "No safely spare money right now: after your expected income of %s and "
            "%s of essential bills due before %s, the projected balance of %s does not "
            "clear your %s safety buffer and %s volatility reserve."
            % (
                _fmt(result.expected_income),
                _fmt(result.upcoming_essential_outflows),
                result.next_income_date or "your next expected income",
                _fmt(result.projected_balance_before_next_income),
                _fmt(result.safety_buffer),
                _fmt(result.volatility_reserve),
            )
        )
    reasons = {
        "monthly_surplus": (
            "Contribution is limited to %s by your average monthly surplus rather than "
            "by today's balance." % _fmt(result.safe_monthly_contribution)
        ),
        "user_monthly_cap": (
            "Contribution is limited to %s by the monthly cap you set."
            % _fmt(result.safe_monthly_contribution)
        ),
        "safe_spare_now": (
            "%s is safely spare after protecting %s of essential bills, a %s buffer and "
            "a %s volatility reserve."
            % (
                _fmt(result.safe_monthly_contribution),
                _fmt(result.upcoming_essential_outflows),
                _fmt(result.safety_buffer),
                _fmt(result.volatility_reserve),
            )
        ),
    }
    base = reasons.get(result.limiting_factor, "")
    if result.balance_is_estimated:
        base += (
            " This uses an estimated balance because your statement did not include a "
            "running balance, so confidence is reduced."
        )
    return base.strip()


def _fmt(value: Decimal) -> str:
    return "$%s" % money(value)


# ---------------------------------------------------------------------------
# Deriving inputs from real transactions
# ---------------------------------------------------------------------------


def _month_key(d: date) -> str:
    return "%04d-%02d" % (d.year, d.month)


def build_inputs(
    transactions: Iterable[Transaction],
    as_of: Optional[date] = None,
    upcoming_essentials: Optional[Decimal] = None,
    expected_income: Optional[Decimal] = None,
    next_income_date: Optional[date] = None,
) -> SafeSpareInputs:
    """Derive Safe Spare inputs from a transaction set.

    `upcoming_essentials` / `expected_income` are normally supplied by the
    recurrence engine, which knows the actual due dates. When they are absent we
    fall back to historical monthly averages and record the substitution in
    `missing_inputs` so the UI can show it (§6.6 "show missing inputs").
    """
    txns = [t for t in transactions if not t.excluded]
    if not txns:
        return SafeSpareInputs(missing_inputs=["no_transactions"])

    txns_sorted = sorted(txns, key=lambda t: t.date)
    as_of = as_of or txns_sorted[-1].date
    missing: List[str] = []

    # Latest verified balance: the most recent row that actually carried one.
    balance: Optional[Decimal] = None
    balance_txn_id: Optional[str] = None
    for t in reversed(txns_sorted):
        if t.balance is not None:
            balance, balance_txn_id = t.balance, t.id
            break

    balance_is_estimated = False
    if balance is None:
        # §6.6: fall back to a historical cash-flow estimate, clearly labelled.
        inflow = sum((t.amount for t in txns_sorted if t.counts_toward_income), ZERO)
        outflow = sum((t.amount for t in txns_sorted if t.counts_toward_spending), ZERO)
        balance = money(max(ZERO, inflow - outflow))
        balance_is_estimated = True
        missing.append("running_balance_absent_estimated_from_cashflow")

    # Monthly aggregates.
    monthly_out: Dict[str, Decimal] = {}
    monthly_in: Dict[str, Decimal] = {}
    monthly_essential: Dict[str, Decimal] = {}
    for t in txns_sorted:
        key = _month_key(t.date)
        if t.counts_toward_spending:
            monthly_out[key] = money(monthly_out.get(key, ZERO) + t.amount)
            if t.is_essential:
                monthly_essential[key] = money(monthly_essential.get(key, ZERO) + t.amount)
        elif t.counts_toward_income:
            monthly_in[key] = money(monthly_in.get(key, ZERO) + t.amount)

    months = sorted(set(list(monthly_out) + list(monthly_in)))
    n_months = max(1, len(months))

    avg_essential = money(sum(monthly_essential.values(), ZERO) / Decimal(n_months))
    avg_in = money(sum(monthly_in.values(), ZERO) / Decimal(n_months))
    avg_out = money(sum(monthly_out.values(), ZERO) / Decimal(n_months))
    surplus = money(max(ZERO, avg_in - avg_out))

    # Income timing: median gap between income credits.
    income_dates = [
        t.date
        for t in txns_sorted
        if t.counts_toward_income and t.category in INCOME_CATEGORIES
    ]
    if next_income_date is None and len(income_dates) >= 2:
        gaps = [
            (b - a).days for a, b in zip(income_dates, income_dates[1:]) if (b - a).days > 0
        ]
        if gaps:
            gaps.sort()
            median_gap = gaps[len(gaps) // 2]
            next_income_date = income_dates[-1] + timedelta(days=median_gap)
    if next_income_date is None:
        missing.append("next_income_date_unknown")

    if expected_income is None:
        # Income expected to ARRIVE strictly before the next income date.
        #
        # For a single-salary user this is zero: the salary *is* the next income
        # event, so it must not be added to today's balance. Counting it here
        # would credit the user with a paycheck they have not received and would
        # inflate every downstream contribution — precisely the mistake this
        # product exists to avoid. Only secondary income already evidenced
        # mid-cycle contributes.
        other_income = [
            t.amount
            for t in txns_sorted
            if t.counts_toward_income
            and t.category is Category.OTHER_INCOME
            and (next_income_date is None or t.date < next_income_date)
        ]
        months_span = max(1, len({_month_key(t.date) for t in txns_sorted}))
        expected_income = (
            money(sum(other_income, ZERO) / Decimal(months_span)) if other_income else ZERO
        )
        has_salary = any(
            t.counts_toward_income and t.category in INCOME_CATEGORIES
            for t in txns_sorted
        )
        if not has_salary:
            missing.append("expected_income_unknown")

    if upcoming_essentials is None:
        # Pro-rate the monthly essential average across the days until next income.
        days = (next_income_date - as_of).days if next_income_date else 30
        days = max(0, min(days, 62))
        upcoming_essentials = money(avg_essential * Decimal(days) / Decimal("30.44"))
        missing.append("upcoming_essentials_estimated_from_average")

    return SafeSpareInputs(
        latest_verified_balance=money(balance),
        balance_is_estimated=balance_is_estimated,
        expected_income_before_next_income=money(expected_income),
        expected_essential_outflows_before_next_income=money(upcoming_essentials),
        average_monthly_essential_spending=avg_essential,
        recent_monthly_outflows=[monthly_out[m] for m in months if m in monthly_out],
        calculated_monthly_surplus=surplus,
        next_income_date=next_income_date,
        missing_inputs=missing,
        source_transaction_ids=([balance_txn_id] if balance_txn_id else []),
    )


def apply_confirmed_recovery(
    result: SafeSpareResult, confirmed_recoverable: Decimal
) -> SafeSpareResult:
    """Add user-confirmed recovered spend to the contribution (§6.9, §25.10).

    Only amounts the user explicitly confirmed may raise the contribution — the
    caller is responsible for passing confirmed-only totals. Potential and
    high-confidence recoverable amounts must never reach this function.
    """
    confirmed = money(max(ZERO, confirmed_recoverable))
    if confirmed == ZERO:
        return result
    result.safe_monthly_contribution = money(result.safe_monthly_contribution + confirmed)
    result.reason += (
        " Includes %s of savings you confirmed by choosing to cancel or downgrade a service."
        % _fmt(confirmed)
    )
    return result
