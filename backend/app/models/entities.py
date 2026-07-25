"""Persisted entities — spec §20.

`models/transaction.py` already owns `Transaction`, `AuditEvent` and
`CalculationProvenance`; this module adds the remaining §20 entities and the
analysis state machine from §19. Nothing here is re-imported by the
deterministic engines — this is the storage layer's vocabulary, kept separate so
the financial core stays framework- and persistence-free.

Every *calculated* record carries `CalculationProvenance` (calculation version,
source transaction IDs, timestamp, confidence, method, user-override status), so
any number the UI shows can be traced back to the code and the rows that
produced it. Dataclasses rather than Pydantic for the same reason as
`transaction.py`: the domain must not depend on a web framework.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from .enums import (
    Category,
    Frequency,
    LeakDecision,
    ReviewStatus,
    UsageStatus,
)
from .transaction import CalculationProvenance, new_id

ZERO = Decimal("0.00")


def utc_now() -> str:
    """ISO-8601 UTC timestamp. Every record is stamped with one (§20)."""
    return datetime.now(timezone.utc).isoformat()


def provenance(
    calculation_version: str,
    method: str,
    source_transaction_ids: Optional[List[str]] = None,
    confidence: float = 1.0,
    user_overridden: bool = False,
) -> CalculationProvenance:
    """Build a fully-populated provenance stamp. §20 requires all six fields."""
    return CalculationProvenance(
        calculation_version=calculation_version,
        method=method,
        source_transaction_ids=list(source_transaction_ids or []),
        confidence=confidence,
        user_overridden=user_overridden,
        timestamp=utc_now(),
    )


class AnalysisStatus(str, Enum):
    """The §19 state machine, in order. `ORDER` below drives progress reporting."""

    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    VALIDATING = "VALIDATING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    NORMALIZING = "NORMALIZING"
    CATEGORIZING = "CATEGORIZING"
    DETECTING_RECURRING = "DETECTING_RECURRING"
    CALCULATING_SAFE_SPARE = "CALCULATING_SAFE_SPARE"
    GENERATING_INSIGHTS = "GENERATING_INSIGHTS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


#: Ordered pipeline states. FAILED is terminal and deliberately outside the order.
STATUS_ORDER: List[AnalysisStatus] = [
    AnalysisStatus.UPLOADED,
    AnalysisStatus.EXTRACTING,
    AnalysisStatus.VALIDATING,
    AnalysisStatus.AWAITING_REVIEW,
    AnalysisStatus.NORMALIZING,
    AnalysisStatus.CATEGORIZING,
    AnalysisStatus.DETECTING_RECURRING,
    AnalysisStatus.CALCULATING_SAFE_SPARE,
    AnalysisStatus.GENERATING_INSIGHTS,
    AnalysisStatus.COMPLETED,
]

#: Human-facing stage labels for the progress UI (§6.2 processing stages).
STATUS_LABELS: Dict[AnalysisStatus, str] = {
    AnalysisStatus.UPLOADED: "Secure upload complete",
    AnalysisStatus.EXTRACTING: "Extracting text and transactions",
    AnalysisStatus.VALIDATING: "Validating transactions",
    AnalysisStatus.AWAITING_REVIEW: "Waiting for you to confirm the extraction",
    AnalysisStatus.NORMALIZING: "Normalizing merchants",
    AnalysisStatus.CATEGORIZING: "Categorizing spending",
    AnalysisStatus.DETECTING_RECURRING: "Detecting recurring payments",
    AnalysisStatus.CALCULATING_SAFE_SPARE: "Calculating your Safe Spare amount",
    AnalysisStatus.GENERATING_INSIGHTS: "Generating insights",
    AnalysisStatus.COMPLETED: "Analysis complete",
    AnalysisStatus.FAILED: "Analysis failed",
}

#: Allowed transitions (§19). Enforced by `AnalysisSession.transition_to`, so an
#: out-of-order write is a programming error rather than a silent corruption.
ALLOWED_TRANSITIONS: Dict[AnalysisStatus, List[AnalysisStatus]] = {
    AnalysisStatus.UPLOADED: [AnalysisStatus.EXTRACTING, AnalysisStatus.FAILED],
    AnalysisStatus.EXTRACTING: [AnalysisStatus.VALIDATING, AnalysisStatus.FAILED],
    AnalysisStatus.VALIDATING: [AnalysisStatus.AWAITING_REVIEW, AnalysisStatus.FAILED],
    AnalysisStatus.AWAITING_REVIEW: [AnalysisStatus.NORMALIZING, AnalysisStatus.FAILED],
    AnalysisStatus.NORMALIZING: [AnalysisStatus.CATEGORIZING, AnalysisStatus.FAILED],
    AnalysisStatus.CATEGORIZING: [AnalysisStatus.DETECTING_RECURRING, AnalysisStatus.FAILED],
    AnalysisStatus.DETECTING_RECURRING: [
        AnalysisStatus.CALCULATING_SAFE_SPARE,
        AnalysisStatus.FAILED,
    ],
    AnalysisStatus.CALCULATING_SAFE_SPARE: [
        AnalysisStatus.GENERATING_INSIGHTS,
        AnalysisStatus.FAILED,
    ],
    AnalysisStatus.GENERATING_INSIGHTS: [AnalysisStatus.COMPLETED, AnalysisStatus.FAILED],
    # A correction re-runs the derived stages, so COMPLETED may re-enter the loop.
    AnalysisStatus.COMPLETED: [AnalysisStatus.NORMALIZING, AnalysisStatus.FAILED],
    AnalysisStatus.FAILED: [],
}


class TransitionError(RuntimeError):
    """Raised on an illegal state-machine transition (§19)."""


@dataclass
class User:
    id: str = field(default_factory=new_id)
    session_key: str = "anonymous"
    created_at: str = field(default_factory=utc_now)
    display_name: Optional[str] = None


@dataclass
class UploadedDocument:
    """A file the user uploaded. Bytes live in the document repository, never here."""

    id: str = field(default_factory=new_id)
    user_id: str = ""
    filename: str = ""
    content_type: str = ""
    size_bytes: int = 0
    object_key: str = ""
    checksum: Optional[str] = None
    uploaded_at: str = field(default_factory=utc_now)
    expires_at: Optional[str] = None
    delete_after_processing: bool = True
    consent_given: bool = False
    is_demo: bool = False
    password_protected: bool = False


@dataclass
class ExtractionRecord:
    """Outcome of the extraction pass (§7, §8) — a calculated record (§20)."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    parser: str = ""
    currency: str = "USD"
    rows_seen: int = 0
    rows_extracted: int = 0
    rows_skipped: List[Dict[str, Any]] = field(default_factory=list)
    duplicates_removed: int = 0
    warnings: List[str] = field(default_factory=list)
    statement_warnings: List[str] = field(default_factory=list)
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None
    balance_reconciles: Optional[bool] = None
    injection_attempts_neutralized: int = 0
    prov: Optional[CalculationProvenance] = None


