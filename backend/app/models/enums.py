"""Category taxonomy and shared enums.

Spec §6.5 fixes the category list; §6.8 and §25 fix which categories are protected
from round-ups and from automated cancellation advice. Those two sets are the
backbone of the mandatory guardrail tests, so they live here as data rather than
being re-derived at each call site.
"""

from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    """The 26 categories from spec §6.5, verbatim and in order."""

    SALARY_INCOME = "salary_income"
    OTHER_INCOME = "other_income"
    RENT_HOUSING = "rent_housing"
    UTILITIES = "utilities"
    GROCERIES = "groceries"
    DINING_DELIVERY = "dining_delivery"
    TRANSPORTATION = "transportation"
    FUEL = "fuel"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    SUBSCRIPTION = "subscription"
    SOFTWARE = "software"
    FITNESS = "fitness"
    EDUCATION = "education"
    MEDICAL = "medical"
    INSURANCE = "insurance"
    LOAN_EMI = "loan_emi"
    TAX = "tax"
    CHILDCARE = "childcare"
    TRAVEL = "travel"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    INTERNAL_TRANSFER = "internal_transfer"
    CASH_WITHDRAWAL = "cash_withdrawal"
    BANK_CHARGE = "bank_charge"
    REFUND_REIMBURSEMENT = "refund_reimbursement"
    UNKNOWN = "unknown"


class Direction(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class Essentiality(str, Enum):
    ESSENTIAL = "essential"
    DISCRETIONARY = "discretionary"
    UNKNOWN = "unknown"


class UsageStatus(str, Enum):
    """Spec §6.9 — the only permitted usage states.

    UNKNOWN is the default and must never be reported as "unused" (§25.9).
    """

    UNKNOWN = "usage_unknown"
    POSSIBLY_UNDERUSED = "possibly_underused"
    CONFIRMED_REGULAR = "user_confirms_regular_use"
    CONFIRMED_OCCASIONAL = "user_confirms_occasional_use"
    CONFIRMED_NOT_USED = "user_confirms_not_used"
    NOT_RECOGNIZED = "user_does_not_recognize_payment"


class LeakDecision(str, Enum):
    """Spec §6.9 available actions."""

    KEEP = "keep"
    REVIEW = "review"
    CANCEL = "cancel"
    DOWNGRADE = "downgrade"
    RENEGOTIATE = "renegotiate"
    MARK_ESSENTIAL = "mark_essential"
    NOT_MINE = "not_mine"
    REVIEW_LATER = "review_later"


class ReviewStatus(str, Enum):
    """Confidence banding from §11 and §14."""

    CONFIRMED = "confirmed"
    LIKELY = "likely"
    NEEDS_REVIEW = "needs_review"


class Frequency(str, Enum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    ANNUAL = "annual"


#: Median days between occurrences for each supported frequency (§11).
FREQUENCY_DAYS = {
    Frequency.WEEKLY: 7.0,
    Frequency.BIWEEKLY: 14.0,
    Frequency.MONTHLY: 30.44,
    Frequency.QUARTERLY: 91.31,
    Frequency.HALF_YEARLY: 182.62,
    Frequency.ANNUAL: 365.25,
}


#: Categories that are essential by definition. Drives essential-outflow
#: projection in the Safe Spare engine (§6.6).
ESSENTIAL_CATEGORIES = frozenset(
    {
        Category.RENT_HOUSING,
        Category.UTILITIES,
        Category.GROCERIES,
        Category.MEDICAL,
        Category.INSURANCE,
        Category.LOAN_EMI,
        Category.TAX,
        Category.EDUCATION,
        Category.CHILDCARE,
    }
)


#: Never recommend cancelling these merely because they recur (§3.15, §25.5-25.8).
#: This is a hard block, independent of leak score.
PROTECTED_FROM_CANCELLATION = frozenset(
    {
        Category.RENT_HOUSING,
        Category.LOAN_EMI,
        Category.INSURANCE,
        Category.TAX,
        Category.MEDICAL,
        Category.UTILITIES,
        Category.EDUCATION,
        Category.CHILDCARE,
    }
)


#: Excluded from round-ups by default (§6.8). Superset of the essentials plus
#: money that is not really "spending" (transfers, withdrawals, refunds, charges).
ROUNDUP_EXCLUDED_CATEGORIES = frozenset(
    {
        Category.RENT_HOUSING,
        Category.LOAN_EMI,
        Category.INSURANCE,
        Category.MEDICAL,
        Category.TAX,
        Category.EDUCATION,
        Category.CHILDCARE,
        Category.INTERNAL_TRANSFER,
        Category.CASH_WITHDRAWAL,
        Category.SAVINGS,
        Category.INVESTMENT,
        Category.REFUND_REIMBURSEMENT,
        Category.BANK_CHARGE,
        Category.SALARY_INCOME,
        Category.OTHER_INCOME,
    }
)


#: Categories treated as income when aggregating (§6.4).
INCOME_CATEGORIES = frozenset({Category.SALARY_INCOME, Category.OTHER_INCOME})


#: Only discretionary recurring expenses may receive a leak score (§13).
LEAK_ELIGIBLE_CATEGORIES = frozenset(
    {
        Category.SUBSCRIPTION,
        Category.SOFTWARE,
        Category.ENTERTAINMENT,
        Category.FITNESS,
        Category.DINING_DELIVERY,
        Category.SHOPPING,
        Category.TRAVEL,
    }
)


def default_essentiality(category: Category) -> Essentiality:
    """Baseline essential/discretionary status for a category.

    UNKNOWN stays UNKNOWN rather than defaulting to discretionary, so that an
    unclassified transaction can never be silently swept into round-up eligibility.
    """
    if category in ESSENTIAL_CATEGORIES:
        return Essentiality.ESSENTIAL
    if category is Category.UNKNOWN:
        return Essentiality.UNKNOWN
    return Essentiality.DISCRETIONARY
