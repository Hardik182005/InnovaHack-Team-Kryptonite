"""Leak Radar scoring — spec §6.9 and §13.

Two rules in here carry most of the product's safety story:

1. `confirmed_non_usage` is 0 unless the *user* said they don't use it (§13).
   Bank data cannot tell you whether someone uses a gym (§3.12, §25.9).
2. Essential categories are hard-blocked from cancellation advice regardless of
   score (§3.15, §25.5-25.8), and the score is capped below the cancellation
   tier whenever usage is unknown (§13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from ..models.enums import (
    LEAK_ELIGIBLE_CATEGORIES,
    PROTECTED_FROM_CANCELLATION,
    Category,
    Frequency,
    LeakDecision,
    ReviewStatus,
    UsageStatus,
)
from ..models.transaction import money
from .price_changes import PriceChange
from .recurrence import RecurrencePattern

CALCULATION_VERSION = "leak_score.v1"

ZERO = Decimal("0.00")

#: §13 interpretation bands.
BAND_LOW = 30
BAND_REVIEW = 60
BAND_DOWNGRADE = 80

#: When usage is unknown the score may not reach the strongest tier (§13).
UNKNOWN_USAGE_CAP = BAND_DOWNGRADE - 1  # 79

#: Services whose categories overlap are candidates for "duplicate optional service".
DUPLICATE_GROUPS = {
    "cloud_storage": {"dropbox", "google one", "icloud", "onedrive", "box"},
    "music": {"spotify", "apple music", "youtube music", "tidal"},
    "video": {"netflix", "hulu", "disney+", "max", "prime video"},
    "fitness": {"planet fitness", "gold's gym", "classpass", "peloton"},
}


@dataclass
class LeakFinding:
    merchant: str
    category: Category
    frequency: Frequency
    monthly_cost: Decimal
    annual_cost: Decimal
    leak_score: int
    band: str
    usage_status: UsageStatus
    review_status: ReviewStatus
    recommended_actions: List[LeakDecision] = field(default_factory=list)
    # Score components, all shown in the UI (§13 "Show every score component")
    price_hike_severity: float = 0.0
    duplicate_probability: float = 0.0
    cost_burden: float = 0.0
    recurrence_commitment: float = 0.0
    confirmed_non_usage: float = 0.0
    duplicate_group: Optional[str] = None
    price_change: Optional[PriceChange] = None
    evidence_transaction_ids: List[str] = field(default_factory=list)
    explanation: str = ""
    protected: bool = False
    calculation_version: str = CALCULATION_VERSION


def _band(score: int) -> str:
    if score < BAND_LOW:
        return "low_concern"
    if score < BAND_REVIEW:
        return "review"
    if score < BAND_DOWNGRADE:
        return "consider_downgrade_or_renegotiation"
    return "strong_cancellation_review_after_confirmation"


def _price_hike_severity(change: Optional[PriceChange]) -> float:
    """0 -> 1 as the percentage increase runs 0% -> 40%."""
    if change is None:
        return 0.0
    pct = float(change.percentage_increase)
    return max(0.0, min(1.0, pct / 40.0))


def _duplicate_probability(
    merchant: str, all_merchants: Iterable[str]
) -> tuple:
    """Detect a second paid service in the same functional group."""
    m = merchant.lower()
    others = {o.lower() for o in all_merchants if o.lower() != m}
    for group, members in DUPLICATE_GROUPS.items():
        if any(member in m for member in members):
            overlap = [
                o for o in others if any(member in o for member in members)
            ]
            if overlap:
                return min(1.0, 0.6 + 0.2 * len(overlap)), group
            return 0.0, None
    return 0.0, None


def _cost_burden(monthly_cost: Decimal, monthly_discretionary: Decimal) -> float:
    """Share of discretionary spend this one service consumes.

    Scaled so that 10% of discretionary spending on a single subscription = 1.0.
    """
    if monthly_discretionary <= 0:
        return 0.0
    share = float(monthly_cost / monthly_discretionary)
    return max(0.0, min(1.0, share / 0.10))


def _recurrence_commitment(pattern: RecurrencePattern) -> float:
    """Longer-running, higher-cadence commitments score higher."""
    cadence = {
        Frequency.WEEKLY: 1.0,
        Frequency.BIWEEKLY: 0.9,
        Frequency.MONTHLY: 0.8,
        Frequency.QUARTERLY: 0.5,
        Frequency.HALF_YEARLY: 0.35,
        Frequency.ANNUAL: 0.25,
    }[pattern.frequency]
    longevity = min(1.0, pattern.occurrences / 12.0)
    return round(0.6 * cadence + 0.4 * longevity, 3)


def _confirmed_non_usage(usage: UsageStatus) -> float:
    """Only an explicit user statement produces a non-zero value (§13)."""
    if usage is UsageStatus.CONFIRMED_NOT_USED:
        return 1.0
    if usage is UsageStatus.NOT_RECOGNIZED:
        return 0.9
    if usage is UsageStatus.CONFIRMED_OCCASIONAL:
        return 0.4
    # UNKNOWN, POSSIBLY_UNDERUSED and CONFIRMED_REGULAR all contribute nothing.
    # POSSIBLY_UNDERUSED is a hypothesis, not evidence.
    return 0.0


def score_leaks(
    patterns: Iterable[RecurrencePattern],
    price_changes: Optional[Iterable[PriceChange]] = None,
    usage_statuses: Optional[Dict[str, UsageStatus]] = None,
    monthly_discretionary_spend: Decimal = ZERO,
) -> List[LeakFinding]:
    """Score discretionary recurring expenses only (§13 first line)."""
    patterns = list(patterns)
    usage_statuses = usage_statuses or {}
    changes_by_merchant = {c.merchant: c for c in (price_changes or [])}
    all_merchants = [p.merchant for p in patterns]

    findings: List[LeakFinding] = []
    for p in patterns:
        protected = p.category in PROTECTED_FROM_CANCELLATION or p.is_essential
        # Essentials are still surfaced (the user may want to renegotiate insurance),
        # but they never receive an automated cancellation recommendation.
        if not protected and p.category not in LEAK_ELIGIBLE_CATEGORIES:
            continue

        usage = usage_statuses.get(p.merchant, UsageStatus.UNKNOWN)
        change = changes_by_merchant.get(p.merchant)

        hike = _price_hike_severity(change)
        dup, group = _duplicate_probability(p.merchant, all_merchants)
        burden = _cost_burden(p.monthly_equivalent, monthly_discretionary_spend)
        commitment = _recurrence_commitment(p)
        non_usage = _confirmed_non_usage(usage)

        raw = (
            0.25 * hike
            + 0.20 * dup
            + 0.15 * burden
            + 0.15 * commitment
            + 0.25 * non_usage
        )
        score = int(round(raw * 100))

        # §13: cap below the strongest tier while usage is unknown.
        if usage is UsageStatus.UNKNOWN or usage is UsageStatus.POSSIBLY_UNDERUSED:
            score = min(score, UNKNOWN_USAGE_CAP)

        # Protected essentials are floored into the review bands at most.
        if protected:
            score = min(score, BAND_REVIEW - 1)

        review_status = p.status
        if p.confidence < 70:
            review_status = ReviewStatus.NEEDS_REVIEW

        finding = LeakFinding(
            merchant=p.merchant,
            category=p.category,
            frequency=p.frequency,
            monthly_cost=p.monthly_equivalent,
            annual_cost=money(p.monthly_equivalent * Decimal("12")),
            leak_score=score,
            band=_band(score),
            usage_status=usage,
            review_status=review_status,
            price_hike_severity=round(hike, 3),
            duplicate_probability=round(dup, 3),
            cost_burden=round(burden, 3),
            recurrence_commitment=commitment,
            confirmed_non_usage=round(non_usage, 3),
            duplicate_group=group,
            price_change=change,
            evidence_transaction_ids=list(p.transaction_ids),
            protected=protected,
        )
        finding.recommended_actions = _actions(finding, review_status)
        finding.explanation = _explain(finding, p)
        findings.append(finding)

    findings.sort(key=lambda f: f.leak_score, reverse=True)
    return findings


def _actions(finding: LeakFinding, review_status: ReviewStatus) -> List[LeakDecision]:
    """Permitted actions for this finding (§6.9).

    CANCEL is only ever offered after the user has confirmed non-usage on a
    non-protected, non-low-confidence finding.
    """
    if finding.protected:
        # Never CANCEL. Renegotiation is legitimate for insurance/utilities.
        return [LeakDecision.KEEP, LeakDecision.RENEGOTIATE, LeakDecision.MARK_ESSENTIAL]
    if review_status is ReviewStatus.NEEDS_REVIEW:
        return [LeakDecision.REVIEW, LeakDecision.REVIEW_LATER, LeakDecision.NOT_MINE]

    actions = [LeakDecision.KEEP, LeakDecision.REVIEW_LATER, LeakDecision.NOT_MINE]
    if finding.usage_status in (
        UsageStatus.CONFIRMED_NOT_USED,
        UsageStatus.NOT_RECOGNIZED,
    ):
        actions.insert(0, LeakDecision.CANCEL)
        actions.insert(1, LeakDecision.DOWNGRADE)
    elif finding.leak_score >= BAND_REVIEW:
        actions.insert(0, LeakDecision.DOWNGRADE)
        actions.insert(1, LeakDecision.RENEGOTIATE)
    return actions


def _explain(finding: LeakFinding, pattern: RecurrencePattern) -> str:
    """Evidence-backed sentence. Deterministic; an LLM may only rephrase it."""
    parts = [
        "%s charges %s %s (%s/year)."
        % (
            finding.merchant,
            _fmt(pattern.median_amount),
            finding.frequency.value.replace("_", "-"),
            _fmt(finding.annual_cost),
        )
    ]
    if finding.price_change is not None:
        c = finding.price_change
        parts.append(
            "The charge rose from %s to %s (%s%%) starting %s."
            % (
                _fmt(c.previous_amount),
                _fmt(c.current_amount),
                c.percentage_increase,
                c.first_date_of_new_price,
            )
        )
    if finding.duplicate_group:
        parts.append(
            "You also pay for another %s service." % finding.duplicate_group.replace("_", " ")
        )
    if finding.usage_status is UsageStatus.UNKNOWN:
        parts.append(
            "Usage is unknown — bank data cannot show whether you use this. "
            "Confirm before deciding."
        )
    elif finding.usage_status is UsageStatus.CONFIRMED_NOT_USED:
        parts.append("You confirmed you have not used this service.")
    if finding.protected:
        parts.append(
            "This is an essential expense and is never recommended for cancellation."
        )
    return " ".join(parts)


def _fmt(value: Decimal) -> str:
    # Rupees. Every statement this product reads is INR, and these strings are
    # user-facing: a dollar sign on an Indian figure reads as a bug or, worse,
    # as a currency conversion that never happened.
    return "₹%s" % money(value)


def recoverable_totals(findings: Iterable[LeakFinding]) -> Dict[str, Decimal]:
    """The three separate totals §6.9 demands never be conflated.

    Only `user_confirmed` may flow into the contribution plan (§25.10).
    """
    potential = ZERO
    high_confidence = ZERO
    confirmed = ZERO
    for f in findings:
        if f.protected:
            continue
        potential = money(potential + f.monthly_cost)
        if f.review_status is not ReviewStatus.NEEDS_REVIEW and f.leak_score >= BAND_REVIEW:
            high_confidence = money(high_confidence + f.monthly_cost)
        if f.usage_status in (UsageStatus.CONFIRMED_NOT_USED, UsageStatus.NOT_RECOGNIZED):
            confirmed = money(confirmed + f.monthly_cost)
    return {
        "potential_recoverable": potential,
        "high_confidence_recoverable": high_confidence,
        "user_confirmed_recoverable": confirmed,
    }


def confirmed_recoverable_from_decisions(
    findings: Iterable[LeakFinding],
    decisions: Dict[str, LeakDecision],
) -> Decimal:
    """Only explicit CANCEL/DOWNGRADE decisions increase the contribution (§6.9).

    A DOWNGRADE recovers half the cost as a deliberately conservative estimate —
    overstating recovery would inflate the contribution the product exists to
    keep safe.
    """
    total = ZERO
    for f in findings:
        decision = decisions.get(f.merchant)
        if decision is None or f.protected:
            continue
        if decision is LeakDecision.CANCEL:
            total = money(total + f.monthly_cost)
        elif decision is LeakDecision.DOWNGRADE:
            total = money(total + f.monthly_cost / Decimal("2"))
    return total
