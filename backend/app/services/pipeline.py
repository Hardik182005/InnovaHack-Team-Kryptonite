"""Analysis orchestrator — the §19 state machine.

Runs the deterministic engines in order and persists every result with its
provenance. This module owns *sequencing and persistence*; it performs no
financial arithmetic of its own. Every number it stores comes from
`app/services/*`, which keeps the "LLMs never calculate" rule (§3.7) structurally
true rather than merely intended.

    UPLOADED → EXTRACTING → VALIDATING → AWAITING_REVIEW → NORMALIZING →
    CATEGORIZING → DETECTING_RECURRING → CALCULATING_SAFE_SPARE →
    GENERATING_INSIGHTS → COMPLETED | FAILED

`AWAITING_REVIEW` is a genuine pause: §6.3 requires the user to see and correct
the extraction before anything is derived from it. `auto_confirm` skips it for
the demo path.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_logger
from ..models.entities import (
    AnalysisSession,
    AnalysisStatus,
    CalculationProvenance,
    ExtractionRecord,
    LeakFindingRecord,
    PriceChangeRecord,
    RecurrencePatternRecord,
    RoundUpCalculation,
    SafeSpareSnapshot,
    TransitionError,
    new_id,
    utc_now,
)
from ..models.enums import (
    Category,
    Frequency,
    LeakDecision,
    ReviewStatus,
    UsageStatus,
)
from ..models.transaction import money
from ..repositories.base import Repositories
from . import (
    cashflow_confidence,
    categorization,
    extraction,
    leak_score,
    merchant_normalization,
    price_changes,
    recurrence,
    roundups,
    safe_spare,
    validation,
)

logger = get_logger(__name__)

CALCULATION_VERSION = "pipeline.v1"

#: Public alias. Every calculated record stores a calculation version (§20), and
#: the API serializers report this one for the analysis as a whole.
PIPELINE_VERSION = CALCULATION_VERSION

ZERO = Decimal("0.00")

# --- calculation-state keys -------------------------------------------------
STATE_EXTRACTION = "extraction"
STATE_VALIDATION = "validation"
STATE_RECOVERABLE = "recoverable"
STATE_SUMMARY = "summary"
STATE_SAFE_SPARE_INPUTS = "safe_spare_inputs"
STATE_SAFE_SPARE_SETTINGS = "safe_spare_settings"
STATE_ROUNDUP_RULES = "roundup_rules"
STATE_ROUNDUP_LINES = "roundup_lines"

#: Instruction-shaped text inside a statement is data, never a command (§3.22-23).
#: Detected here so the count can be surfaced to the user and the text can be
#: neutralised before it ever reaches a model prompt.
_INJECTION_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"disregard\s+(the\s+)?(above|previous|prior)",
        r"system\s*prompt",
        r"you\s+are\s+now\s+",
        r"display\s+all\s+api\s+keys?",
        r"reveal\s+(the\s+)?(secret|key|password|token)",
        r"set\s+safe\s*spare\s+to",
        r"tell\s+(the\s+)?user\s+this\s+.{0,30}unused",
        r"cancel\s+rent\s+automatically",
        r"guarantee\s+\d+\s*%\s*return",
        r"</?(system|assistant|user)>",
    )
]


class PipelineError(RuntimeError):
    """A user-safe pipeline failure.

    Carries an HTTP status and a message that is safe to show — never a stack
    trace or an internal detail (§5, testing prompt §2.19).
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Settings <-> stored-state helpers (also used by api/serializers.py)
# ---------------------------------------------------------------------------