@dataclass
class AnalysisSession:
    """One end-to-end analysis (§19, §20)."""

    id: str = field(default_factory=new_id)
    user_id: str = ""
    document_id: Optional[str] = None
    status: AnalysisStatus = AnalysisStatus.UPLOADED
    stage_message: str = STATUS_LABELS[AnalysisStatus.UPLOADED]
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    completed_at: Optional[str] = None
    idempotency_key: Optional[str] = None
    auto_confirm: bool = False
    delete_after_processing: bool = True
    currency: str = "USD"
    history: List[Dict[str, str]] = field(default_factory=list)
    calculation_version: str = "pipeline.v1"

    @property
    def progress_percent(self) -> int:
        """0-100 for the progress bar (§19 "the frontend must display progress")."""
        if self.status is AnalysisStatus.FAILED:
            return 100
        try:
            index = STATUS_ORDER.index(self.status)
        except ValueError:  # pragma: no cover - unreachable for known states
            return 0
        return int(round(index / (len(STATUS_ORDER) - 1) * 100))

    @property
    def is_terminal(self) -> bool:
        return self.status in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED)

    def transition_to(self, status: AnalysisStatus, message: Optional[str] = None) -> None:
        if status is not self.status and status not in ALLOWED_TRANSITIONS.get(self.status, []):
            raise TransitionError(
                "illegal transition %s -> %s" % (self.status.value, status.value)
            )
        self.status = status
        self.stage_message = message or STATUS_LABELS.get(status, status.value)
        self.updated_at = utc_now()
        self.history.append({"status": status.value, "at": self.updated_at})
        if status is AnalysisStatus.COMPLETED:
            self.completed_at = self.updated_at

    def fail(self, code: str, message: str) -> None:
        """Terminal failure. `message` is a safe, user-facing string (§5)."""
        self.status = AnalysisStatus.FAILED
        self.error_code = code
        self.error_message = message
        self.stage_message = STATUS_LABELS[AnalysisStatus.FAILED]
        self.updated_at = utc_now()
        self.history.append({"status": self.status.value, "at": self.updated_at})


