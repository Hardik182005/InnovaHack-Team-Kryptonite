"""Shared fixtures and builders for the deterministic-core tests."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.enums import Category, Direction, Essentiality  # noqa: E402
from app.models.transaction import Transaction  # noqa: E402


def txn(
    day,
    description,
    amount,
    direction=Direction.DEBIT,
    category=Category.UNKNOWN,
    merchant=None,
    balance=None,
    essentiality=None,
    **kwargs
):
    """Terse Transaction builder. `day` may be a date or a 2026 day-offset int."""
    if isinstance(day, int):
        day = date(2026, 1, 1) + timedelta(days=day)
    t = Transaction(
        date=day,
        description=description,
        amount=Decimal(str(amount)),
        direction=direction,
        category=category,
        normalized_merchant=merchant or description,
        balance=Decimal(str(balance)) if balance is not None else None,
        **kwargs
    )
    if essentiality is not None:
        t.essentiality = essentiality
    return t


def monthly_series(merchant, amount, category, months=6, day_of_month=5, start_year=2025):
    """A clean monthly recurring charge — the happy path for recurrence tests."""
    out = []
    for i in range(months):
        year = start_year + (day_of_month and 0) + (i // 12)
        month = (i % 12) + 1
        out.append(
            txn(
                date(year, month, day_of_month),
                merchant,
                amount,
                category=category,
                merchant=merchant,
            )
        )
    return out


@pytest.fixture
def salary_and_rent():
    """Two months of income plus protected essential outflows."""
    rows = []
    for month in (1, 2, 3):
        rows.append(
            txn(
                date(2026, month, 1),
                "ACME PAYROLL",
                4000,
                direction=Direction.CREDIT,
                category=Category.SALARY_INCOME,
                merchant="Acme Payroll",
            )
        )
        rows.append(
            txn(
                date(2026, month, 3),
                "GREENFIELD PROPERTIES RENT",
                1500,
                category=Category.RENT_HOUSING,
                merchant="Greenfield Properties",
            )
        )
        rows.append(
            txn(
                date(2026, month, 6),
                "SECURELIFE INSURANCE",
                120,
                category=Category.INSURANCE,
                merchant="SecureLife Insurance",
            )
        )
    return rows
