"""Silent price-increase detection — spec §12.

"Never allow an LLM to calculate these values." Every figure below is arithmetic
over verified transactions, with the evidence transaction IDs attached so the UI
can show its work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable, List, Optional, Tuple

from ..models.transaction import money
from .recurrence import RecurrencePattern, _median

CALCULATION_VERSION = "price_changes.v1"

ZERO = Decimal("0.00")

#: Configurable thresholds (§12). Both must be met to reduce false positives on
#: small charges, where a $0.30 rounding change is not a "price increase".
DEFAULT_MIN_ABSOLUTE_INCREASE = Decimal("1.00")
DEFAULT_MIN_PERCENTAGE_INCREASE = Decimal("5.0")


@dataclass
class PriceChange:
    merchant: str
    previous_amount: Decimal
    current_amount: Decimal
    absolute_increase: Decimal
    percentage_increase: Decimal
    first_date_of_new_price: date
    median_amount: Decimal
    rolling_average: Decimal
    confidence: float
    evidence_transaction_ids: List[str] = field(default_factory=list)
    calculation_version: str = CALCULATION_VERSION

    @property
    def annualized_increase(self) -> Decimal:
        return money(self.absolute_increase * Decimal("12"))


def detect_price_changes(
    patterns: Iterable[RecurrencePattern],
    amounts_by_pattern: Optional[dict] = None,
    min_absolute: Decimal = DEFAULT_MIN_ABSOLUTE_INCREASE,
    min_percentage: Decimal = DEFAULT_MIN_PERCENTAGE_INCREASE,
) -> List[PriceChange]:
    """Find recurring charges whose latest amount rose above both thresholds.

    `amounts_by_pattern` maps merchant key -> ordered list of (date, amount, txn_id).
    When omitted, the pattern's own median/latest pair is used, which is enough to
    detect a hike but cannot pinpoint the first date of the new price.
    """
    changes: List[PriceChange] = []
    amounts_by_pattern = amounts_by_pattern or {}

    for p in patterns:
        history = amounts_by_pattern.get(p.merchant)
        if not history or len(history) < 2:
            continue

        history = sorted(history, key=lambda row: row[0])
        amounts = [money(row[1]) for row in history]

        split = _find_price_step(amounts, min_absolute, min_percentage)
        if split is None:
            continue
        k, previous, current = split

        absolute = money(current - previous)
        percentage = (
            (Decimal(current - previous) / previous * Decimal("100"))
        ).quantize(Decimal("0.1"))

        first_new = history[k][0]
        # Evidence: the last payment at the old price and the first at the new one.
        evidence = [row[2] for row in history[k - 1 : k + 1] if len(row) > 2]

        changes.append(
            PriceChange(
                merchant=p.merchant,
                previous_amount=previous,
                current_amount=current,
                absolute_increase=absolute,
                percentage_increase=percentage,
                first_date_of_new_price=first_new,
                median_amount=_median(amounts[:k]),
                rolling_average=money(sum(amounts[:k], ZERO) / Decimal(k)),
                confidence=_confidence(p, len(amounts)),
                evidence_transaction_ids=evidence,
            )
        )

    changes.sort(key=lambda c: c.percentage_increase, reverse=True)
    return changes


#: A plateau is a run of payments whose spread is within this fraction of its
#: mean. Real subscriptions sit exactly flat; 4% tolerates a rounding or FX wobble.
PLATEAU_TOLERANCE = Decimal("0.04")

#: Both sides of the step need this many payments. Without it, any two-payment
#: merchant (`$20` then `$60`) reads as a 200% "price rise".
MIN_PLATEAU_LENGTH = 2


def _coefficient_of_variation(values: List[Decimal]) -> Decimal:
    """Spread relative to the mean. 0 means every payment is identical."""
    if not values:
        return Decimal("1")
    mean = sum(values, ZERO) / Decimal(len(values))
    if mean == 0:
        return Decimal("1")
    spread = max(values) - min(values)
    return spread / mean


def _find_price_step(
    amounts: List[Decimal], min_absolute: Decimal, min_percentage: Decimal
) -> Optional[Tuple[int, Decimal, Decimal]]:
    """Locate a genuine price step: one stable plateau followed by a higher one.

    This replaces a naive "latest vs previous" comparison, which fails in both
    directions on real data:

    * A hike that happened three months ago and has been stable since is
      invisible to a last-two comparison, yet it is exactly the "silent price
      increase" §12 asks us to surface.
    * Discretionary spending at one merchant (fuel, cafes) fluctuates every
      cycle, so a last-two comparison reports a "price rise" on what is simply a
      bigger purchase. Those merchants have no price to speak of.

    Requiring both sides to be internally flat separates the two cleanly.
    Returns (split_index, old_price, new_price) or None.
    """
    n = len(amounts)
    if n < MIN_PLATEAU_LENGTH * 2:
        return None

    best: Optional[Tuple[int, Decimal, Decimal]] = None
    best_jump = ZERO

    for k in range(MIN_PLATEAU_LENGTH, n - MIN_PLATEAU_LENGTH + 1):
        before, after = amounts[:k], amounts[k:]
        if _coefficient_of_variation(before) > PLATEAU_TOLERANCE:
            continue
        if _coefficient_of_variation(after) > PLATEAU_TOLERANCE:
            continue

        old_price = money(sum(before, ZERO) / Decimal(len(before)))
        new_price = money(sum(after, ZERO) / Decimal(len(after)))
        if old_price <= 0 or new_price <= old_price:
            continue

        absolute = new_price - old_price
        percentage = absolute / old_price * Decimal("100")
        if absolute < money(min_absolute) or percentage < min_percentage:
            continue

        if absolute > best_jump:
            best_jump = absolute
            best = (k, old_price, new_price)

    return best


def _confidence(pattern: RecurrencePattern, sample_size: int) -> float:
    """Confidence in the *hike*, bounded by confidence in the pattern itself.

    A price change on a shaky pattern cannot be more certain than the pattern.
    """
    base = pattern.confidence / 100.0
    sample_bonus = min(0.15, (sample_size - 2) * 0.05)
    if pattern.amount_varies:
        # A charge that always fluctuates makes any single rise weaker evidence.
        base *= 0.7
    return round(min(1.0, base + sample_bonus), 2)
