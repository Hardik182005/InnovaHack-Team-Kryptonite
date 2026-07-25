"""Transaction categorization — spec §10.

Ensemble, in order: merchant dictionary -> keyword/regex rules ->
essential/discretionary rules -> embedding similarity (optional) ->
statistical features -> LLM fallback for genuine ambiguity only.

§10 is explicit that we must not pretend a classifier was trained on real
labelled data. There is no such dataset here, so this is rules + merchant
dictionary, the confidence reflects that honestly, and the limitation is
documented rather than dressed up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from ..models.enums import Category, Direction, Essentiality, default_essentiality
from ..models.transaction import Transaction

CALCULATION_VERSION = "categorization.v1"

#: Known merchant -> category. High confidence: this is a direct lookup.
MERCHANT_CATEGORIES: Dict[str, Category] = {
    "netflix": Category.SUBSCRIPTION,
    "spotify": Category.SUBSCRIPTION,
    "disney+": Category.SUBSCRIPTION,
    "amazon prime": Category.SUBSCRIPTION,
    "dropbox": Category.SOFTWARE,
    "google one": Category.SOFTWARE,
    "adobe": Category.SOFTWARE,
    "github": Category.SOFTWARE,
    "planet fitness": Category.FITNESS,
    "peak fitness": Category.FITNESS,
    "uber eats": Category.DINING_DELIVERY,
    "doordash": Category.DINING_DELIVERY,
    "starbucks": Category.DINING_DELIVERY,
    "uber": Category.TRANSPORTATION,
    "lyft": Category.TRANSPORTATION,
    "shell": Category.FUEL,
    "amazon": Category.SHOPPING,
}

#: Keyword rules. Ordered — the first match wins, so specific patterns
#: (e.g. "rent") must precede general ones.
KEYWORD_RULES = [
    (Category.SALARY_INCOME, r"\b(payroll|salary|wages|direct deposit|stipend)\b"),
    (Category.RENT_HOUSING, r"\b(rent|lease|landlord|properties|housing|mortgage)\b"),
    (Category.LOAN_EMI, r"\b(emi|loan|repayment|instal?ment|finance co)\b"),
    (Category.INSURANCE, r"\b(insurance|assurance|policy premium|lic\b)\b"),
    (Category.TAX, r"\b(tax|irs|hmrc|gst|vat)\b"),
    (Category.MEDICAL, r"\b(clinic|hospital|pharmacy|medical|dental|doctor|health)\b"),
    (Category.UTILITIES, r"\b(electric|power|water|gas bill|internet|broadband|mobile|telecom)\b"),
    (Category.EDUCATION, r"\b(school|tuition|college|university|course|udemy|coursera)\b"),
    (Category.CHILDCARE, r"\b(daycare|childcare|nursery|babysit)\b"),
    (Category.GROCERIES, r"\b(grocer|supermarket|market|foods|mart|walmart|costco|aldi)\b"),
    (Category.DINING_DELIVERY, r"\b(restaurant|cafe|coffee|pizza|burger|deliver|eats|diner|bistro)\b"),
    (Category.FUEL, r"\b(fuel|petrol|gasoline|shell|bp|exxon|chevron)\b"),
    (Category.TRANSPORTATION, r"\b(uber|lyft|taxi|metro|transit|rail|bus|parking|toll)\b"),
    (Category.TRAVEL, r"\b(airline|flight|hotel|airbnb|booking\.com|expedia|travel)\b"),
    (Category.FITNESS, r"\b(gym|fitness|yoga|pilates|crossfit)\b"),
    (Category.SUBSCRIPTION, r"\b(subscription|subscr|membership|prime|plus monthly)\b"),
    (Category.SOFTWARE, r"\b(software|saas|cloud|hosting|domain|license|api)\b"),
    (Category.ENTERTAINMENT, r"\b(cinema|movie|theatre|concert|game|steam|playstation|xbox)\b"),
    (Category.SHOPPING, r"\b(store|shop|retail|mall|fashion|apparel|electronics)\b"),
    (Category.INTERNAL_TRANSFER, r"\b(transfer|trf|own account|self|to savings|from savings)\b"),
    (Category.CASH_WITHDRAWAL, r"\b(atm|cash withdrawal|cash wdl)\b"),
    (Category.BANK_CHARGE, r"\b(fee|charge|penalty|overdraft|service charge|interest charged)\b"),
    (Category.INVESTMENT, r"\b(brokerage|mutual fund|sip|etf|invest|securities)\b"),
    (Category.SAVINGS, r"\b(savings|deposit|rd\b|fd\b)\b"),
    (Category.REFUND_REIMBURSEMENT, r"\b(refund|reimburse|reversal|cashback|credited back)\b"),
    (Category.OTHER_INCOME, r"\b(interest earned|dividend|bonus|freelance|invoice paid)\b"),
]

_COMPILED = [(cat, re.compile(pattern, re.I)) for cat, pattern in KEYWORD_RULES]


@dataclass
class Classification:
    category: Category
    confidence: float
    method: str
    rule: Optional[str] = None
    essentiality: Essentiality = Essentiality.UNKNOWN
    calculation_version: str = CALCULATION_VERSION


def classify(
    description: str,
    normalized_merchant: Optional[str] = None,
    direction: Direction = Direction.DEBIT,
    amount: Optional[Decimal] = None,
) -> Classification:
    """Classify one transaction. Confidence reflects which rung matched."""
    haystack = " ".join(filter(None, [normalized_merchant or "", description or ""])).lower()

    # 1. merchant dictionary — most reliable signal available
    if normalized_merchant:
        key = normalized_merchant.lower()
        if key in MERCHANT_CATEGORIES:
            cat = MERCHANT_CATEGORIES[key]
            return Classification(
                cat, 0.95, "merchant_dictionary", key, default_essentiality(cat)
            )

    # 2. keyword / regex rules
    for cat, pattern in _COMPILED:
        match = pattern.search(haystack)
        if match:
            # A credit matching a debit-shaped rule is usually a refund or income.
            if direction is Direction.CREDIT and cat not in (
                Category.SALARY_INCOME,
                Category.OTHER_INCOME,
                Category.REFUND_REIMBURSEMENT,
                Category.INTERNAL_TRANSFER,
            ):
                continue
            return Classification(
                cat, 0.82, "keyword_rule", pattern.pattern, default_essentiality(cat)
            )

    # 3. direction-based statistical fallback
    if direction is Direction.CREDIT:
        return Classification(
            Category.OTHER_INCOME, 0.5, "direction_heuristic", "credit_without_match",
            Essentiality.DISCRETIONARY,
        )

    # 4. genuinely unknown — routed to review and, if configured, to the LLM
    #    fallback in app/ai. Low confidence keeps it out of round-ups (§6.8).
    return Classification(Category.UNKNOWN, 0.3, "unresolved", None, Essentiality.UNKNOWN)


def classify_transactions(transactions: Iterable[Transaction]) -> List[Transaction]:
    """Classify in place, skipping any row the user has already corrected (§10)."""
    out: List[Transaction] = []
    for t in transactions:
        if t.user_overridden:
            out.append(t)
            continue
        result = classify(
            t.description,
            normalized_merchant=t.normalized_merchant,
            direction=t.direction,
            amount=t.amount,
        )
        t.category = result.category
        t.category_confidence = result.confidence
        t.category_method = result.method
        t.category_rule = result.rule
        t.essentiality = result.essentiality
        if t.category is Category.INTERNAL_TRANSFER:
            t.is_internal_transfer = True
        if t.category is Category.REFUND_REIMBURSEMENT:
            t.is_reimbursement = True
        out.append(t)
    return out


def category_breakdown(transactions: Iterable[Transaction]) -> Dict[Category, Dict]:
    """Per-category totals for the Spending Intelligence page (§6.5)."""
    rows = [t for t in transactions if t.counts_toward_spending]
    total = sum((t.amount for t in rows), Decimal("0.00"))
    out: Dict[Category, Dict] = {}
    for t in rows:
        entry = out.setdefault(
            t.category,
            {
                "total": Decimal("0.00"),
                "count": 0,
                "essentiality": t.essentiality,
                "confidence_sum": 0.0,
                "evidence_transaction_ids": [],
            },
        )
        entry["total"] += t.amount
        entry["count"] += 1
        entry["confidence_sum"] += t.category_confidence
        entry["evidence_transaction_ids"].append(t.id)
    for cat, entry in out.items():
        entry["percentage"] = (
            round(float(entry["total"] / total) * 100, 1) if total else 0.0
        )
        entry["confidence"] = round(entry["confidence_sum"] / entry["count"], 2)
        del entry["confidence_sum"]
    return out