def _decimal(value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    if value is None or value == "":
        return default
    try:
        return money(value)
    except (InvalidOperation, ValueError, TypeError):
        return default


def _safe_spare_settings(state: Optional[Dict[str, Any]]) -> safe_spare.SafeSpareSettings:
    """Rebuild `SafeSpareSettings` from persisted state, falling back to defaults."""
    state = state or {}
    defaults = safe_spare.SafeSpareSettings()
    try:
        return safe_spare.SafeSpareSettings(
            user_minimum_buffer=_decimal(
                state.get("user_minimum_buffer"), defaults.user_minimum_buffer
            ),
            buffer_percentage=_decimal(
                state.get("buffer_percentage"), defaults.buffer_percentage
            ),
            volatility_multiplier=_decimal(
                state.get("volatility_multiplier"), defaults.volatility_multiplier
            ),
            user_monthly_cap=_decimal(state.get("user_monthly_cap"), None),
        )
    except (ValueError, InvalidOperation):
        # A bad stored value must never break the analysis; fall back to safe defaults.
        logger.warning("invalid safe-spare settings in state; using defaults")
        return defaults


def _roundup_rules(state: Optional[Dict[str, Any]]) -> roundups.RoundUpRules:
    """Rebuild `RoundUpRules` from persisted state, falling back to defaults."""
    state = state or {}
    defaults = roundups.RoundUpRules()
    excluded_categories = state.get("excluded_categories")
    categories = defaults.excluded_categories
    if excluded_categories:
        resolved = set()
        for raw in excluded_categories:
            try:
                resolved.add(Category(raw))
            except ValueError:
                continue
        if resolved:
            categories = frozenset(resolved)
    try:
        return roundups.RoundUpRules(
            increment=_decimal(state.get("increment"), defaults.increment),
            monthly_cap=_decimal(state.get("monthly_cap"), None),
            per_transaction_cap=_decimal(state.get("per_transaction_cap"), None),
            excluded_categories=categories,
            excluded_merchants=frozenset(state.get("excluded_merchants") or ()),
            large_transaction_threshold=_decimal(
                state.get("large_transaction_threshold"),
                defaults.large_transaction_threshold,
            ),
            paused=bool(state.get("paused", False)),
        )
    except (ValueError, InvalidOperation):
        logger.warning("invalid round-up rules in state; using defaults")
        return defaults


def detect_injection(text: str) -> bool:
    """True when a description contains instruction-shaped text."""
    return any(pattern.search(text or "") for pattern in _INJECTION_PATTERNS)


def neutralize(text: str) -> str:
    """Render instruction-shaped text inert for display and prompts.

    The transaction is preserved verbatim in `raw_merchant` for the audit trail;
    this is the form that may be shown or sent onward. We never delete the row —
    §8 forbids silently dropping a transaction — and never obey it.
    """
    cleaned = text or ""
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("[flagged text removed]", cleaned)
    return cleaned


def _prov(method: str, source_ids: Optional[List[str]] = None, confidence: float = 1.0):
    return CalculationProvenance(
        calculation_version=CALCULATION_VERSION,
        method=method,
        source_transaction_ids=list(source_ids or []),
        confidence=confidence,
        timestamp=utc_now(),
    )


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


class AnalysisPipeline:
    """Drives one analysis through the §19 states.

    Every public method is idempotent: re-running a completed stage recomputes
    from stored transactions rather than duplicating them (§19 "duplicate worker
    execution is idempotent").
    """

    def __init__(
        self, repos: Repositories, settings: Any = None, password: Optional[str] = None
    ) -> None:
        self.repos = repos
        self.settings = settings
        # Held for the duration of this run only. A PDF password is never written
        # to a document record or a log — §22 forbids persisting it.
        self._password = password

    # -- public entry points -------------------------------------------------

    def run(self, analysis: AnalysisSession) -> AnalysisSession:
        """Full run from UPLOADED. Stops at AWAITING_REVIEW unless auto_confirm."""
        try:
            if analysis.status is AnalysisStatus.UPLOADED:
                self._extract(analysis)
                self._validate(analysis)
            if analysis.status is AnalysisStatus.AWAITING_REVIEW and not analysis.auto_confirm:
                self._save(analysis)
                return analysis
            return self._derive(analysis)
        except PipelineError:
            raise
        except TransitionError as exc:
            logger.warning("illegal transition: %s", exc)
            raise PipelineError(409, "INVALID_STATE", "That step cannot run right now.")
        except Exception:
            # Never leak an internal error to the user (§5).
            logger.exception("pipeline failure for analysis %s", analysis.id)
            analysis.fail(
                "PIPELINE_FAILED",
                "We could not finish analysing this statement. Please try uploading it again.",
            )
            self._save(analysis)
            raise PipelineError(
                500, "PIPELINE_FAILED", "We could not finish analysing this statement."
            )

    def confirm(self, analysis: AnalysisSession) -> AnalysisSession:
        """User confirmed the extraction (§6.3) — continue to the derived stages."""
        if analysis.status is not AnalysisStatus.AWAITING_REVIEW:
            if analysis.status is AnalysisStatus.COMPLETED:
                return analysis
            raise PipelineError(
                409, "NOT_AWAITING_REVIEW", "This analysis is not waiting for confirmation."
            )
        return self.run(analysis)

    def recalculate(self, analysis: AnalysisSession) -> AnalysisSession:
        """Re-derive everything after a user correction (§6.3).

        Transactions are read back from the repository, so the correction the
        user just made is the input — this is what makes an edit propagate to
        the dashboard, Safe Spare and round-ups.
        """
        if analysis.status is AnalysisStatus.FAILED:
            raise PipelineError(409, "ANALYSIS_FAILED", "This analysis cannot be updated.")
        if analysis.status in (AnalysisStatus.COMPLETED, AnalysisStatus.AWAITING_REVIEW):
            try:
                analysis.transition_to(AnalysisStatus.NORMALIZING)
            except TransitionError:
                raise PipelineError(
                    409, "INVALID_STATE", "That step cannot run right now."
                )
            return self._derive(analysis, already_normalizing=True)
        raise PipelineError(409, "ANALYSIS_IN_PROGRESS", "This analysis is still processing.")

    # -- stages --------------------------------------------------------------

    def _extract(self, analysis: AnalysisSession) -> None:
        analysis.transition_to(AnalysisStatus.EXTRACTING)
        self._save(analysis)

        document = self.repos.documents.get(analysis.document_id or "")
        if document is None:
            raise PipelineError(404, "DOCUMENT_MISSING", "The uploaded file is no longer available.")
        content = self.repos.documents.get_content(document.id)
        if not content:
            raise PipelineError(400, "EMPTY_FILE", "That file appears to be empty.")

        result = extraction.extract(
            content,
            filename=getattr(document, "filename", "") or "",
            password=self._password,
        )

        if not result.transactions:
            reason = (
                "We could not read any transactions from that file. If it is a scanned "
                "statement, try a digital PDF or a CSV export."
            )
            analysis.fail("NO_TRANSACTIONS", reason)
            self._save(analysis)
            raise PipelineError(422, "NO_TRANSACTIONS", reason)

        kept, removed = extraction.deduplicate(result.transactions)

        # Neutralise instruction-shaped descriptions before anything else sees them.
        injections = 0
        for txn in kept:
            if detect_injection(txn.description):
                injections += 1
                txn.raw_merchant = txn.description
                txn.description = neutralize(txn.description)
                if "prompt_like_text_neutralized" not in txn.validation_warnings:
                    txn.validation_warnings.append("prompt_like_text_neutralized")

        analysis.currency = result.currency or analysis.currency
        self.repos.transactions.replace_all(analysis.id, kept)

        record = ExtractionRecord(
            analysis_id=analysis.id,
            parser=result.parser,
            currency=result.currency,
            rows_seen=result.rows_seen,
            rows_extracted=len(kept),
            rows_skipped=[{"row": r, "reason": why} for r, why in result.rows_skipped],
            duplicates_removed=len(removed),
            warnings=list(result.warnings),
            date_range_start=result.date_range[0] if result.date_range else None,
            date_range_end=result.date_range[1] if result.date_range else None,
            injection_attempts_neutralized=injections,
            prov=_prov("extraction:" + result.parser, [t.id for t in kept[:50]]),
        )
        self.repos.calculations.set_state(
            analysis.id, STATE_EXTRACTION, _extraction_state(record)
        )
        if injections:
            logger.info(
                "neutralized %d instruction-like transaction descriptions", injections
            )

    def _validate(self, analysis: AnalysisSession) -> None:
        analysis.transition_to(AnalysisStatus.VALIDATING)
        self._save(analysis)

        txns = self.repos.transactions.list_for_analysis(analysis.id)
        report = validation.validate(txns)
        for txn in txns:
            self.repos.transactions.save(analysis.id, txn)

        self.repos.calculations.set_state(
            analysis.id,
            STATE_VALIDATION,
            {
                "statement_warnings": list(report.statement_warnings),
                "duplicate_groups": len(report.duplicate_groups),
                "transfer_pairs": len(report.transfer_pairs),
                "balance_reconciles": report.balance_reconciles,
                "opening_balance": str(report.opening_balance)
                if report.opening_balance is not None
                else None,
                "closing_balance": str(report.closing_balance)
                if report.closing_balance is not None
                else None,
                "currencies_seen": list(report.currencies_seen),
                "needs_review_count": report.needs_review_count,
            },
        )
        analysis.transition_to(AnalysisStatus.AWAITING_REVIEW)
        self._save(analysis)

    def _derive(
        self, analysis: AnalysisSession, already_normalizing: bool = False
    ) -> AnalysisSession:
        """Stages that depend on confirmed transactions."""
        if not already_normalizing:
            analysis.transition_to(AnalysisStatus.NORMALIZING)
        self._save(analysis)

        txns = self.repos.transactions.list_for_analysis(analysis.id)
        if not txns:
            raise PipelineError(422, "NO_TRANSACTIONS", "There are no transactions to analyse.")

        # --- normalize (§9) — user overrides win --------------------------
        resolutions = merchant_normalization.normalize_all(
            [t.raw_merchant or t.description for t in txns]
        )
        for txn, resolution in zip(txns, resolutions):
            if txn.user_overridden and txn.normalized_merchant:
                continue
            txn.normalized_merchant = resolution.normalized_merchant
            txn.merchant_method = resolution.method
            txn.merchant_confidence = resolution.confidence

        # --- categorize (§10) ---------------------------------------------
        analysis.transition_to(AnalysisStatus.CATEGORIZING)
        self._save(analysis)
        categorization.classify_transactions(txns)
        for txn in txns:
            self.repos.transactions.save(analysis.id, txn)

        # --- recurrence, price changes, leaks (§11, §12, §13) -------------
        analysis.transition_to(AnalysisStatus.DETECTING_RECURRING)
        self._save(analysis)
        patterns = recurrence.detect_recurring(txns)
        changes = self._price_changes(patterns, txns)
        findings, recoverable = self._leaks(analysis, patterns, changes, txns)

        self._persist_patterns(analysis, patterns)
        change_ids = self._persist_price_changes(analysis, changes)
        self._persist_leaks(analysis, findings, change_ids)
        self.repos.calculations.set_state(
            analysis.id, STATE_RECOVERABLE, {k: str(v) for k, v in recoverable.items()}
        )

        # --- safe spare (§6.6) --------------------------------------------
        analysis.transition_to(AnalysisStatus.CALCULATING_SAFE_SPARE)
        self._save(analysis)
        snapshot, roundup_result = self._safe_spare_and_roundups(analysis, txns, patterns)

        # --- insights (§6.5) ----------------------------------------------
        analysis.transition_to(AnalysisStatus.GENERATING_INSIGHTS)
        self._save(analysis)
        self.repos.calculations.set_state(
            analysis.id,
            STATE_SUMMARY,
            _summary_state(txns, snapshot, roundup_result, recoverable),
        )

        analysis.transition_to(AnalysisStatus.COMPLETED)
        analysis.error_code = None
        analysis.error_message = None
        self._save(analysis)
        return analysis

    # -- stage helpers -------------------------------------------------------

    def _price_changes(self, patterns, txns) -> List[Any]:
        history: Dict[str, List[Tuple[date, Decimal, str]]] = {}
        for txn in txns:
            if txn.is_debit and not txn.excluded:
                key = txn.normalized_merchant or txn.description
                history.setdefault(key, []).append((txn.date, txn.amount, txn.id))
        return price_changes.detect_price_changes(patterns, history)

    def _leaks(self, analysis, patterns, changes, txns):
        """Score leaks, replaying any usage confirmations the user already gave.

        Replaying them is what makes a correction non-destructive: a user who
        confirmed "not used" keeps that answer when an unrelated edit triggers a
        recalculation.
        """
        usage: Dict[str, UsageStatus] = {}
        decisions: Dict[str, LeakDecision] = {}
        for existing in self.repos.calculations.get_leaks(analysis.id):
            if existing.usage_status is not UsageStatus.UNKNOWN:
                usage[existing.merchant] = existing.usage_status
            if existing.decision is not None:
                decisions[existing.merchant] = existing.decision

        months = max(1, len({(t.date.year, t.date.month) for t in txns}))
        discretionary = sum(
            (t.amount for t in txns if t.counts_toward_spending and not t.is_essential),
            ZERO,
        )
        findings = leak_score.score_leaks(
            patterns,
            changes,
            usage_statuses=usage,
            monthly_discretionary_spend=money(discretionary / Decimal(months)),
        )
        for finding in findings:
            if finding.merchant in decisions:
                setattr(finding, "_decision", decisions[finding.merchant])

        totals = leak_score.recoverable_totals(findings)
        totals["confirmed_from_decisions"] = leak_score.confirmed_recoverable_from_decisions(
            findings, decisions
        )
        return findings, totals

    def _safe_spare_and_roundups(self, analysis, txns, patterns):
        settings_state = self.repos.calculations.get_state(
            analysis.id, STATE_SAFE_SPARE_SETTINGS, {}
        )
        settings = _safe_spare_settings(settings_state)

        # Upcoming essentials come from real recurrence due-dates, not a monthly
        # average — this is what lets SafeSpare say "rent is due before payday".
        base_inputs = safe_spare.build_inputs(txns)
        as_of = max(t.date for t in txns)
        upcoming = None
        if base_inputs.next_income_date is not None:
            upcoming = recurrence.upcoming_essential_outflows(
                patterns, as_of, base_inputs.next_income_date
            )
        inputs = safe_spare.build_inputs(txns, as_of=as_of, upcoming_essentials=upcoming)
        result = safe_spare.compute_safe_spare(inputs, settings)

        # Only user-CONFIRMED recovery may raise the contribution (§25.10).
        recoverable = self.repos.calculations.get_state(analysis.id, STATE_RECOVERABLE, {}) or {}
        confirmed = _decimal(recoverable.get("confirmed_from_decisions"), ZERO) or ZERO
        if confirmed > 0:
            result = safe_spare.apply_confirmed_recovery(result, confirmed)

        confidence = cashflow_confidence.compute(
            txns,
            latest_balance=result.latest_verified_balance,
            balance_is_estimated=result.balance_is_estimated,
        )

        snapshot = SafeSpareSnapshot(
            analysis_id=analysis.id,
            latest_verified_balance=result.latest_verified_balance,
            balance_is_estimated=result.balance_is_estimated,
            expected_income=result.expected_income,
            upcoming_essential_outflows=result.upcoming_essential_outflows,
            projected_balance_before_next_income=result.projected_balance_before_next_income,
            safety_buffer=result.safety_buffer,
            volatility_reserve=result.volatility_reserve,
            safe_spare_now=result.safe_spare_now,
            safe_monthly_contribution=result.safe_monthly_contribution,
            confirmed_recovery_included=confirmed,
            limiting_factor=result.limiting_factor,
            reason=result.reason,
            missing_inputs=list(result.missing_inputs),
            next_income_date=result.next_income_date,
            cashflow_confidence=confidence.score,
            cashflow_components={c.name: c.value for c in confidence.components},
            prov=_prov("safe_spare.v1", result.source_transaction_ids, result.confidence),
        )
        self.repos.calculations.set_safe_spare(analysis.id, snapshot)
        self.repos.calculations.set_state(
            analysis.id, STATE_SAFE_SPARE_INPUTS, _inputs_state(inputs)
        )

        rules_state = self.repos.calculations.get_state(analysis.id, STATE_ROUNDUP_RULES, {})
        rules = _roundup_rules(rules_state)
        roundup_result = roundups.calculate_roundups(
            txns,
            rules=rules,
            safe_monthly_contribution=result.safe_monthly_contribution,
        )
        self.repos.calculations.set_roundups(
            analysis.id,
            RoundUpCalculation(
                analysis_id=analysis.id,
                historical_round_up_total=roundup_result.historical_round_up_total,
                allowed_round_up_total=roundup_result.allowed_round_up_total,
                limiting_factor=roundup_result.limiting_factor,
                explanation=roundup_result.explanation,
                eligible_count=roundup_result.eligible_count,
                excluded_count=roundup_result.excluded_count,
                per_merchant=roundups.group_by_merchant(roundup_result),
                exclusion_reasons=roundups.excluded_reasons_summary(roundup_result),
                prov=_prov("roundups.v1", roundup_result.source_transaction_ids),
            ),
        )
        self.repos.calculations.set_state(
            analysis.id,
            STATE_ROUNDUP_LINES,
            [
                {
                    "transaction_id": line.transaction_id,
                    "merchant": line.merchant,
                    "amount": str(line.amount),
                    "round_up": str(line.round_up),
                    "eligible": line.eligible,
                    "reason": line.reason,
                }
                for line in roundup_result.lines
            ],
        )
        return snapshot, roundup_result

    # -- persistence ---------------------------------------------------------

    def _persist_patterns(self, analysis, patterns) -> None:
        self.repos.calculations.set_patterns(
            analysis.id,
            [
                RecurrencePatternRecord(
                    analysis_id=analysis.id,
                    merchant=p.merchant,
                    category=p.category,
                    frequency=p.frequency,
                    occurrences=p.occurrences,
                    median_amount=p.median_amount,
                    latest_amount=p.latest_amount,
                    monthly_equivalent=p.monthly_equivalent,
                    first_date=p.first_date,
                    latest_date=p.latest_date,
                    next_expected_date=p.next_expected_date,
                    status=p.status,
                    is_essential=p.is_essential,
                    amount_varies=p.amount_varies,
                    components={
                        "interval_regularity": p.interval_regularity,
                        "merchant_similarity": p.merchant_similarity,
                        "amount_stability": p.amount_stability,
                        "occurrence_strength": p.occurrence_strength,
                        "confidence": p.confidence,
                    },
                    prov=_prov("recurrence.v1", p.transaction_ids, p.confidence / 100.0),
                )
                for p in patterns
            ],
        )

    def _persist_price_changes(self, analysis, changes) -> Dict[str, str]:
        records = [
            PriceChangeRecord(
                analysis_id=analysis.id,
                merchant=c.merchant,
                previous_amount=c.previous_amount,
                current_amount=c.current_amount,
                absolute_increase=c.absolute_increase,
                percentage_increase=c.percentage_increase,
                annualized_increase=c.annualized_increase,
                first_date_of_new_price=c.first_date_of_new_price,
                prov=_prov("price_changes.v1", c.evidence_transaction_ids, c.confidence),
            )
            for c in changes
        ]
        self.repos.calculations.set_price_changes(analysis.id, records)
        return {r.merchant: r.id for r in records}

    def _persist_leaks(self, analysis, findings, change_ids: Dict[str, str]) -> None:
        """Persist leak findings with IDs stable across recomputation.

        The ID is derived from the merchant so a usage confirmation or decision
        the user made against a finding is not orphaned when a correction
        triggers a recalculation.
        """
        existing = {r.merchant: r for r in self.repos.calculations.get_leaks(analysis.id)}
        records = []
        for f in findings:
            prior = existing.get(f.merchant)
            records.append(
                LeakFindingRecord(
                    id=prior.id if prior else new_id(),
                    analysis_id=analysis.id,
                    merchant=f.merchant,
                    category=f.category,
                    frequency=f.frequency,
                    monthly_cost=f.monthly_cost,
                    annual_cost=f.annual_cost,
                    leak_score=f.leak_score,
                    band=f.band,
                    usage_status=f.usage_status,
                    review_status=f.review_status,
                    recommended_actions=list(f.recommended_actions),
                    components={
                        "price_hike_severity": f.price_hike_severity,
                        "duplicate_probability": f.duplicate_probability,
                        "cost_burden": f.cost_burden,
                        "recurrence_commitment": f.recurrence_commitment,
                        "confirmed_non_usage": f.confirmed_non_usage,
                    },
                    duplicate_group=f.duplicate_group,
                    price_change_id=change_ids.get(f.merchant),
                    explanation=f.explanation,
                    protected=f.protected,
                    decision=prior.decision if prior else None,
                    prov=_prov("leak_score.v1", f.evidence_transaction_ids),
                )
            )
        self.repos.calculations.set_leaks(analysis.id, records)

    def _save(self, analysis: AnalysisSession) -> None:
        analysis.updated_at = utc_now()
        self.repos.analyses.put(analysis)


# ---------------------------------------------------------------------------
# State serialisation helpers
# ---------------------------------------------------------------------------


def _extraction_state(record: ExtractionRecord) -> Dict[str, Any]:
    return {
        "parser": record.parser,
        "currency": record.currency,
        "rows_seen": record.rows_seen,
        "rows_extracted": record.rows_extracted,
        "rows_skipped": record.rows_skipped,
        "duplicates_removed": record.duplicates_removed,
        "warnings": record.warnings,
        "date_range_start": record.date_range_start.isoformat()
        if record.date_range_start
        else None,
        "date_range_end": record.date_range_end.isoformat()
        if record.date_range_end
        else None,
        "injection_attempts_neutralized": record.injection_attempts_neutralized,
    }


def _inputs_state(inputs: safe_spare.SafeSpareInputs) -> Dict[str, Any]:
    return {
        "latest_verified_balance": str(inputs.latest_verified_balance)
        if inputs.latest_verified_balance is not None
        else None,
        "balance_is_estimated": inputs.balance_is_estimated,
        "expected_income_before_next_income": str(
            inputs.expected_income_before_next_income
        ),
        "expected_essential_outflows_before_next_income": str(
            inputs.expected_essential_outflows_before_next_income
        ),
        "average_monthly_essential_spending": str(
            inputs.average_monthly_essential_spending
        ),
        "recent_monthly_outflows": [str(v) for v in inputs.recent_monthly_outflows],
        "calculated_monthly_surplus": str(inputs.calculated_monthly_surplus),
        "next_income_date": inputs.next_income_date.isoformat()
        if inputs.next_income_date
        else None,
        "missing_inputs": list(inputs.missing_inputs),
    }


def _summary_state(txns, snapshot, roundup_result, recoverable) -> Dict[str, Any]:
    """Dashboard aggregates (§6.4). Every figure is summed from transactions."""
    income = sum((t.amount for t in txns if t.counts_toward_income), ZERO)
    spending = sum((t.amount for t in txns if t.counts_toward_spending), ZERO)
    essential = sum(
        (t.amount for t in txns if t.counts_toward_spending and t.is_essential), ZERO
    )
    months = max(1, len({(t.date.year, t.date.month) for t in txns}))
    return {
        "transaction_count": len(txns),
        "months_covered": months,
        "total_income": str(money(income)),
        "total_spending": str(money(spending)),
        "essential_spending": str(money(essential)),
        "discretionary_spending": str(money(spending - essential)),
        "average_monthly_surplus": str(money((income - spending) / Decimal(months))),
        "potential_round_ups": str(roundup_result.historical_round_up_total),
        "allowed_round_ups": str(roundup_result.allowed_round_up_total),
        "safe_spare_now": str(snapshot.safe_spare_now),
        "safe_monthly_contribution": str(snapshot.safe_monthly_contribution),
        "cashflow_confidence": snapshot.cashflow_confidence,
        "potential_recoverable": str(recoverable.get("potential_recoverable", ZERO)),
        "user_confirmed_recoverable": str(
            recoverable.get("confirmed_from_decisions", ZERO)
        ),
    }