@dataclass
class MerchantAlias:
    """User- or system-supplied mapping from a raw string to a merchant (§9)."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    raw_pattern: str = ""
    normalized_merchant: str = ""
    method: str = "user_override"
    confidence: float = 1.0
    user_overridden: bool = True
    created_at: str = field(default_factory=utc_now)


@dataclass
class CategoryOverride:
    """A user's category correction (§6.3). Always wins over the classifier."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    transaction_id: str = ""
    category: Category = Category.UNKNOWN
    reason: Optional[str] = None
    created_at: str = field(default_factory=utc_now)


@dataclass
class RecurrencePatternRecord:
    """Persisted form of `services.recurrence.RecurrencePattern` (§11)."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    merchant: str = ""
    category: Category = Category.UNKNOWN
    frequency: Frequency = Frequency.MONTHLY
    occurrences: int = 0
    median_amount: Decimal = ZERO
    latest_amount: Decimal = ZERO
    monthly_equivalent: Decimal = ZERO
    first_date: Optional[date] = None
    latest_date: Optional[date] = None
    next_expected_date: Optional[date] = None
    status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    is_essential: bool = False
    amount_varies: bool = False
    components: Dict[str, float] = field(default_factory=dict)
    prov: Optional[CalculationProvenance] = None


@dataclass
class PriceChangeRecord:
    """Persisted form of `services.price_changes.PriceChange` (§12)."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    merchant: str = ""
    previous_amount: Decimal = ZERO
    current_amount: Decimal = ZERO
    absolute_increase: Decimal = ZERO
    percentage_increase: Decimal = ZERO
    annualized_increase: Decimal = ZERO
    first_date_of_new_price: Optional[date] = None
    prov: Optional[CalculationProvenance] = None


@dataclass
class LeakFindingRecord:
    """Persisted form of `services.leak_score.LeakFinding` (§13).

    The ID is stable across recomputation (keyed on merchant) so that a usage
    confirmation or decision made by the user is not orphaned when a correction
    triggers a recalculation.
    """

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    merchant: str = ""
    category: Category = Category.UNKNOWN
    frequency: Frequency = Frequency.MONTHLY
    monthly_cost: Decimal = ZERO
    annual_cost: Decimal = ZERO
    leak_score: int = 0
    band: str = "low_concern"
    usage_status: UsageStatus = UsageStatus.UNKNOWN
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    recommended_actions: List[LeakDecision] = field(default_factory=list)
    components: Dict[str, float] = field(default_factory=dict)
    duplicate_group: Optional[str] = None
    price_change_id: Optional[str] = None
    explanation: str = ""
    protected: bool = False
    decision: Optional[LeakDecision] = None
    prov: Optional[CalculationProvenance] = None


@dataclass
class UsageConfirmation:
    """The user's answer to "have you used this in the last 30 days?" (§6.9)."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    leak_id: str = ""
    merchant: str = ""
    usage_status: UsageStatus = UsageStatus.UNKNOWN
    note: Optional[str] = None
    created_at: str = field(default_factory=utc_now)


@dataclass
class ActionDecision:
    """An explicit user decision on a leak (§6.9). Never executed (§3.9, §25.20)."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    leak_id: str = ""
    merchant: str = ""
    decision: LeakDecision = LeakDecision.REVIEW
    monthly_recovery: Decimal = ZERO
    executed: bool = False  # Always False. SafeSpare never performs the action.
    created_at: str = field(default_factory=utc_now)


@dataclass
class SafeSpareSnapshot:
    """Persisted Safe Spare result (§6.6) with full provenance (§20)."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    latest_verified_balance: Decimal = ZERO
    balance_is_estimated: bool = False
    expected_income: Decimal = ZERO
    upcoming_essential_outflows: Decimal = ZERO
    projected_balance_before_next_income: Decimal = ZERO
    safety_buffer: Decimal = ZERO
    volatility_reserve: Decimal = ZERO
    safe_spare_now: Decimal = ZERO
    safe_monthly_contribution: Decimal = ZERO
    confirmed_recovery_included: Decimal = ZERO
    limiting_factor: str = "none"
    reason: str = ""
    missing_inputs: List[str] = field(default_factory=list)
    next_income_date: Optional[date] = None
    cashflow_confidence: int = 0
    cashflow_components: Dict[str, float] = field(default_factory=dict)
    prov: Optional[CalculationProvenance] = None


@dataclass
class RoundUpRuleRecord:
    """User round-up configuration (§6.8). Every field maps to a UI control."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    increment: Decimal = Decimal("1.00")
    monthly_cap: Optional[Decimal] = None
    per_transaction_cap: Optional[Decimal] = None
    excluded_categories: List[Category] = field(default_factory=list)
    excluded_merchants: List[str] = field(default_factory=list)
    large_transaction_threshold: Decimal = Decimal("2000.00")
    paused: bool = False
    user_overridden: bool = False
    updated_at: str = field(default_factory=utc_now)


