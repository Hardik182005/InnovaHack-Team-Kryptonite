"""Recurring-payment detection — spec §11.

"Do not use an LLM as the primary detector." This module is pure statistics over
normalized merchant groups: interval regularity, amount stability, occurrence
count. An LLM may later *describe* a pattern found here, never produce one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from ..models.enums import (
    ESSENTIAL_CATEGORIES,
    FREQUENCY_DAYS,
    Category,
    Frequency,
    ReviewStatus,
)
from ..models.transaction import Transaction, money

CALCULATION_VERSION = "recurrence.v1"

ZERO = Decimal("0.00")

#: Utility bills legitimately vary month to month (§11 last line), so amount
#: stability is scored leniently for these categories.
VARIABLE_AMOUNT_CATEGORIES = frozenset(
    {Category.UTILITIES, Category.FUEL, Category.MEDICAL}
)

MIN_OCCURRENCES_FOR_CONFIRMED = 3


@dataclass
class RecurrencePattern:
    merchant: str
    category: Category
    frequency: Frequency
    occurrences: int
    median_amount: Decimal
    latest_amount: Decimal
    first_date: date
    latest_date: date
    next_expected_date: Optional[date]
    confidence: float                      # 0-100
    status: ReviewStatus
    is_essential: bool
    amount_varies: bool
    interval_regularity: float = 0.0
    merchant_similarity: float = 1.0
    amount_stability: float = 0.0
    occurrence_strength: float = 0.0
    transaction_ids: List[str] = field(default_factory=list)
    calculation_version: str = CALCULATION_VERSION

    @property
    def monthly_equivalent(self) -> Decimal:
        """Normalize any cadence to a monthly cost, for leak/recovery maths."""
        days = FREQUENCY_DAYS[self.frequency]
        return money(self.median_amount * Decimal("30.44") / Decimal(str(days)))


def _median(values: List[Decimal]) -> Decimal:
    if not values:
        return ZERO
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return money(s[mid])
    return money((s[mid - 1] + s[mid]) / Decimal("2"))


def _median_float(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _classify_frequency(median_gap: float) -> Optional[Frequency]:
    """Snap the median inter-payment gap to the nearest supported cadence.

    Tolerance is proportional (25%) so annual renewals aren't rejected for
    drifting by a couple of weeks.
    """
    best: Optional[Frequency] = None
    best_err = None
    for freq, days in FREQUENCY_DAYS.items():
        err = abs(median_gap - days) / days
        if err <= 0.25 and (best_err is None or err < best_err):
            best, best_err = freq, err
    return best


def _interval_regularity(gaps: List[float], expected: float) -> float:
    """1.0 when every gap matches the expected cadence exactly."""
    if not gaps:
        return 0.0
    errs = [min(1.0, abs(g - expected) / expected) for g in gaps]
    return max(0.0, 1.0 - sum(errs) / len(errs))


def _amount_stability(amounts: List[Decimal], lenient: bool) -> float:
    """1.0 when the charge never changes.

    Utilities get a 3x tolerance multiplier rather than a free pass — a bill that
    triples is still worth flagging.
    """
    if len(amounts) < 2:
        return 0.0
    med = _median(amounts)
    if med == 0:
        return 0.0
    deviations = [abs(float((a - med) / med)) for a in amounts]
    avg_dev = sum(deviations) / len(deviations)
    tolerance = 0.60 if lenient else 0.20
    return max(0.0, 1.0 - min(1.0, avg_dev / tolerance))


def _occurrence_strength(n: int) -> float:
    """Saturates at 6 occurrences — more history adds little certainty."""
    if n <= 1:
        return 0.0
    return min(1.0, (n - 1) / 5.0)


def detect_recurring(
    transactions: Iterable[Transaction],
    min_occurrences: int = 2,
) -> List[RecurrencePattern]:
    """Group debits by normalized merchant and score each group (§11)."""
    groups: Dict[str, List[Transaction]] = {}
    for t in transactions:
        if t.excluded or not t.is_debit or t.is_internal_transfer:
            continue
        if t.category is Category.INTERNAL_TRANSFER:
            continue
        key = t.merchant_key()
        if not key:
            continue
        groups.setdefault(key, []).append(t)

    patterns: List[RecurrencePattern] = []
    for key, items in groups.items():
        if len(items) < min_occurrences:
            continue
        items.sort(key=lambda t: t.date)
        dates = [t.date for t in items]
        amounts = [t.amount for t in items]

        gaps = [float((b - a).days) for a, b in zip(dates, dates[1:]) if (b - a).days > 0]
        if not gaps:
            continue
        median_gap = _median_float(gaps)
        freq = _classify_frequency(median_gap)
        if freq is None:
            continue

        category = _dominant_category(items)
        lenient = category in VARIABLE_AMOUNT_CATEGORIES

        interval_regularity = _interval_regularity(gaps, FREQUENCY_DAYS[freq])
        # Merchant similarity is 1.0 here because grouping is already by the
        # normalized key; the fuzzy work happens upstream in normalization (§9).
        merchant_similarity = _merchant_similarity(items)
        # Two readings of the same data: the lenient one feeds the confidence
        # score (a utility bill should not lose confidence for being a utility
        # bill), the strict one answers "does this amount actually fluctuate?",
        # which price-change confidence depends on.
        amount_stability = _amount_stability(amounts, lenient)
        strict_stability = _amount_stability(amounts, lenient=False)
        occurrence_strength = _occurrence_strength(len(items))

        raw = (
            0.35 * interval_regularity
            + 0.25 * merchant_similarity
            + 0.20 * amount_stability
            + 0.20 * occurrence_strength
        )
        confidence = round(raw * 100, 1)

        status = _status_for(confidence, len(items), freq)
        # §11: three occurrences required for "confirmed" unless it is an annual
        # renewal, where two charges a year apart is the strongest evidence available.
        if (
            status is ReviewStatus.CONFIRMED
            and len(items) < MIN_OCCURRENCES_FOR_CONFIRMED
            and freq is not Frequency.ANNUAL
        ):
            status = ReviewStatus.LIKELY

        patterns.append(
            RecurrencePattern(
                merchant=items[0].normalized_merchant or items[0].description,
                category=category,
                frequency=freq,
                occurrences=len(items),
                median_amount=_median(amounts),
                latest_amount=amounts[-1],
                first_date=dates[0],
                latest_date=dates[-1],
                next_expected_date=dates[-1] + timedelta(days=int(round(median_gap))),
                confidence=confidence,
                status=status,
                is_essential=category in ESSENTIAL_CATEGORIES,
                amount_varies=strict_stability < 0.8,
                interval_regularity=round(interval_regularity, 3),
                merchant_similarity=round(merchant_similarity, 3),
                amount_stability=round(amount_stability, 3),
                occurrence_strength=round(occurrence_strength, 3),
                transaction_ids=[t.id for t in items],
            )
        )

    patterns.sort(key=lambda p: p.confidence, reverse=True)
    return patterns


def _status_for(confidence: float, occurrences: int, freq: Frequency) -> ReviewStatus:
    """§11 banding: 90-100 confirmed, 70-89 likely, below 70 needs review."""
    if confidence >= 90:
        return ReviewStatus.CONFIRMED
    if confidence >= 70:
        return ReviewStatus.LIKELY
    return ReviewStatus.NEEDS_REVIEW


def _dominant_category(items: List[Transaction]) -> Category:
    counts: Dict[Category, int] = {}
    for t in items:
        counts[t.category] = counts.get(t.category, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _merchant_similarity(items: List[Transaction]) -> float:
    """How consistently the raw descriptions map to one normalized merchant.

    Perfect agreement scores 1.0; a group assembled from many different raw
    strings scores lower, which correctly reduces confidence.
    """
    raws = {(t.raw_merchant or t.description).strip().lower() for t in items}
    if len(raws) <= 1:
        return 1.0
    return max(0.4, 1.0 - (len(raws) - 1) / (2.0 * len(items)))


def upcoming_essential_outflows(
    patterns: Iterable[RecurrencePattern],
    start: date,
    end: date,
) -> Decimal:
    """Sum essential recurring charges expected in [start, end].

    Feeds the Safe Spare engine's `expected_essential_outflows_before_next_income`,
    which is the whole reason SafeSpare protects rent before it invests spare change.
    """
    total = ZERO
    if end < start:
        return total
    for p in patterns:
        if not p.is_essential:
            continue
        cursor = p.next_expected_date
        if cursor is None:
            continue
        step = int(round(FREQUENCY_DAYS[p.frequency]))
        guard = 0
        while cursor <= end and guard < 24:
            if cursor >= start:
                total = money(total + p.median_amount)
            cursor = cursor + timedelta(days=step)
            guard += 1
    return total
