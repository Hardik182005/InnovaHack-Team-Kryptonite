"""Core domain entities.

Deliberately dependency-free dataclasses rather than Pydantic models: the
deterministic engines are the financial source of truth (§3.7, §16) and must be
importable and testable without a web framework, a database, or any network.
Pydantic is used at the API boundary (`app/api`) and for strict LLM output
validation (`app/ai`), which is what spec §16 actually requires.

All money is `Decimal`. Float arithmetic on currency would make the round-up
engine wrong in exactly the direction the product claims to protect against.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from .enums import (
    Category,
    Direction,
    Essentiality,
    default_essentiality,
)

TWO_PLACES = Decimal("0.01")


def money(value) -> Decimal:
    """Coerce to a 2dp Decimal without going through binary float."""
    if isinstance(value, Decimal):
        d = value
    else:
        d = Decimal(str(value))
    return d.quantize(TWO_PLACES)


def new_id() -> str:
    """UUIDs everywhere, per §20."""
    return str(uuid.uuid4())


@dataclass
class Transaction:
    """One statement line.

    `amount` is always positive; `direction` carries the sign. Storing a signed
    amount invites the reversed debit/credit bug that §8 asks us to validate for.
    """

    date: date
    description: str
    amount: Decimal
    direction: Direction

    id: str = field(default_factory=new_id)

    # Normalization / classification (§9, §10)
    raw_merchant: Optional[str] = None
    normalized_merchant: Optional[str] = None
    merchant_method: Optional[str] = None
    merchant_confidence: float = 0.0

    category: Category = Category.UNKNOWN
    category_confidence: float = 0.0
    category_method: Optional[str] = None
    category_rule: Optional[str] = None

    essentiality: Essentiality = Essentiality.UNKNOWN

    balance: Optional[Decimal] = None
    currency: str = "USD"

    # Provenance (§8) — never silently drop a transaction, always know where it came from
    source_page: Optional[int] = None
    source_row: Optional[int] = None
    parser: Optional[str] = None
    extraction_confidence: float = 1.0
    validation_warnings: List[str] = field(default_factory=list)
    external_model_used: bool = False

    # User controls (§6.3)
    excluded: bool = False
    is_internal_transfer: bool = False
    is_reimbursement: bool = False
    user_overridden: bool = False
    reference: Optional[str] = None

    def __post_init__(self) -> None:
        self.amount = money(self.amount)
        if self.amount < 0:
            # Normalize a signed import into amount+direction rather than rejecting it.
            self.amount = -self.amount
            self.direction = (
                Direction.CREDIT if self.direction is Direction.DEBIT else Direction.DEBIT
            )
        if self.balance is not None:
            self.balance = money(self.balance)
        if self.raw_merchant is None:
            self.raw_merchant = self.description
        if self.essentiality is Essentiality.UNKNOWN and self.category is not Category.UNKNOWN:
            self.essentiality = default_essentiality(self.category)

    # -- convenience predicates -------------------------------------------------

    @property
    def is_debit(self) -> bool:
        return self.direction is Direction.DEBIT

    @property
    def is_credit(self) -> bool:
        return self.direction is Direction.CREDIT

    @property
    def is_essential(self) -> bool:
        return self.essentiality is Essentiality.ESSENTIAL

    @property
    def counts_toward_spending(self) -> bool:
        """Excluded rows, transfers and reimbursements are not spending."""
        return (
            not self.excluded
            and self.is_debit
            and not self.is_internal_transfer
            and self.category is not Category.INTERNAL_TRANSFER
        )

    @property
    def counts_toward_income(self) -> bool:
        return (
            not self.excluded
            and self.is_credit
            and not self.is_internal_transfer
            and self.category is not Category.INTERNAL_TRANSFER
        )

    def merchant_key(self) -> str:
        """Grouping key for recurrence detection (§11)."""
        return (self.normalized_merchant or self.raw_merchant or self.description or "").lower()


@dataclass
class AuditEvent:
    """§6.3 — every user correction creates an audit record."""

    entity_type: str
    entity_id: str
    action: str
    before: Optional[str] = None
    after: Optional[str] = None
    actor: str = "user"
    id: str = field(default_factory=new_id)


@dataclass
class CalculationProvenance:
    """Attached to every calculated record (§20).

    Storing the calculation version alongside the value is what lets the UI prove
    a number came from backend code and not from a model.
    """

    calculation_version: str
    method: str
    source_transaction_ids: List[str] = field(default_factory=list)
    confidence: float = 1.0
    user_overridden: bool = False
    timestamp: Optional[str] = None