@dataclass
class RoundUpCalculation:
    """Persisted round-up result (§6.8)."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    historical_round_up_total: Decimal = ZERO
    allowed_round_up_total: Decimal = ZERO
    limiting_factor: str = "none"
    explanation: str = ""
    eligible_count: int = 0
    excluded_count: int = 0
    per_merchant: Dict[str, Decimal] = field(default_factory=dict)
    exclusion_reasons: Dict[str, int] = field(default_factory=dict)
    prov: Optional[CalculationProvenance] = None


@dataclass
class FinancialGoal:
    """§6.10 goal. `goal_type` is free-form to allow "custom goal"."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    user_id: str = ""
    name: str = ""
    goal_type: str = "custom"
    target_amount: Decimal = ZERO
    target_date: Optional[date] = None
    months: int = 12
    starting_principal: Decimal = ZERO
    annual_return_rate: Decimal = Decimal("0.07")
    include_roundups: bool = True
    include_confirmed_recovery: bool = True
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class Simulation:
    """A stored projection run (§6.10). Illustrative only — never executed."""

    id: str = field(default_factory=new_id)
    goal_id: str = ""
    analysis_id: str = ""
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
    scenarios: List[Dict[str, Any]] = field(default_factory=list)
    disclaimer: str = ""
    created_at: str = field(default_factory=utc_now)
    prov: Optional[CalculationProvenance] = None


@dataclass
class AIInsight:
    """A phrased insight (§6.11).

    `values_are_backend_verified` is always True: an insight is only stored after
    `ai.validators` has confirmed every number in it came from backend state. The
    `source` field records whether the wording came from a model or from a
    deterministic template, which is what makes provider-outage behaviour visible
    to the UI (§3.21).
    """

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    insight_type: str = "summary"
    title: str = ""
    explanation: str = ""
    suggested_action: Optional[str] = None
    evidence_transaction_ids: List[str] = field(default_factory=list)
    confidence: float = 1.0
    review_status: ReviewStatus = ReviewStatus.CONFIRMED
    source: str = "deterministic_template"
    model: Optional[str] = None
    values_are_backend_verified: bool = True
    created_at: str = field(default_factory=utc_now)
    prov: Optional[CalculationProvenance] = None


@dataclass
class VoiceAsset:
    """A generated voice summary (§6.12). Transcript is authoritative."""

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    transcript: str = ""
    audio_base64: Optional[str] = None
    content_type: Optional[str] = None
    provider: str = "unavailable"
    model: Optional[str] = None
    available: bool = False
    fallback_reason: Optional[str] = None
    created_at: str = field(default_factory=utc_now)


@dataclass
class AuditRecord:
    """§6.3 / §20 audit trail entry.

    Distinct from `models.transaction.AuditEvent`, which the engines use for
    in-memory correction tracking; this is the persisted, analysis-scoped form.
    """

    id: str = field(default_factory=new_id)
    analysis_id: str = ""
    user_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    action: str = ""
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    created_at: str = field(default_factory=utc_now)


@dataclass
class UploadTicket:
    """A presigned-upload grant (§18 `POST /api/uploads/presign`, §22).

    In AWS this is an S3 presigned PUT; the local implementation keeps the same
    shape (randomized object key, expiry, size ceiling) so swapping the storage
    backend does not change the API contract.
    """

    id: str = field(default_factory=new_id)
    user_id: str = ""
    filename: str = ""
    content_type: str = ""
    object_key: str = ""
    upload_url: str = ""
    method: str = "PUT"
    max_bytes: int = 0
    expires_at: str = ""
    created_at: str = field(default_factory=utc_now)
    consumed: bool = False


def random_object_key(filename: str) -> str:
    """Randomized, non-guessable storage key (§22 "randomized object keys")."""
    suffix = ""
    if "." in filename:
        candidate = filename.rsplit(".", 1)[-1].lower()
        if candidate.isalnum() and len(candidate) <= 5:
            suffix = "." + candidate
    return "uploads/%s/%s%s" % (
        datetime.now(timezone.utc).strftime("%Y/%m/%d"),
        uuid.uuid4().hex,
        suffix,
    )
