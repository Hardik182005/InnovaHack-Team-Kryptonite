"""Request bodies for the §18 API.

Pydantic v2 models with `extra="forbid"`, so an unexpected field is a 422 rather
than a silently ignored typo. Money arrives as a string and is converted with
`Decimal(str(...))` at the service boundary — never through a float, which would
reintroduce the rounding errors the engines take care to avoid.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.enums import Category, Essentiality, LeakDecision, UsageStatus


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _positive_decimal(value: Any, field: str) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except Exception:
        raise ValueError("%s must be a number" % field)
    if parsed < 0:
        raise ValueError("%s cannot be negative" % field)
    return parsed


class PresignRequest(_Base):
    """§18 POST /api/uploads/presign."""

    filename: str = Field(min_length=1, max_length=255)
    content_type: Optional[str] = Field(default=None, max_length=200)
    size_bytes: int = Field(ge=0)


class CreateAnalysisRequest(_Base):
    """§18 POST /api/analyses.

    `document_password` is accepted for one request and never persisted (§22):
    it is passed by value to the extraction stage and then discarded.
    """

    upload_id: Optional[str] = None
    demo: bool = False
    document_password: Optional[str] = Field(default=None, max_length=256)
    consent_confirmed: bool = True
    delete_after_processing: bool = True
    declared_currency: Optional[str] = Field(default=None, max_length=8)
    auto_confirm: bool = False


class TransactionPatch(_Base):
    """§6.3 corrections. Every field is optional; only what is sent changes."""

    normalized_merchant: Optional[str] = Field(default=None, max_length=200)
    amount: Optional[str] = None
    direction: Optional[str] = None
    category: Optional[Category] = None
    essentiality: Optional[Essentiality] = None
    is_internal_transfer: Optional[bool] = None
    is_reimbursement: Optional[bool] = None
    excluded: Optional[bool] = None
    description: Optional[str] = Field(default=None, max_length=500)

    @field_validator("direction")
    @classmethod
    def _check_direction(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        lowered = value.lower()
        if lowered not in ("debit", "credit"):
            raise ValueError("direction must be 'debit' or 'credit'")
        return lowered

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        parsed = _positive_decimal(value, "amount")
        if parsed is None or parsed <= 0:
            raise ValueError("amount must be greater than zero")
        return str(parsed)


class BulkConfirmRequest(_Base):
    """§18 POST /api/transactions/bulk-confirm."""

    analysis_id: str
    transaction_ids: Optional[List[str]] = None
    confirm_all: bool = True


class UsageConfirmationRequest(_Base):
    """§6.9 — the answer to "have you used this in the last 30 days?"."""

    usage_status: UsageStatus
    note: Optional[str] = Field(default=None, max_length=500)


class LeakDecisionRequest(_Base):
    """§6.9 — keep / review / cancel / downgrade / renegotiate / ..."""

    decision: LeakDecision
    note: Optional[str] = Field(default=None, max_length=500)


class DraftActionRequest(_Base):
    """§6.11 — draft a cancellation, downgrade or negotiation message."""

    action_type: str = Field(default="cancel", max_length=40)
    tone: Optional[str] = Field(default=None, max_length=40)

    @field_validator("action_type")
    @classmethod
    def _check_action(cls, value: str) -> str:
        allowed = {"cancel", "downgrade", "renegotiate"}
        if value.lower() not in allowed:
            raise ValueError("action_type must be one of %s" % sorted(allowed))
        return value.lower()


class SafeSpareSettingsPatch(_Base):
    """§6.6 user safety settings."""

    user_minimum_buffer: Optional[str] = None
    buffer_percentage: Optional[str] = None
    volatility_multiplier: Optional[str] = None
    user_monthly_cap: Optional[str] = None

    @field_validator("user_minimum_buffer", "user_monthly_cap")
    @classmethod
    def _check_money(cls, value: Optional[str]) -> Optional[str]:
        parsed = _positive_decimal(value, "amount")
        return None if parsed is None else str(parsed)

    @field_validator("buffer_percentage", "volatility_multiplier")
    @classmethod
    def _check_multiplier(cls, value: Optional[str]) -> Optional[str]:
        parsed = _positive_decimal(value, "multiplier")
        if parsed is None:
            return None
        if parsed > 10:
            raise ValueError("multiplier is unreasonably large")
        return str(parsed)


class RoundUpRulesPatch(_Base):
    """§6.8 round-up configuration."""

    increment: Optional[str] = None
    monthly_cap: Optional[str] = None
    per_transaction_cap: Optional[str] = None
    excluded_categories: Optional[List[Category]] = None
    excluded_merchants: Optional[List[str]] = None
    paused: Optional[bool] = None

    @field_validator("increment")
    @classmethod
    def _check_increment(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        parsed = _positive_decimal(value, "increment")
        if parsed is None or parsed <= 0:
            raise ValueError("increment must be greater than zero")
        if parsed > 100:
            raise ValueError("increment is unreasonably large")
        return str(parsed)

    @field_validator("monthly_cap", "per_transaction_cap")
    @classmethod
    def _check_caps(cls, value: Optional[str]) -> Optional[str]:
        parsed = _positive_decimal(value, "cap")
        return None if parsed is None else str(parsed)


class GoalRequest(_Base):
    """§6.10 create a goal."""

    analysis_id: str
    name: str = Field(min_length=1, max_length=120)
    goal_type: str = Field(default="custom", max_length=40)
    target_amount: str
    target_date: Optional[str] = None
    starting_principal: str = "0"

    @field_validator("target_amount")
    @classmethod
    def _check_target(cls, value: str) -> str:
        parsed = _positive_decimal(value, "target_amount")
        if parsed is None or parsed <= 0:
            raise ValueError("target_amount must be greater than zero")
        return str(parsed)

    @field_validator("starting_principal")
    @classmethod
    def _check_principal(cls, value: str) -> str:
        parsed = _positive_decimal(value, "starting_principal")
        return str(parsed or Decimal("0"))


class GoalPatch(_Base):
    name: Optional[str] = Field(default=None, max_length=120)
    target_amount: Optional[str] = None
    target_date: Optional[str] = None
    starting_principal: Optional[str] = None

    @field_validator("target_amount", "starting_principal")
    @classmethod
    def _check_money(cls, value: Optional[str]) -> Optional[str]:
        parsed = _positive_decimal(value, "amount")
        return None if parsed is None else str(parsed)


class SimulateRequest(_Base):
    """§6.10 run a projection.

    `annual_return_rate` is an *illustrative assumption*, never a forecast, and
    is capped to keep the UI from presenting an implausible growth curve.
    """

    months: Optional[int] = Field(default=None, ge=1, le=600)
    annual_return_rate: Optional[str] = None
    include_roundups: bool = True
    include_confirmed_recovery: bool = True

    @field_validator("annual_return_rate")
    @classmethod
    def _check_rate(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            parsed = Decimal(str(value))
        except Exception:
            raise ValueError("annual_return_rate must be a number")
        if parsed < 0 or parsed > 1:
            raise ValueError("annual_return_rate must be between 0 and 1")
        return str(parsed)


class ChatRequest(_Base):
    """§6.11 AI Coach."""

    analysis_id: str
    question: str = Field(min_length=1, max_length=1000)


class VoiceRequest(_Base):
    """§6.12 voice summary."""

    analysis_id: str


class DeleteDataRequest(_Base):
    """§18 POST /api/privacy/delete-data."""

    confirm: bool = False
    analysis_id: Optional[str] = None


class SpokenExpenseRequest(_Base):
    """§ voice entry — parse one spoken phrase into a draft expense."""

    transcript: str = Field(min_length=1, max_length=500)
    language: str = Field(default="en", max_length=8)


class ConfirmSpokenExpenseRequest(_Base):
    """The user confirmed what was heard. Only then does it become a transaction."""

    analysis_id: Optional[str] = None
    transcript: str = Field(min_length=1, max_length=500)
    language: str = Field(default="en", max_length=8)
    amount: str
    description: str = Field(max_length=200)
    category: Optional[Category] = None
    direction: str = "debit"
    currency: str = Field(default="INR", max_length=8)

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, value: str) -> str:
        parsed = _positive_decimal(value, "amount")
        if parsed is None or parsed <= 0:
            raise ValueError("amount must be greater than zero")
        return str(parsed)
