"""Goal simulation — spec §6.10.

Deterministic future-value maths. Principal and illustrative growth are always
returned as separate figures (§25.12) so the UI can never present market growth
as money the user actually saved.

Nothing here executes, recommends or implies a real investment (§3.9, §3.11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from ..models.transaction import money

CALCULATION_VERSION = "projections.v1"

ZERO = Decimal("0.00")

#: Mandatory on every projection surface (§6.10).
ILLUSTRATIVE_DISCLAIMER = (
    "Illustrative simulation only. Actual returns may be higher, lower or negative."
)

#: Scenario set from §6.10. These are illustrative *assumptions*, not forecasts,
#: and deliberately not tied to any named security or product (§3.11).
SCENARIOS = {
    "contributions_only": Decimal("0.00"),
    "lower": Decimal("0.04"),
    "medium": Decimal("0.07"),
    "higher_volatility": Decimal("0.10"),
}


@dataclass
class GoalInputs:
    """§6.10 inputs."""

    target_amount: Decimal
    months: int
    starting_principal: Decimal = ZERO
    safe_monthly_contribution: Decimal = ZERO
    confirmed_recovered_amount: Decimal = ZERO
    roundup_contribution: Decimal = ZERO
    annual_return_rate: Decimal = Decimal("0.07")
    target_date: Optional[date] = None

    def __post_init__(self) -> None:
        self.target_amount = money(self.target_amount)
        self.starting_principal = money(self.starting_principal)
        self.safe_monthly_contribution = money(self.safe_monthly_contribution)
        self.confirmed_recovered_amount = money(self.confirmed_recovered_amount)
        self.roundup_contribution = money(self.roundup_contribution)
        if self.months < 0:
            raise ValueError("months must be >= 0")

    @property
    def monthly_contribution(self) -> Decimal:
        """Total monthly inflow: safe contribution + confirmed recovery + round-ups.

        Only *confirmed* recovery is included; unconfirmed findings must never
        inflate a projection (§25.10).
        """
        return money(
            self.safe_monthly_contribution
            + self.confirmed_recovered_amount
            + self.roundup_contribution
        )


@dataclass
class ScenarioResult:
    name: str
    annual_rate: Decimal
    user_contributions: Decimal
    illustrative_growth: Decimal
    projected_value: Decimal


@dataclass
class SimulationResult:
    """Everything §6.10 requires on screen."""

    user_contributions: Decimal = ZERO
    illustrative_growth: Decimal = ZERO
    projected_value: Decimal = ZERO
    goal_gap: Decimal = ZERO
    estimated_completion_months: Optional[int] = None
    estimated_completion_date: Optional[date] = None
    required_monthly_contribution: Decimal = ZERO
    safe_monthly_contribution: Decimal = ZERO
    contribution_shortfall: Decimal = ZERO
    achievable: bool = False
    scenarios: List[ScenarioResult] = field(default_factory=list)
    disclaimer: str = ILLUSTRATIVE_DISCLAIMER
    calculation_version: str = CALCULATION_VERSION


def future_value(
    principal: Decimal,
    monthly_contribution: Decimal,
    monthly_rate: Decimal,
    months: int,
) -> Decimal:
    """End-of-month annuity future value (§6.10).

    FV = P(1+r)^n + C * (((1+r)^n - 1) / r)

    The r == 0 branch is not an edge case to tolerate but a required scenario:
    "contributions only" is one of the four mandated scenarios, and the general
    formula divides by zero there.
    """
    principal = money(principal)
    monthly_contribution = money(monthly_contribution)
    if months <= 0:
        return principal
    if monthly_rate == 0:
        return money(principal + monthly_contribution * Decimal(months))
    growth = (Decimal("1") + monthly_rate) ** months
    return money(
        principal * growth + monthly_contribution * ((growth - Decimal("1")) / monthly_rate)
    )


def monthly_rate_from_annual(annual_rate: Decimal) -> Decimal:
    """Simple nominal conversion, matching the annuity formula's compounding."""
    return Decimal(annual_rate) / Decimal("12")


def required_monthly_contribution(
    target: Decimal, principal: Decimal, monthly_rate: Decimal, months: int
) -> Decimal:
    """Solve the FV formula for C. Zero-rate branch handled explicitly."""
    target = money(target)
    principal = money(principal)
    if months <= 0:
        return money(max(ZERO, target - principal))
    if monthly_rate == 0:
        return money(max(ZERO, (target - principal) / Decimal(months)))
    growth = (Decimal("1") + monthly_rate) ** months
    numerator = target - principal * growth
    if numerator <= 0:
        return ZERO
    return money(numerator * monthly_rate / (growth - Decimal("1")))


def months_to_target(
    target: Decimal,
    principal: Decimal,
    monthly_contribution: Decimal,
    monthly_rate: Decimal,
    max_months: int = 1200,
) -> Optional[int]:
    """First month at which the balance reaches the target.

    Iterative rather than closed-form: it stays correct for the zero-rate and
    zero-contribution cases, and 1200 iterations of Decimal maths is trivial.
    Returns None when the goal is unreachable (no contributions, no growth).
    """
    target = money(target)
    balance = money(principal)
    if balance >= target:
        return 0
    if monthly_contribution <= 0 and monthly_rate <= 0:
        return None
    for m in range(1, max_months + 1):
        balance = money(balance * (Decimal("1") + monthly_rate) + monthly_contribution)
        if balance >= target:
            return m
    return None


def _add_months(start: date, months: int) -> date:
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    # Clamp the day so month-end dates don't overflow (e.g. Jan 31 + 1 month).
    day = min(start.day, [31, 29 if _leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def simulate(inputs: GoalInputs, today: Optional[date] = None) -> SimulationResult:
    """Run the projection and all four mandated scenarios."""
    today = today or date.today()
    monthly = inputs.monthly_contribution
    rate = monthly_rate_from_annual(inputs.annual_return_rate)

    projected = future_value(inputs.starting_principal, monthly, rate, inputs.months)
    contributions = money(
        inputs.starting_principal + monthly * Decimal(max(0, inputs.months))
    )
    # Growth is the residual — reported separately, never folded into contributions.
    growth = money(projected - contributions)

    required = required_monthly_contribution(
        inputs.target_amount, inputs.starting_principal, rate, inputs.months
    )
    completion = months_to_target(
        inputs.target_amount, inputs.starting_principal, monthly, rate
    )

    result = SimulationResult(
        user_contributions=contributions,
        illustrative_growth=growth,
        projected_value=projected,
        goal_gap=money(max(ZERO, inputs.target_amount - projected)),
        estimated_completion_months=completion,
        estimated_completion_date=_add_months(today, completion) if completion else None,
        required_monthly_contribution=required,
        safe_monthly_contribution=inputs.safe_monthly_contribution,
        contribution_shortfall=money(max(ZERO, required - monthly)),
        achievable=projected >= inputs.target_amount,
    )

    for name, annual in SCENARIOS.items():
        r = monthly_rate_from_annual(annual)
        fv = future_value(inputs.starting_principal, monthly, r, inputs.months)
        result.scenarios.append(
            ScenarioResult(
                name=name,
                annual_rate=annual,
                user_contributions=contributions,
                illustrative_growth=money(fv - contributions),
                projected_value=fv,
            )
        )

    return result
