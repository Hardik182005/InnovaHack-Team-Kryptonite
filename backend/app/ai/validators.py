"""Output guardrails — spec §16 and §25.

The backend is the source of truth. Every model response passes through here and
is **rejected**, never repaired, when it fails any check. Repairing would mean
the application had silently accepted a model's version of a number.

§16 rejection triggers, each mapped to a constant below:

  amounts do not match backend context .... AMOUNT_MISMATCH
  merchant is unsupported ................. UNSUPPORTED_MERCHANT
  percentages differ from calculations .... PERCENTAGE_MISMATCH
  transaction IDs do not exist ............ UNKNOWN_TRANSACTION_ID
  unused status is unsupported ............ UNSUPPORTED_UNUSED_STATUS
  returns are guaranteed .................. GUARANTEED_RETURN
  specific investments recommended ........ SPECIFIC_SECURITY
  essentials recommended for cancellation . ESSENTIAL_CANCELLATION
  PII is exposed .......................... PII_EXPOSED
  schema fields are absent ................ SCHEMA_INVALID

Two additional triggers are not in §16's list but follow from §3.9 and §3.23:
EXECUTION_CLAIM (the model claims an action was carried out) and
PROMPT_INJECTION_ECHO (the model repeated instruction-like text lifted from an
uploaded document).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Set, Type

from pydantic import BaseModel, ValidationError

from ..models.enums import PROTECTED_FROM_CANCELLATION, Category
from .prompts import contains_injection, redact_text

# -- rejection reasons -------------------------------------------------------

AMOUNT_MISMATCH = "amount_does_not_match_backend_context"
UNSUPPORTED_MERCHANT = "merchant_not_supported_by_backend"
PERCENTAGE_MISMATCH = "percentage_does_not_match_calculation"
UNKNOWN_TRANSACTION_ID = "transaction_id_does_not_exist"
UNSUPPORTED_UNUSED_STATUS = "unused_status_not_supported_by_evidence"
GUARANTEED_RETURN = "returns_described_as_guaranteed"
SPECIFIC_SECURITY = "specific_security_recommended"
ESSENTIAL_CANCELLATION = "essential_expense_recommended_for_cancellation"
PII_EXPOSED = "pii_exposed_in_model_output"
SCHEMA_INVALID = "schema_fields_absent_or_invalid"
EXECUTION_CLAIM = "model_claimed_to_execute_an_action"
PROMPT_INJECTION_ECHO = "model_echoed_instruction_like_document_text"

TWO_PLACES = Decimal("0.01")

# -- text patterns -----------------------------------------------------------

#: A monetary value: a currency symbol, or two decimal places, or a currency word.
#: A bare integer is *not* money — "3 recurring payments" must not be flagged.
_MONEY = re.compile(
    r"(?:[$£€₹]\s?(?P<sym>\d[\d,]*(?:\.\d{1,2})?)"
    r"|(?P<dec>\b\d[\d,]*\.\d{2})\b"
    r"|\b(?P<word>\d[\d,]*(?:\.\d{1,2})?)\s?(?:dollars|usd|eur|gbp|inr|rupees)\b)",
    re.I,
)

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|percent\b)", re.I)

_GUARANTEE = re.compile(
    r"(?i)\b("
    r"guarante\w*|risk[- ]free|assured\s+return|no\s+risk|certain\s+return|"
    r"you\s+will\s+(?:earn|make|receive|get)|will\s+definitely\s+(?:grow|return)|"
    r"promise[sd]?\s+(?:a\s+)?return"
    r")\b"
)

#: Named instruments and asset classes. Mentioning any of these in a personal
#: finance app is a recommendation in effect, whatever the surrounding hedging.
_NAMED_SECURITIES = re.compile(
    r"(?i)\b("
    r"bitcoin|btc|ethereum|dogecoin|crypto(?:currency)?|"
    r"s\s?&\s?p\s?500|nasdaq|dow\s+jones|nifty|sensex|ftse|"
    r"vanguard|blackrock|fidelity\s+fund|robinhood|"
    r"index\s+fund|mutual\s+fund|etfs?|"
    r"tesla|nvidia|apple\s+stock|amazon\s+stock"
    r")\b"
)

_RECOMMEND_SECURITY = re.compile(
    r"(?i)\b(buy|purchase|invest\s+in|put\s+(?:it|money|this)\s+into|allocate\s+to|"
    r"recommend|suggest)\b[^.]{0,40}\b(stocks?|shares?|equit(?:y|ies)|bonds?|"
    r"securit(?:y|ies)|fund|portfolio|ticker)\b"
)

_CANCEL_VERB = re.compile(r"(?i)\b(cancel|cancelling|canceling|terminate|stop\s+paying|"
                          r"discontinue|end)\b")

#: Words that identify an essential obligation, per §3.15 / §25.5-25.8.
_ESSENTIAL_WORDS = re.compile(
    r"(?i)\b(rent|mortgage|landlord|emi|loan\s+(?:repayment|payment|instal?ment)|"
    r"insurance|premium|tax(?:es)?|medical|hospital|clinic|pharmacy|"
    r"utilit(?:y|ies)|electricity|water\s+bill|gas\s+bill|"
    r"school\s+fee|tuition|childcare|daycare)\b"
)

_UNUSED_CLAIM = re.compile(
    r"(?i)\b(unused|not\s+used|never\s+used|you\s+(?:do\s+not|don'?t)\s+use|"
    r"you\s+(?:have\s+not|haven'?t)\s+used|no\s+longer\s+use|dormant\s+subscription|"
    r"inactive\s+subscription)\b"
)

_EXECUTION_CLAIM = re.compile(
    r"(?i)\b("
    r"i\s+(?:have\s+)?(?:cancelled|canceled|transferred|invested|purchased|bought|sold|"
    r"paid|executed|placed\s+the\s+order)|"
    r"(?:has|have)\s+been\s+(?:cancelled|canceled|transferred|invested|executed)|"
    r"we\s+(?:cancelled|canceled|transferred|invested)"
    r")\b"
)

#: Placeholder left behind by `prompts.neutralize_injection`; if it comes back
#: out of a model, the model was chewing on document instructions (§3.23).
_INJECTION_MARKER = "[REMOVED_INSTRUCTION_LIKE_TEXT]"


def _to_decimal(raw: str) -> Optional[Decimal]:
    try:
        return Decimal(raw.replace(",", "").strip()).quantize(TWO_PLACES)
    except (InvalidOperation, ValueError, AttributeError):
        return None


def extract_amounts(text: str) -> List[Decimal]:
    """Every monetary value a piece of text asserts."""
    out: List[Decimal] = []
    for match in _MONEY.finditer(text or ""):
        raw = match.group("sym") or match.group("dec") or match.group("word")
        value = _to_decimal(raw)
        if value is not None:
            out.append(value)
    return out


def extract_percentages(text: str) -> List[Decimal]:
    out: List[Decimal] = []
    for match in _PERCENT.finditer(text or ""):
        value = _to_decimal(match.group(1))
        if value is not None:
            out.append(value)
    return out


@dataclass
class ValidationContext:
    """The backend truth a model response is checked against.

    Nothing is inferred here: the caller passes exactly the values the backend
    calculated. If a number is not in this context, no model may state it.
    """

    allowed_amounts: Set[Decimal] = field(default_factory=set)
    allowed_percentages: Set[Decimal] = field(default_factory=set)
    allowed_merchants: Set[str] = field(default_factory=set)
    allowed_transaction_ids: Set[str] = field(default_factory=set)
    #: Merchants the *user* explicitly confirmed they do not use (§13, §25.9).
    confirmed_unused_merchants: Set[str] = field(default_factory=set)
    #: Merchants that must never be recommended for cancellation (§25.5-25.8).
    protected_merchants: Set[str] = field(default_factory=set)
    allowed_categories: Set[str] = field(
        default_factory=lambda: {c.value for c in Category}
    )

    def add_amount(self, value: Any) -> "ValidationContext":
        if isinstance(value, Decimal):
            self.allowed_amounts.add(value.quantize(TWO_PLACES))
        elif isinstance(value, (int, float)):
            self.allowed_amounts.add(Decimal(str(value)).quantize(TWO_PLACES))
        return self

    def add_percentage(self, value: Any) -> "ValidationContext":
        if isinstance(value, (Decimal, int, float)):
            self.allowed_percentages.add(Decimal(str(value)).quantize(TWO_PLACES))
        return self

    def merchant_allowed(self, merchant: Optional[str]) -> bool:
        if not merchant:
            return False
        return merchant.strip().lower() in {m.strip().lower() for m in self.allowed_merchants}

    def merchant_protected(self, merchant: Optional[str]) -> bool:
        if not merchant:
            return False
        return merchant.strip().lower() in {m.strip().lower() for m in self.protected_merchants}

    def unused_supported(self, merchant: Optional[str]) -> bool:
        if not merchant:
            return False
        return merchant.strip().lower() in {
            m.strip().lower() for m in self.confirmed_unused_merchants
        }

    @classmethod
    def from_facts(
        cls,
        facts: Dict[str, Any],
        merchants: Optional[Iterable[str]] = None,
        transaction_ids: Optional[Iterable[str]] = None,
        confirmed_unused: Optional[Iterable[str]] = None,
        protected: Optional[Iterable[str]] = None,
    ) -> "ValidationContext":
        """Build a context from the same fact dictionary that went into the prompt.

        Using one dictionary for both means a value can only be stated by the
        model if the backend actually put it in front of the model.
        """
        context = cls(
            allowed_merchants=set(merchants or []),
            allowed_transaction_ids=set(transaction_ids or []),
            confirmed_unused_merchants=set(confirmed_unused or []),
            protected_merchants=set(protected or []),
        )
        for key, value in facts.items():
            if isinstance(value, (Decimal, int, float)) and not isinstance(value, bool):
                if "percent" in key or key.endswith("_pct"):
                    context.add_percentage(value)
                else:
                    context.add_amount(value)
                    # A percentage may legitimately be quoted from a numeric fact.
                    if "percent" in key or "increase" in key:
                        context.add_percentage(value)
        return context


@dataclass
class GuardrailResult:
    """Outcome of validating one model response."""

    accepted: bool
    violations: List[str] = field(default_factory=list)
    value: Optional[BaseModel] = None
    raw: Optional[str] = None

    @property
    def rejected(self) -> bool:
        return not self.accepted


def check_text(
    text: str,
    context: ValidationContext,
    merchant: Optional[str] = None,
    allow_cancellation_language: bool = False,
) -> List[str]:
    """Run every content check §16 lists over a free-text field."""
    violations: List[str] = []
    text = text or ""

    for amount in extract_amounts(text):
        if amount not in context.allowed_amounts:
            violations.append("%s:%s" % (AMOUNT_MISMATCH, amount))

    for percentage in extract_percentages(text):
        if percentage not in context.allowed_percentages:
            violations.append("%s:%s" % (PERCENTAGE_MISMATCH, percentage))

    if _GUARANTEE.search(text):
        violations.append(GUARANTEED_RETURN)

    if _NAMED_SECURITIES.search(text) or _RECOMMEND_SECURITY.search(text):
        violations.append(SPECIFIC_SECURITY)

    if _CANCEL_VERB.search(text):
        if _ESSENTIAL_WORDS.search(text):
            violations.append(ESSENTIAL_CANCELLATION)
        elif context.merchant_protected(merchant):
            violations.append(ESSENTIAL_CANCELLATION)

    if _UNUSED_CLAIM.search(text) and not context.unused_supported(merchant):
        violations.append(UNSUPPORTED_UNUSED_STATUS)

    if _EXECUTION_CLAIM.search(text) and not allow_cancellation_language:
        violations.append(EXECUTION_CLAIM)

    if redact_text(text) != text:
        violations.append(PII_EXPOSED)

    if _INJECTION_MARKER in text or contains_injection(text):
        violations.append(PROMPT_INJECTION_ECHO)

    return violations


def validate_merchant_resolution(
    model: "BaseModel", context: ValidationContext
) -> List[str]:
    """§16 checks specific to MerchantResolution."""
    violations: List[str] = []
    merchant = getattr(model, "normalized_merchant", "")
    if not context.merchant_allowed(merchant):
        violations.append("%s:%s" % (UNSUPPORTED_MERCHANT, merchant))
    category = (getattr(model, "category", "") or "").strip().lower()
    if category and category not in {c.lower() for c in context.allowed_categories}:
        violations.append("%s:%s" % (SCHEMA_INVALID, "unknown_category"))
    violations += check_text(getattr(model, "explanation", ""), context, merchant)
    for token in getattr(model, "evidence_tokens", []) or []:
        if redact_text(token) != token:
            violations.append(PII_EXPOSED)
    return violations


def validate_insight(model: "BaseModel", context: ValidationContext) -> List[str]:
    """§16 checks specific to InsightExplanation."""
    violations: List[str] = []
    for txn_id in getattr(model, "evidence_transaction_ids", []) or []:
        if txn_id not in context.allowed_transaction_ids:
            violations.append("%s:%s" % (UNKNOWN_TRANSACTION_ID, txn_id))
    for value in (
        getattr(model, "title", ""),
        getattr(model, "explanation", ""),
        getattr(model, "suggested_action", "") or "",
    ):
        violations += check_text(value, context)
    return violations


def validate_action_draft(model: "BaseModel", context: ValidationContext) -> List[str]:
    """§16 checks specific to ActionDraft.

    A cancellation draft must be allowed to contain the word "cancel" — that is
    the whole point of the artefact — but only for a merchant the backend has
    confirmed is *not* protected, and it may still never claim the cancellation
    already happened.
    """
    violations: List[str] = []
    merchant = getattr(model, "merchant", "")
    if not context.merchant_allowed(merchant):
        violations.append("%s:%s" % (UNSUPPORTED_MERCHANT, merchant))
    if context.merchant_protected(merchant):
        violations.append(ESSENTIAL_CANCELLATION)

    body = getattr(model, "body", "")
    subject = getattr(model, "subject", "")
    combined = "%s\n%s" % (subject, body)

    for amount in extract_amounts(combined):
        if amount not in context.allowed_amounts:
            violations.append("%s:%s" % (AMOUNT_MISMATCH, amount))
    for percentage in extract_percentages(combined):
        if percentage not in context.allowed_percentages:
            violations.append("%s:%s" % (PERCENTAGE_MISMATCH, percentage))
    if _GUARANTEE.search(combined):
        violations.append(GUARANTEED_RETURN)
    if _NAMED_SECURITIES.search(combined) or _RECOMMEND_SECURITY.search(combined):
        violations.append(SPECIFIC_SECURITY)
    if _ESSENTIAL_WORDS.search(combined) and _CANCEL_VERB.search(combined):
        violations.append(ESSENTIAL_CANCELLATION)
    if _UNUSED_CLAIM.search(combined) and not context.unused_supported(merchant):
        violations.append(UNSUPPORTED_UNUSED_STATUS)
    if _EXECUTION_CLAIM.search(combined):
        violations.append(EXECUTION_CLAIM)
    if redact_text(combined) != combined:
        violations.append(PII_EXPOSED)
    if _INJECTION_MARKER in combined or contains_injection(combined):
        violations.append(PROMPT_INJECTION_ECHO)

    if getattr(model, "unsupported_claims", None):
        # The model itself flagged unsupported content: take it at its word.
        violations.append("%s:self_reported" % AMOUNT_MISMATCH)
    return violations


def validate_verification(model: "BaseModel", context: ValidationContext) -> List[str]:
    """§16 checks specific to VerificationResult."""
    violations: List[str] = []
    corrected = getattr(model, "corrected_text", None)
    if corrected:
        violations += check_text(corrected, context)
    return violations


_VALIDATORS = {
    "MerchantResolution": validate_merchant_resolution,
    "InsightExplanation": validate_insight,
    "ActionDraft": validate_action_draft,
    "VerificationResult": validate_verification,
}


def _strip_code_fence(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def parse_and_validate(
    raw: str,
    schema: Type[BaseModel],
    context: ValidationContext,
) -> GuardrailResult:
    """Parse raw model output into `schema` and run every §16 content check.

    A rejected result is returned, never raised, so callers fall back to the
    deterministic template rather than failing the request (§3.21).
    """
    text = _strip_code_fence(raw)
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return GuardrailResult(False, [SCHEMA_INVALID + ":not_json"], None, raw)

    if not isinstance(payload, dict):
        return GuardrailResult(False, [SCHEMA_INVALID + ":not_an_object"], None, raw)

    try:
        model = schema(**payload)
    except ValidationError as exc:
        reasons = [
            "%s:%s" % (SCHEMA_INVALID, ".".join(str(p) for p in err.get("loc", ())) or "root")
            for err in exc.errors()
        ]
        return GuardrailResult(False, reasons or [SCHEMA_INVALID], None, raw)

    validator = _VALIDATORS.get(schema.__name__)
    violations = validator(model, context) if validator else []
    if violations:
        return GuardrailResult(False, sorted(set(violations)), None, raw)
    return GuardrailResult(True, [], model, raw)


def protected_merchant_names(
    merchant_categories: Dict[str, Category]
) -> Set[str]:
    """Merchants whose category is protected from cancellation advice (§25.5-25.8)."""
    return {
        merchant
        for merchant, category in merchant_categories.items()
        if category in PROTECTED_FROM_CANCELLATION
    }
