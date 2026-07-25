"""Transaction validation — spec §8.

"Never silently drop a transaction." Every problem found here becomes a warning
attached to the row and surfaced in the extraction review screen (§6.3). Nothing
in this module deletes data; it only annotates and flags for review.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from ..models.enums import Direction
from ..models.transaction import Transaction, money

CALCULATION_VERSION = "validation.v1"

ZERO = Decimal("0.00")

#: A transfer pair is two opposite entries of equal value within this window.
TRANSFER_WINDOW_DAYS = 3

#: Anything above this is flagged as implausible for a personal statement.
IMPLAUSIBLE_AMOUNT = Decimal("1000000.00")


@dataclass
class ValidationReport:
    warnings_by_transaction: Dict[str, List[str]] = field(default_factory=dict)
    statement_warnings: List[str] = field(default_factory=list)
    duplicate_groups: List[List[str]] = field(default_factory=list)
    transfer_pairs: List[Tuple[str, str]] = field(default_factory=list)
    balance_reconciles: Optional[bool] = None
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    currencies_seen: List[str] = field(default_factory=list)
    date_range: Optional[Tuple[date, date]] = None
    calculation_version: str = CALCULATION_VERSION

    @property
    def needs_review_count(self) -> int:
        return len(self.warnings_by_transaction)

    def add(self, transaction_id: str, warning: str) -> None:
        self.warnings_by_transaction.setdefault(transaction_id, []).append(warning)


def validate(transactions: Iterable[Transaction]) -> ValidationReport:
    """Run every §8 check and annotate rows in place."""
    txns = list(transactions)
    report = ValidationReport()
    if not txns:
        report.statement_warnings.append("no_transactions_extracted")
        return report

    _check_rows(txns, report)
    _check_duplicates(txns, report)
    _check_date_range(txns, report)
    _check_currency(txns, report)
    _check_transfer_pairs(txns, report)
    _check_running_balance(txns, report)

    # Push warnings back onto the transactions so the UI can show them per row.
    for t in txns:
        extra = report.warnings_by_transaction.get(t.id)
        if extra:
            for w in extra:
                if w not in t.validation_warnings:
                    t.validation_warnings.append(w)
    return report


def _check_rows(txns: List[Transaction], report: ValidationReport) -> None:
    """Per-row checks: amount format, direction exclusivity, impossible values."""
    for t in txns:
        if t.amount <= ZERO:
            report.add(t.id, "non_positive_amount")
        if t.amount >= IMPLAUSIBLE_AMOUNT:
            report.add(t.id, "implausible_amount")
        if t.amount.as_tuple().exponent < -2:
            report.add(t.id, "more_than_two_decimal_places")
        if not (t.description or "").strip() or t.description == "(no description)":
            report.add(t.id, "missing_description")
        if t.direction not in (Direction.DEBIT, Direction.CREDIT):
            report.add(t.id, "invalid_direction")
        if t.date > date.today() + timedelta(days=1):
            report.add(t.id, "future_dated")


def _check_duplicates(txns: List[Transaction], report: ValidationReport) -> None:
    """Exact duplicate rows (§8). Grouped, never auto-removed."""
    groups: Dict[tuple, List[str]] = defaultdict(list)
    for t in txns:
        key = (
            t.date,
            t.amount,
            t.direction,
            (t.description or "").strip().lower()[:50],
        )
        groups[key].append(t.id)
    for ids in groups.values():
        if len(ids) > 1:
            report.duplicate_groups.append(ids)
            for tid in ids:
                report.add(tid, "possible_duplicate")


def _check_date_range(txns: List[Transaction], report: ValidationReport) -> None:
    dates = sorted(t.date for t in txns)
    report.date_range = (dates[0], dates[-1])
    span = (dates[-1] - dates[0]).days
    if span > 400:
        report.statement_warnings.append("date_range_exceeds_13_months")
    if span == 0 and len(txns) > 5:
        report.statement_warnings.append("all_transactions_same_day_check_date_parsing")

    # Ambiguous d/m vs m/d: if no day-of-month exceeds 12, the order is unprovable.
    if len({d.day for d in dates}) > 1 and max(d.day for d in dates) <= 12:
        report.statement_warnings.append("ambiguous_day_month_order_confirm_date_format")


def _check_currency(txns: List[Transaction], report: ValidationReport) -> None:
    currencies = Counter(t.currency for t in txns if t.currency)
    report.currencies_seen = sorted(currencies)
    if len(currencies) > 1:
        report.statement_warnings.append("mixed_currencies_detected")
        dominant = currencies.most_common(1)[0][0]
        for t in txns:
            if t.currency != dominant:
                report.add(t.id, "currency_differs_from_statement")


def _check_transfer_pairs(txns: List[Transaction], report: ValidationReport) -> None:
    """Match equal-and-opposite entries — these are transfers, not spending (§8).

    Flagging them prevents a move between the user's own accounts being counted
    as both income and expenditure, which would distort the surplus figure that
    Safe Spare depends on.
    """
    debits = [t for t in txns if t.is_debit]
    credits = [t for t in txns if t.is_credit]
    used = set()
    for d in debits:
        for c in credits:
            if c.id in used or d.id in used:
                continue
            if c.amount != d.amount:
                continue
            if abs((c.date - d.date).days) > TRANSFER_WINDOW_DAYS:
                continue
            report.transfer_pairs.append((d.id, c.id))
            report.add(d.id, "possible_internal_transfer_pair")
            report.add(c.id, "possible_internal_transfer_pair")
            used.add(d.id)
            used.add(c.id)
            break


def _check_running_balance(txns: List[Transaction], report: ValidationReport) -> None:
    """Reconcile the running balance column where one exists (§8).

    A mismatch means either a missing transaction or a misread direction — both
    of which would silently corrupt the Safe Spare projection, so the statement
    is marked as not reconciling rather than trusted.
    """
    with_balance = sorted(
        [t for t in txns if t.balance is not None], key=lambda t: (t.date, t.source_row or 0)
    )
    if len(with_balance) < 2:
        report.balance_reconciles = None
        return

    report.opening_balance = with_balance[0].balance
    report.closing_balance = with_balance[-1].balance

    mismatches = 0
    for previous, current in zip(with_balance, with_balance[1:]):
        delta = current.amount if current.is_credit else -current.amount
        expected = money(previous.balance + delta)
        if expected != current.balance:
            mismatches += 1
            report.add(current.id, "balance_does_not_reconcile")
            # A mismatch of exactly 2x the amount means the sign is reversed.
            if money(previous.balance - delta) == current.balance:
                report.add(current.id, "reversed_debit_credit_suspected")

    report.balance_reconciles = mismatches == 0
    if mismatches:
        report.statement_warnings.append(
            "running_balance_mismatch_on_%d_rows" % mismatches
        )


def confidence_for(transaction: Transaction) -> float:
    """Overall row confidence: extraction quality minus validation penalties."""
    score = transaction.extraction_confidence
    score -= 0.1 * len(transaction.validation_warnings)
    if transaction.user_overridden:
        return 1.0  # a human corrected it; that is the highest confidence available
    return round(max(0.0, min(1.0, score)), 2)
