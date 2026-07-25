"""The AI router — the only door between business logic and a model provider.

Spec §14 in one paragraph: the deterministic engines in `app/services` compute
every financial value; a model may *phrase* one of those values, resolve a
genuinely ambiguous merchant string, or read a finished sentence aloud. Nothing
else. This module is where that rule is enforced, so no route, service or
repository ever imports a provider adapter.

Five properties this file guarantees, each of which a caller may rely on:

1. **No method ever raises.** Every public method catches everything and returns
   a deterministic template on failure. `get_router()` itself cannot raise, so a
   missing provider, a bad environment variable or a broken adapter degrades the
   wording of the product and nothing else (§3.21, §14 "Do not crash because one
   provider is unavailable").

2. **Deterministic mode is a first-class path, not an error path.** With zero API
   keys configured — the normal state of this repository — every method returns
   complete, specific, evidence-backed content built from the backend's own
   numbers. The templates below are the product's voice, not a stub.

3. **Confidence routing (§14).** ≥90 the finding is already settled and a model
   may only rephrase it; 70-89 a model may help resolve ambiguity and the status
   stays "Likely"; <70 the finding is marked Needs Review and no consequential
   recommendation is produced at all — the router will not even call a provider.

4. **Disagreement is never averaged.** When a second model contradicts the
   first, both outputs are discarded, the finding is marked Needs Review and the
   deterministic template is used. There is deliberately no code path anywhere in
   this file that blends, votes on or means two model answers (§14).

5. **Context minimization and untrusted input (§3.17-3.23, §22).** Prompts are
   built exclusively by `prompts.py` from a bounded fact dictionary and at most
   `MAX_EVIDENCE_ROWS` short evidence rows. There is no code path that can send a
   statement, a file, or an account number to a provider, and document-derived
   text is fenced and neutralized before it is included as data.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..config import Settings, get_logger, load_settings
from . import prompts, validators
from .base import LLMProvider, ProviderUnavailable, TTSProvider, VoiceResult
from .elevenlabs_provider import ElevenLabsProvider
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider
from .openai_provider import OpenAIProvider
from .schemas import (
    ActionDraft,
    InsightExplanation,
    MerchantResolution,
    VerificationResult,
)
from .validators import ValidationContext

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Routing constants (§14)
# ---------------------------------------------------------------------------

#: At or above this backend confidence the finding is settled: no model is
#: needed to *detect* anything, only (optionally) to phrase it.
CONFIDENCE_CONFIRMED = 90.0

#: Below this the finding is Needs Review and produces no consequential advice.
CONFIDENCE_LIKELY = 70.0

BAND_CONFIRMED = "confirmed"
BAND_LIKELY = "likely"
BAND_NEEDS_REVIEW = "needs_review"

SOURCE_LLM = "llm"
SOURCE_DETERMINISTIC = "deterministic"

#: Router-level roles. Each maps onto the `roles` tags the adapters declare.
ROLE_EXPLANATION = "explanation"
ROLE_AMBIGUITY = "ambiguity"
ROLE_VERIFICATION = "verification"

_ROLE_TAGS: Dict[str, frozenset] = {
    ROLE_EXPLANATION: frozenset(
        {"explanations", "summaries", "action_drafts", "ai_coach"}
    ),
    ROLE_AMBIGUITY: frozenset(
        {"ambiguous_merchant", "ambiguous_classification", "multimodal_extraction_fallback"}
    ),
    ROLE_VERIFICATION: frozenset(
        {"verification", "contradiction_detection", "final_action_plan_check"}
    ),
}

#: Preference order from §14 "Recommended roles", used to break ties between two
#: providers that both declare the role.
_ROLE_ORDER: Dict[str, Tuple[str, ...]] = {
    ROLE_EXPLANATION: ("groq", "gemini", "openai"),
    ROLE_AMBIGUITY: ("gemini", "openai", "groq"),
    ROLE_VERIFICATION: ("openai", "gemini", "groq"),
}

#: A summary longer than this is not sent for synthesis. Truncating would make
#: the spoken words differ from the displayed words, which §26 forbids, so the
#: whole text falls back to display-only instead.
MAX_TRANSCRIPT_CHARS = 4000

#: Fact keys that may never be forwarded to a provider, whatever the caller
#: passes (§22, §34 context minimization). Matching is on the key name, so a
#: careless `{"account_number": ...}` is dropped before any redaction runs.
_FORBIDDEN_FACT_KEY = re.compile(
    r"(?i)(account|card_?(?:no|num)|iban|routing|sort_?code|ssn|passport|"
    r"email|phone|password|secret|token|api[_-]?key|statement_text|raw_text|"
    r"full_text|document_text)"
)

#: Fact keys whose numeric value should be rendered as money in a template.
_MONEY_KEY = re.compile(
    r"(?i)(amount|cost|total|balance|spare|contribution|income|outflow|buffer|"
    r"reserve|price|saving|recovery|value|growth|principal|cap|charge|fee|"
    r"spend|increase|payment)"
)

_PERCENT_KEY = re.compile(r"(?i)(percent|_pct$|rate$)")

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")

#: Attached to every AI-touched payload the UI renders.
DISCLAIMER = (
    "SafeSpare provides information only, not financial advice. "
    "It never moves money and never acts on your behalf."
)

#: Usage labels that never assert non-use. `UsageStatus.CONFIRMED_NOT_USED` is
#: deliberately worded so the sentence stays true without tripping the "unused"
#: guardrail when the merchant has not been passed for validation (§25.9).
_USAGE_LABELS = {
    "usage_unknown": "usage unknown",
    "possibly_underused": "possibly underused, which is an inference and not evidence",
    "user_confirms_regular_use": "confirmed by you as regular use",
    "user_confirms_occasional_use": "confirmed by you as occasional use",
    "user_confirms_not_used": "confirmed by you as no longer needed",
    "user_does_not_recognize_payment": "not recognised by you",
}

_CONFIRMED_UNUSED = {"user_confirms_not_used", "user_does_not_recognize_payment"}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _q(value: Any) -> Optional[Decimal]:
    """Coerce anything numeric to a 2dp Decimal, or None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, Decimal):
            return value.quantize(TWO_PLACES)
        if isinstance(value, (int, float)):
            return Decimal(str(value)).quantize(TWO_PLACES)
        if isinstance(value, str):
            return Decimal(value.replace(",", "").strip()).quantize(TWO_PLACES)
    except (InvalidOperation, ValueError, ArithmeticError):
        return None
    return None


def _dec(facts: Dict[str, Any], key: str) -> Optional[Decimal]:
    return _q(facts.get(key)) if facts else None


def _money(value: Any) -> str:
    """`$31.00`. No thousands separators — the amount validator parses this back."""
    amount = _q(value)
    return "$%s" % (amount if amount is not None else "0.00")


def _band(confidence: Optional[float]) -> str:
    """§14 confidence band. A missing confidence is treated as settled.

    Callers that omit `confidence` are reporting a value the deterministic core
    computed with certainty (a sum, a total); those are `confirmed` by
    definition. A caller with a genuine confidence score always passes it.
    """
    if confidence is None:
        return BAND_CONFIRMED
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return BAND_CONFIRMED
    if value <= 1.0:  # a 0-1 score rather than a 0-100 one
        value *= 100.0
    if value >= CONFIDENCE_CONFIRMED:
        return BAND_CONFIRMED
    if value >= CONFIDENCE_LIKELY:
        return BAND_LIKELY
    return BAND_NEEDS_REVIEW


def _as_float_confidence(value: Any, default: float = 100.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out * 100.0 if out <= 1.0 else out


def _texts_of(value: Any) -> Iterable[str]:
    """Every string reachable inside a payload value, for injection scanning."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            for text in _texts_of(item):
                yield text
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            for text in _texts_of(item):
                yield text


@dataclass
class _Attempt:
    """One provider round-trip. Never carries raw model text to a caller."""

    value: Optional[Any] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    failures: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    attempted: bool = False

    @property
    def accepted(self) -> bool:
        return self.value is not None


# ---------------------------------------------------------------------------
# Deterministic templates — the primary path (§3.21, §14 "All providers
# unavailable: use deterministic templates; keep the core application working")
# ---------------------------------------------------------------------------


def _usage_sentence(usage_status: Optional[str], merchant: Optional[str]) -> str:
    status = (usage_status or "usage_unknown").strip()
    subject = merchant or "this service"
    if status in ("usage_unknown", ""):
        return (
            "Bank data can show the payment but not the visit, so the usage status "
            "for %s stays 'usage unknown' until you answer the usage question."
            % subject
        )
    if status == "possibly_underused":
        return (
            "The payment pattern for %s suggests it may be underused. That is an "
            "inference from the statement, not evidence, and it stays an inference "
            "until you confirm it." % subject
        )
    if status == "user_confirms_not_used":
        return "You confirmed you have not used %s in the last 30 days." % subject
    if status == "user_does_not_recognize_payment":
        return "You told us you do not recognise the payment to %s." % subject
    if status == "user_confirms_regular_use":
        return "You confirmed you use %s regularly." % subject
    if status == "user_confirms_occasional_use":
        return "You confirmed you use %s occasionally." % subject
    return (
        "The usage status for %s is %s."
        % (subject, _USAGE_LABELS.get(status, "usage unknown"))
    )


def _compose_safe_spare(facts: Dict[str, Any]) -> str:
    parts: List[str] = []
    now = _dec(facts, "safe_spare_now")
    monthly = _dec(facts, "safe_monthly_contribution")
    balance = _dec(facts, "latest_verified_balance")
    income = _dec(facts, "expected_income")
    essentials = _dec(facts, "upcoming_essential_outflows")
    projected = _dec(facts, "projected_balance_before_next_income")
    buffer_ = _dec(facts, "safety_buffer")
    volatility = _dec(facts, "volatility_reserve")

    if now is not None:
        parts.append(
            "SafeSpare calculates that %s can be safely spared right now." % _money(now)
        )
    if balance is not None and essentials is not None:
        sentence = "It starts from your latest balance of %s" % _money(balance)
        if income is not None and income > 0:
            sentence += ", adds expected income of %s" % _money(income)
        sentence += ", and subtracts %s of essential obligations that fall due before your next expected income" % _money(
            essentials
        )
        if projected is not None:
            sentence += ", leaving a projected balance of %s" % _money(projected)
        parts.append(sentence + ".")
    if buffer_ is not None or volatility is not None:
        held: List[str] = []
        if buffer_ is not None:
            held.append("a %s safety buffer" % _money(buffer_))
        if volatility is not None:
            held.append("a %s volatility reserve" % _money(volatility))
        parts.append("Held back on top of that: %s." % " and ".join(held))
    if monthly is not None:
        parts.append(
            "That works out at %s a month you could redirect without putting the "
            "essentials at risk." % _money(monthly)
        )
    limiting = facts.get("limiting_factor")
    if isinstance(limiting, str) and limiting and limiting != "none":
        parts.append(
            "The figure is currently limited by your %s." % limiting.replace("_", " ")
        )
    if facts.get("balance_is_estimated"):
        parts.append(
            "The opening balance was estimated from the statement rather than read "
            "directly, so treat this as indicative."
        )
    return " ".join(parts)


def _compose_roundup(facts: Dict[str, Any]) -> str:
    historical = _dec(facts, "historical_round_up_total")
    allowed = _dec(facts, "allowed_round_up_total")
    parts: List[str] = []
    if historical is not None and allowed is not None:
        if allowed < historical:
            parts.append(
                "Your transactions created %s in potential round-ups, but only %s is "
                "considered safely redirectable." % (_money(historical), _money(allowed))
            )
        else:
            parts.append(
                "Your transactions created %s in round-ups, all of which is within "
                "your safe contribution." % (_money(historical),)
            )
    limiting = facts.get("limiting_factor")
    if isinstance(limiting, str) and limiting and limiting != "none":
        parts.append("The limit that applied was your %s." % limiting.replace("_", " "))
    eligible = facts.get("eligible_count")
    excluded = facts.get("excluded_count")
    if isinstance(eligible, int) and isinstance(excluded, int):
        parts.append(
            "%d transactions were eligible and %d were excluded, because essential "
            "payments, transfers and withdrawals never generate round-ups."
            % (eligible, excluded)
        )
    return " ".join(parts)


def _compose_price_increase(facts: Dict[str, Any], merchant: Optional[str]) -> str:
    previous = _dec(facts, "previous_amount")
    current = _dec(facts, "current_amount")
    percentage = _dec(facts, "percentage_increase")
    annualized = _dec(facts, "annualized_increase")
    started = facts.get("first_date_of_new_price")
    name = merchant or facts.get("merchant") or "This merchant"

    parts: List[str] = []
    if previous is not None and current is not None:
        sentence = "%s went from %s to %s" % (name, _money(previous), _money(current))
        if percentage is not None:
            sentence += ", an increase of %s%%" % percentage
        parts.append(sentence + ".")
    if annualized is not None:
        parts.append("Over a year that is %s more than before." % _money(annualized))
    if started:
        parts.append("The new price first appears on %s." % prompts.redact_text(started))
    parts.append(
        "Nothing was changed on your account — this is a change the merchant made."
    )
    return " ".join(parts)


def _compose_subscription(
    facts: Dict[str, Any], merchant: Optional[str], usage_status: Optional[str]
) -> str:
    monthly = _dec(facts, "monthly_cost")
    annual = _dec(facts, "annual_cost")
    score = facts.get("leak_score")
    band = facts.get("band")
    frequency = facts.get("frequency")
    name = merchant or facts.get("merchant") or "This recurring payment"

    parts: List[str] = []
    if monthly is not None:
        sentence = "%s costs %s a month" % (name, _money(monthly))
        if annual is not None:
            sentence += " (%s a year)" % _money(annual)
        parts.append(sentence + ".")
    elif isinstance(frequency, str) and frequency:
        parts.append("%s recurs %s." % (name, frequency.replace("_", "-")))
    if isinstance(score, int) and isinstance(band, str) and band:
        parts.append(
            "Its Leak Score is %d out of 100, which places it in the '%s' band."
            % (score, band.replace("_", " "))
        )
    parts.append(_usage_sentence(usage_status, name))
    if facts.get("protected"):
        parts.append(
            "This is recorded as an essential obligation, so SafeSpare never puts it "
            "forward as something to stop paying."
        )
    return " ".join(parts)


def _compose_goal(facts: Dict[str, Any]) -> str:
    contributions = _dec(facts, "user_contributions")
    growth = _dec(facts, "illustrative_growth")
    projected = _dec(facts, "projected_value")
    months = facts.get("months")
    monthly = _dec(facts, "safe_monthly_contribution")

    parts: List[str] = []
    if monthly is not None and isinstance(months, int):
        parts.append(
            "Setting aside %s a month for %d months is the plan you are looking at."
            % (_money(monthly), months)
        )
    if contributions is not None:
        parts.append("Of the projected total, %s is your own money." % _money(contributions))
    if growth is not None:
        parts.append(
            "The illustrative growth on top of that is %s." % _money(growth)
        )
    if projected is not None:
        parts.append("That gives an illustrative total of %s." % _money(projected))
    parts.append(
        "This is an illustration only. Actual outcomes may be higher, lower or negative."
    )
    return " ".join(parts)


def _label(key: str) -> str:
    return key.replace("_", " ").strip()


def _compose_generic(facts: Dict[str, Any]) -> str:
    """Last-resort renderer: state each verified fact plainly.

    Never invents a narrative it cannot support — it reports exactly what the
    backend passed in, which is what makes it safe for any insight type the
    product grows later.
    """
    rendered: List[str] = []
    for key in sorted(facts):
        value = facts[key]
        if isinstance(value, bool):
            rendered.append("%s: %s" % (_label(key), "yes" if value else "no"))
            continue
        number = _q(value)
        if number is not None and _MONEY_KEY.search(key) and not _PERCENT_KEY.search(key):
            rendered.append("%s: %s" % (_label(key), _money(number)))
        elif number is not None and _PERCENT_KEY.search(key):
            rendered.append("%s: %s%%" % (_label(key), number))
        elif number is not None:
            rendered.append("%s: %s" % (_label(key), number))
        else:
            rendered.append("%s: %s" % (_label(key), prompts.redact_text(value)))
    if not rendered:
        return (
            "SafeSpare has recorded this finding, and every figure behind it comes "
            "from your own transactions."
        )
    return "Verified figures behind this finding — %s." % "; ".join(rendered)


_COMPOSERS = {
    "safe_spare": _compose_safe_spare,
    "safe_spare_summary": _compose_safe_spare,
    "cashflow": _compose_safe_spare,
    "roundup": _compose_roundup,
    "round_up": _compose_roundup,
    "roundups": _compose_roundup,
    "goal": _compose_goal,
    "projection": _compose_goal,
    "simulation": _compose_goal,
}

_MERCHANT_COMPOSERS = {
    "price_increase": _compose_price_increase,
    "silent_price_increase": _compose_price_increase,
    "price_change": _compose_price_increase,
}

_USAGE_COMPOSERS = {
    "subscription": _compose_subscription,
    "leak": _compose_subscription,
    "leak_finding": _compose_subscription,
    "recurring": _compose_subscription,
    "recurring_payment": _compose_subscription,
    "duplicate_service": _compose_subscription,
}

#: Titles used when the caller does not supply one.
_DEFAULT_TITLES = {
    "safe_spare": "How much you can safely spare",
    "roundup": "Your round-up total",
    "round_up": "Your round-up total",
    "price_increase": "A price went up",
    "silent_price_increase": "A price went up quietly",
    "subscription": "A recurring payment worth reviewing",
    "leak": "A recurring payment worth reviewing",
    "goal": "Your goal projection",
    "projection": "Your goal projection",
}

# -- canned, always-safe strings ---------------------------------------------

SAFE_MINIMAL_EXPLANATION = (
    "Every figure in this finding was calculated by SafeSpare from your own "
    "transactions. Open the finding to see the transactions behind it."
)

REFUSAL_RULES = (
    "I follow the same rules in every conversation: SafeSpare's figures come from "
    "your transactions, and I only explain values the app has already calculated. "
    "I cannot rewrite those rules or those figures."
)
REFUSAL_SECRET = (
    "SafeSpare never shows a full account or card number, and it never discloses "
    "provider keys or credentials. Only the masked details on your dashboard are "
    "available to me."
)
REFUSAL_MUTATE = (
    "The Safe Spare figure is calculated from your transactions: income timing, "
    "essential obligations, your buffer and your spending volatility. I cannot "
    "overwrite it, and no figure in SafeSpare can be edited by asking for it. You "
    "can adjust the inputs — your buffer, your caps and your usage confirmations — "
    "and the app recalculates from those."
)
REFUSAL_GUARANTEE = (
    "No investment outcome can be promised. Every projection in SafeSpare is "
    "illustrative and may be higher, lower or negative."
)
REFUSAL_SECURITY = (
    "SafeSpare does not name or recommend any individual investment product, and it "
    "never tells you what to hold. It only shows how much you could safely set "
    "aside and what that might look like over time."
)
REFUSAL_ESSENTIAL = (
    "SafeSpare never recommends stopping an essential obligation — housing, loans, "
    "insurance, tax, medical, utility, childcare or education payments — and it "
    "never carries out any action for you. If the cost is a problem, ask the "
    "provider about payment options or a rate review."
)
REFUSAL_EXECUTE = (
    "SafeSpare never carries out payments, transfers, trades or changes to a "
    "subscription. Everything here is a draft or a projection that you decide to "
    "act on yourself."
)
REFUSAL_INVENT = (
    "I can only talk about transactions that are in the statement you uploaded. I "
    "will not add, guess or make anything up."
)
REFUSAL_UNUSED = (
    "Bank data alone cannot show how often you use a service. Until you answer the "
    "usage question in the app, the status for every subscription stays "
    "'usage unknown'."
)
COACH_DEFAULT = (
    "I can explain any figure SafeSpare has already calculated — your Safe Spare "
    "amount, your round-ups, recurring payments, price changes and goal "
    "projections — and point you at the transactions behind each one. I do not "
    "calculate, change or act on anything myself."
)

# -- question intent patterns (deterministic AI Coach, §24) -------------------

_ASK_SECRET = re.compile(
    r"(?i)\b(account|card|routing|iban|sort\s*code)\s*(number|no\b|digits)|"
    r"\bapi\s*key|\bpassword\b|\bcredential|\bsecret\b|\benv(ironment)?\s+var"
)
_ASK_MUTATE = re.compile(
    r"(?i)\b(change|set|update|edit|make|increase|raise|lower|override|force)\b"
    r"[^.\n]{0,40}\b(safe\s*spare|budget|balance|amount|saving|contribution|"
    r"figure|number|total)\b"
)
_ASK_GUARANTEE = re.compile(
    r"(?i)\b(guarantee\w*|risk[- ]free|assured|promise\w*)\b|"
    r"\b(will|can)\s+(i|this|it|you)\b[^.\n]{0,30}\b(definitely|for\s+sure|certain)\b"
)
_ASK_SECURITY = re.compile(
    r"(?i)\b(which|what|any|best)\b[^.\n]{0,30}"
    r"\b(stocks?|shares?|funds?|etfs?|crypto\w*|coins?|tickers?|securit(?:y|ies)|"
    r"bonds?)\b|"
    r"\bshould\s+i\s+(buy|sell|invest|hold)\b|"
    r"\b(recommend|suggest|pick)\b[^.\n]{0,25}\b(stocks?|funds?|etfs?|crypto\w*)\b"
)
_ASK_CANCEL = re.compile(
    r"(?i)\b(cancel|stop|terminate|end|close|unsubscribe)\b"
)
_ASK_ESSENTIAL = re.compile(
    r"(?i)\b(rent|mortgage|landlord|emi|loan|insurance|tax(?:es)?|medical|hospital|"
    r"utilit(?:y|ies)|electricity|school\s+fee|tuition|childcare|daycare)\b"
)
_ASK_EXECUTE = re.compile(
    r"(?i)^\s*(cancel|stop|pause|transfer|invest|buy|sell|pay|move)\b|"
    r"\b(do\s+it|for\s+me)\s*(now|please)?\s*[.!]?\s*$"
)
_ASK_INVENT = re.compile(
    r"(?i)\b(invent|make\s+up|fabricate|pretend|imagine)\b|"
    r"\blist\s+transactions?\s+(that\s+are\s+)?not\b|"
    r"\b(add|create)\s+a\s+(fake\s+)?transaction\b"
)
_ASK_UNUSED = re.compile(r"(?i)\b(unused|not\s+used|never\s+used|isn'?t\s+used)\b")
_ASK_USAGE = re.compile(
    r"(?i)\bdid\s+i\s+(use|go|visit|attend)\b|\bdo\s+i\s+(still\s+)?use\b|"
    r"\bhave\s+i\s+used\b|\bam\s+i\s+using\b"
)
_ASK_SPEND = re.compile(
    r"(?i)\bhow\s+much\b[^.\n]{0,50}\b(spend|spent|pay|paid|cost|costs|charge)\b|"
    r"\bwhat\s+(do|did)\s+i\s+(spend|pay)\b"
)
_ASK_EVIDENCE = re.compile(
    r"(?i)\b(which|what)\s+transactions?\b|\bprove[sd]?\b|\bproof\b|\bevidence\b|"
    r"\bshow\s+me\s+the\s+(transactions?|rows?)\b"
)


# ---------------------------------------------------------------------------
# The router
# ---------------------------------------------------------------------------


class AIRouter:
    """Synchronous, never-raising facade over every model provider (§14).

    Construct with `get_router()`. Tests inject fakes directly:

        AIRouter(Settings(), llm_providers=[FakeProvider(cfg)], tts_provider=FakeTTS())

    Every public method returns a dictionary containing at least::

        {"source": "llm" | "deterministic",
         "provider": <provider name> | None,
         "validation_failures": [<guardrail code>, ...],
         "review_required": bool}

    `validation_failures` records guardrail rejections only. A provider being
    down is not a validation failure — it appears in `provider_errors` and never
    marks a finding for review, because an outage says nothing about the finding.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        llm_providers: Optional[Sequence[LLMProvider]] = None,
        tts_provider: Optional[TTSProvider] = None,
    ) -> None:
        self.settings = settings if settings is not None else Settings()
        self._llms: List[LLMProvider] = []
        self._tts: Optional[TTSProvider] = tts_provider

        if llm_providers is not None:
            self._llms = [p for p in llm_providers if p is not None]
        else:
            for factory, config in (
                (GroqProvider, getattr(self.settings, "groq", None)),
                (GeminiProvider, getattr(self.settings, "gemini", None)),
                (OpenAIProvider, getattr(self.settings, "openai", None)),
            ):
                if config is None:
                    continue
                try:
                    self._llms.append(factory(config))
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "ai_provider_init_failed",
                        extra={
                            "event": "ai_provider_init_failed",
                            "ai_provider": getattr(config, "name", "unknown"),
                            "error_type": type(exc).__name__,
                        },
                    )

        if self._tts is None:
            try:
                self._tts = ElevenLabsProvider(self.settings.elevenlabs)
            except Exception:  # pragma: no cover - defensive
                self._tts = None

        self._log_startup_status()

    # -- startup validation (§14.1-14.6) ------------------------------------

    def _log_startup_status(self) -> None:
        """Log identifiers and states only. A secret can never reach this path."""
        try:
            for entry in self.provider_status():
                logger.info(
                    "ai_provider_status",
                    extra={
                        "event": "ai_provider_status",
                        "ai_provider": str(entry.get("provider")),
                        "ai_model": str(entry.get("model") or ""),
                        "ai_fallback_model": str(entry.get("fallback_model") or ""),
                        "configured": bool(entry.get("configured")),
                        "available": bool(entry.get("available")),
                        "detail": str(entry.get("detail") or ""),
                    },
                )
        except Exception:  # pragma: no cover - logging must never break startup
            pass

    def provider_status(self) -> List[Dict[str, Any]]:
        """Health of every adapter. Identifiers and booleans only — no secrets."""
        out: List[Dict[str, Any]] = []
        for provider in list(self._llms) + ([self._tts] if self._tts else []):
            try:
                out.append(provider.status().as_dict())
            except Exception:  # pragma: no cover - a broken adapter is still reportable
                out.append(
                    {
                        "provider": getattr(provider, "name", "unknown"),
                        "configured": False,
                        "available": False,
                        "model": None,
                        "fallback_model": None,
                        "detail": "status_unavailable",
                        "roles": [],
                    }
                )
        return out

    def deterministic_only(self) -> bool:
        """True when no LLM provider is usable — the normal state without keys."""
        return not any(self._configured(p) for p in self._llms)

    # -- provider plumbing --------------------------------------------------

    @staticmethod
    def _configured(provider: LLMProvider) -> bool:
        try:
            return bool(provider.configured)
        except Exception:  # pragma: no cover - defensive
            return False

    def _ordered(self, role: str, exclude: Sequence[str] = ()) -> List[LLMProvider]:
        """Configured providers for `role`, best fit first.

        A provider that does not declare the role is still used as a last
        resort: with a single key configured, one provider must be able to cover
        every role or the product would silently lose its wording layer.
        """
        tags = _ROLE_TAGS.get(role, frozenset())
        order = _ROLE_ORDER.get(role, ())
        excluded = {name.lower() for name in exclude if name}

        candidates: List[Tuple[int, int, int, LLMProvider]] = []
        for index, provider in enumerate(self._llms):
            if not self._configured(provider):
                continue
            name = str(getattr(provider, "name", "")).lower()
            if name in excluded:
                continue
            declares = 0 if tags & frozenset(getattr(provider, "roles", []) or []) else 1
            preference = order.index(name) if name in order else len(order)
            candidates.append((declares, preference, index, provider))
        candidates.sort(key=lambda item: item[:3])
        return [item[3] for item in candidates]

    def _call(
        self,
        role: str,
        prompt: Dict[str, str],
        schema: Any,
        context: ValidationContext,
        max_tokens: int = 700,
        exclude: Sequence[str] = (),
    ) -> _Attempt:
        """Ask providers for `role` until one answers. Never raises.

        A **transport** failure moves on to the next provider. A **guardrail**
        rejection does not: unsafe output means this question falls back to the
        deterministic template rather than being asked again elsewhere, so a
        rejected claim can never be laundered through a second provider.
        """
        attempt = _Attempt()
        for provider in self._ordered(role, exclude):
            attempt.attempted = True
            try:
                response = provider.complete_json(prompt, max_tokens=max_tokens)
            except ProviderUnavailable as exc:
                attempt.errors.append("%s:%s" % (exc.provider, exc.reason))
                continue
            except Exception as exc:  # pragma: no cover - adapters wrap their own
                attempt.errors.append(
                    "%s:%s" % (getattr(provider, "name", "unknown"), type(exc).__name__)
                )
                continue

            attempt.provider = response.provider
            attempt.model = response.model
            result = validators.parse_and_validate(response.text, schema, context)
            if result.accepted:
                attempt.value = result.value
                return attempt
            attempt.failures.extend(result.violations)
            return attempt
        return attempt

    # -- disagreement detection (§14: never average) ------------------------

    @staticmethod
    def _claims(model: Any) -> Tuple:
        """The checkable assertions in a model response.

        Two responses "agree" when they assert the same merchant/category, the
        same amounts, the same percentages and the same evidence rows. Wording
        may differ freely; facts may not.
        """
        empty = ValidationContext()
        if isinstance(model, MerchantResolution):
            return (
                (model.normalized_merchant or "").strip().lower(),
                (model.category or "").strip().lower(),
            )
        if isinstance(model, InsightExplanation):
            text = "%s %s %s" % (
                model.title,
                model.explanation,
                model.suggested_action or "",
            )
            return (
                frozenset(validators.extract_amounts(text)),
                frozenset(validators.extract_percentages(text)),
                frozenset(model.evidence_transaction_ids or []),
                bool(model.suggested_action),
            )
        if isinstance(model, ActionDraft):
            text = "%s %s" % (model.subject, model.body)
            return (
                (model.merchant or "").strip().lower(),
                (model.action_type or "").strip().lower(),
                frozenset(validators.extract_amounts(text)),
            )
        if isinstance(model, VerificationResult):
            return (bool(model.supported),)
        return (repr(model),)

    def _cross_check(
        self,
        role: str,
        prompt: Dict[str, str],
        schema: Any,
        context: ValidationContext,
        primary: _Attempt,
    ) -> Tuple[bool, _Attempt]:
        """Ask a *different* provider the same question. True when they disagree."""
        second = self._call(
            role, prompt, schema, context, exclude=(primary.provider or "",)
        )
        if not second.accepted:
            # No usable second opinion is not a disagreement; it is silence.
            return False, second
        return self._claims(primary.value) != self._claims(second.value), second

    def _verify(
        self,
        statement: str,
        facts: Dict[str, Any],
        context: ValidationContext,
        exclude: Sequence[str] = (),
    ) -> Tuple[Optional[bool], _Attempt]:
        """Second-model support check on a high-impact statement (§14).

        Returns `(supported, attempt)`. `supported` is None when no second
        provider was available — silence is never treated as disagreement.
        """
        prompt = prompts.verification_context(statement, facts)
        attempt = self._call(
            ROLE_VERIFICATION, prompt, VerificationResult, context, exclude=exclude
        )
        if not attempt.accepted:
            return None, attempt
        result = attempt.value
        supported = bool(result.supported) and not result.contradictions
        return supported, attempt

    # -- context assembly ---------------------------------------------------

    def _clean_facts(self, facts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Drop PII-shaped keys and redact every string value (§22, §25.18).

        This runs before anything is rendered into a prompt or a template, so an
        account number cannot reach a provider even if a caller puts one in the
        fact dictionary by mistake.
        """
        out: Dict[str, Any] = {}
        if not isinstance(facts, dict):
            return out
        dropped = 0
        for key, value in facts.items():
            name = str(key)
            if _FORBIDDEN_FACT_KEY.search(name):
                dropped += 1
                continue
            if isinstance(value, str):
                out[name] = prompts.redact_text(value)[: prompts.MAX_UNTRUSTED_FIELD_CHARS]
            elif isinstance(value, (Decimal, int, float, bool)) or value is None:
                out[name] = value
            else:
                out[name] = prompts.redact_text(value)[: prompts.MAX_UNTRUSTED_FIELD_CHARS]
        if dropped:
            logger.info(
                "ai_facts_filtered",
                extra={"event": "ai_facts_filtered", "dropped_fact_keys": dropped},
            )
        return out

    @staticmethod
    def _copy_context(context: Optional[ValidationContext]) -> ValidationContext:
        if not isinstance(context, ValidationContext):
            return ValidationContext()
        return ValidationContext(
            allowed_amounts=set(context.allowed_amounts),
            allowed_percentages=set(context.allowed_percentages),
            allowed_merchants=set(context.allowed_merchants),
            allowed_transaction_ids=set(context.allowed_transaction_ids),
            confirmed_unused_merchants=set(context.confirmed_unused_merchants),
            protected_merchants=set(context.protected_merchants),
            allowed_categories=set(context.allowed_categories),
        )

    def _context_for(
        self,
        context: Optional[ValidationContext],
        facts: Dict[str, Any],
        merchant: Optional[str] = None,
        transaction_ids: Optional[Iterable[str]] = None,
        usage_status: Optional[str] = None,
    ) -> ValidationContext:
        """The caller's context, widened by the facts the backend supplied.

        A value the backend put in front of the model is by definition a backend
        value, so it belongs in the allowed set. Nothing derived from a *model*
        response is ever added here — that is what makes "the LLM cannot alter a
        backend amount" hold.
        """
        ctx = self._copy_context(context)
        for key, value in (facts or {}).items():
            if isinstance(value, bool) or value is None:
                continue
            number = _q(value)
            if number is None:
                continue
            ctx.allowed_amounts.add(number)
            if _PERCENT_KEY.search(key) or "increase" in key:
                ctx.allowed_percentages.add(number)
        if merchant:
            ctx.allowed_merchants.add(merchant)
        for txn_id in transaction_ids or []:
            if txn_id:
                ctx.allowed_transaction_ids.add(str(txn_id))
        if merchant and (usage_status or "") in _CONFIRMED_UNUSED:
            ctx.confirmed_unused_merchants.add(merchant)
        return ctx

    @staticmethod
    def _evidence_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = payload.get("evidence_rows") or []
        if not isinstance(rows, (list, tuple)):
            return []
        return [row for row in rows if isinstance(row, dict)][: prompts.MAX_EVIDENCE_ROWS]

    @staticmethod
    def _injection_in(*values: Any) -> bool:
        """True when any untrusted value reads like an attempt to steer a model."""
        for value in values:
            for text in _texts_of(value):
                if prompts.contains_injection(text):
                    return True
        return False

    def _self_check(
        self,
        text: str,
        context: ValidationContext,
        merchant: Optional[str] = None,
    ) -> str:
        """Run the router's own template through the §16 guardrails.

        A deterministic template is trusted code, but trusted code drifts. If our
        own wording ever asserts a value the context does not contain, we would
        rather ship the minimal sentence than the wrong number.
        """
        try:
            violations = validators.check_text(text, context, merchant)
        except Exception:  # pragma: no cover - defensive
            return SAFE_MINIMAL_EXPLANATION
        if not violations:
            return text
        logger.warning(
            "ai_template_self_check_failed",
            extra={
                "event": "ai_template_self_check_failed",
                "validation_failures": ",".join(sorted({v.split(":")[0] for v in violations})),
            },
        )
        return SAFE_MINIMAL_EXPLANATION

    def _log(self, method: str, result: Dict[str, Any]) -> None:
        """Identifiers and codes only — never a prompt, a response or a fact."""
        try:
            codes = sorted(
                {str(f).split(":")[0] for f in result.get("validation_failures") or []}
            )
            logger.info(
                "ai_route",
                extra={
                    "event": "ai_route",
                    "ai_method": method,
                    "ai_provider": str(result.get("provider") or "none"),
                    "ai_model": str(result.get("model") or ""),
                    "ai_source": str(result.get("source")),
                    "review_required": bool(result.get("review_required")),
                    "validation_failures": ",".join(codes),
                    "provider_error_count": len(result.get("provider_errors") or []),
                    "injection_detected": bool(result.get("injection_detected")),
                },
            )
        except Exception:  # pragma: no cover - logging must never break a request
            pass

    # -- §6.11 insight explanation -----------------------------------------

    def explain_insight(
        self, context: Optional[ValidationContext], payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Phrase a finding the backend has already calculated.

        `payload` keys, all optional except `facts`:

        ``insight_type``        one of the keys in `_COMPOSERS` / free-form
        ``title``              deterministic title, if the caller has one
        ``facts``              verified backend values — the only real numbers
        ``deterministic_explanation``  wording a service already produced
        ``evidence_transaction_ids``   IDs a model may cite, and no others
        ``evidence_rows``      up to `MAX_EVIDENCE_ROWS` short rows
        ``confidence``         0-100 (or 0-1) backend confidence — drives routing
        ``merchant``           the finding's merchant, if any
        ``usage_status``       `UsageStatus` value, if any
        ``suggested_action``   deterministic next step, if any
        ``high_impact``        request a second-model support check
        """
        try:
            return self._explain_insight(context, payload)
        except Exception as exc:  # pragma: no cover - the contract is "never raises"
            logger.warning(
                "ai_explain_insight_failed",
                extra={"event": "ai_explain_insight_failed", "error_type": type(exc).__name__},
            )
            return {
                "insight_type": "summary",
                "title": "Finding",
                "explanation": SAFE_MINIMAL_EXPLANATION,
                "suggested_action": None,
                "evidence_transaction_ids": [],
                "confidence": 0.0,
                "review_status": BAND_NEEDS_REVIEW,
                "review_required": True,
                "usage_status": "usage_unknown",
                "source": SOURCE_DETERMINISTIC,
                "provider": None,
                "model": None,
                "validation_failures": [],
                "provider_errors": [],
                "injection_detected": False,
                "values_are_backend_verified": True,
                "disclaimer": DISCLAIMER,
            }

    def _explain_insight(
        self, context: Optional[ValidationContext], payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = dict(payload or {})
        insight_type = str(payload.get("insight_type") or "summary")
        merchant = payload.get("merchant") or None
        usage_status = payload.get("usage_status") or "usage_unknown"
        facts = self._clean_facts(payload.get("facts"))
        evidence_ids = [
            str(i) for i in (payload.get("evidence_transaction_ids") or []) if i
        ]
        ctx = self._context_for(context, facts, merchant, evidence_ids, usage_status)
        band = _band(payload.get("confidence"))
        confidence = _as_float_confidence(payload.get("confidence"))
        rows = self._evidence_rows(payload)
        injection = self._injection_in(
            rows, payload.get("deterministic_explanation"), payload.get("title"),
            merchant, facts,
        )

        title = str(payload.get("title") or _DEFAULT_TITLES.get(insight_type) or "Finding")
        explanation = self._deterministic_explanation(
            insight_type, facts, merchant, usage_status, payload
        )
        explanation = self._self_check(explanation, ctx, merchant)
        suggested = payload.get("suggested_action") or None

        failures: List[str] = []
        errors: List[str] = []
        source = SOURCE_DETERMINISTIC
        provider = None
        model_id = None

        # §14: below 70 the finding is Needs Review and produces no consequential
        # recommendation, so no provider is consulted at all.
        if band != BAND_NEEDS_REVIEW and not self.deterministic_only():
            prompt = prompts.insight_context(insight_type, facts, rows)
            attempt = self._call(ROLE_EXPLANATION, prompt, InsightExplanation, ctx)
            errors.extend(attempt.errors)
            failures.extend(attempt.failures)
            if attempt.accepted:
                proposed = attempt.value
                disagreement = False
                if payload.get("high_impact"):
                    supported, verifier = self._verify(
                        proposed.explanation, facts, ctx, exclude=(attempt.provider or "",)
                    )
                    errors.extend(verifier.errors)
                    failures.extend(verifier.failures)
                    if supported is False:
                        # §14: do not average, do not pick a winner — review it.
                        disagreement = True
                        failures.append(validators.MODEL_DISAGREEMENT)
                if not disagreement:
                    title = proposed.title or title
                    explanation = proposed.explanation
                    suggested = proposed.suggested_action or suggested
                    evidence_ids = [
                        i for i in (proposed.evidence_transaction_ids or []) if i
                    ] or evidence_ids
                    source = SOURCE_LLM
                    provider = attempt.provider
                    model_id = attempt.model

        review_status = band
        if failures or injection:
            review_status = BAND_NEEDS_REVIEW
        if review_status == BAND_NEEDS_REVIEW:
            # §14: no consequential recommendation at this confidence.
            suggested = None
            if SAFE_MINIMAL_EXPLANATION not in explanation:
                explanation = (
                    "%s SafeSpare has flagged this finding for your review before any "
                    "action is considered." % explanation
                ).strip()

        result = {
            "insight_type": insight_type,
            "title": title,
            "explanation": explanation,
            "suggested_action": suggested,
            "evidence_transaction_ids": evidence_ids,
            "confidence": confidence,
            "review_status": review_status,
            "review_required": review_status == BAND_NEEDS_REVIEW,
            "usage_status": usage_status,
            "merchant": merchant,
            "source": source,
            "provider": provider,
            "model": model_id,
            "validation_failures": failures,
            "provider_errors": errors,
            "injection_detected": injection,
            "values_are_backend_verified": True,
            "disclaimer": DISCLAIMER,
        }
        self._log("explain_insight", result)
        return result

    def _deterministic_explanation(
        self,
        insight_type: str,
        facts: Dict[str, Any],
        merchant: Optional[str],
        usage_status: Optional[str],
        payload: Dict[str, Any],
    ) -> str:
        """Template wording for one finding. Never touches a provider."""
        supplied = payload.get("deterministic_explanation") or payload.get("explanation")
        if isinstance(supplied, str) and supplied.strip():
            # A service already wrote an evidence-backed sentence; it is the
            # better text and it is already built from verified values.
            return prompts.redact_text(supplied).strip()

        key = insight_type.strip().lower()
        if key in _MERCHANT_COMPOSERS:
            text = _MERCHANT_COMPOSERS[key](facts, merchant)
        elif key in _USAGE_COMPOSERS:
            text = _USAGE_COMPOSERS[key](facts, merchant, usage_status)
        elif key in _COMPOSERS:
            text = _COMPOSERS[key](facts)
        else:
            text = _compose_generic(facts)
        text = text.strip()
        return text or SAFE_MINIMAL_EXPLANATION

    # -- §6.9 action drafts -------------------------------------------------

    def draft_action(
        self, context: Optional[ValidationContext], payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Draft a message the *user* may choose to send. Never sends anything.

        `payload` keys:

        ``action_type``   "cancel" | "downgrade" | "renegotiate" | "review"
        ``merchant``      required — the backend's normalized merchant
        ``facts``         verified values that may appear in the message
        ``confidence``    0-100 backend confidence
        ``usage_status``  `UsageStatus` value
        ``protected``     True when the merchant is an essential obligation
        ``user_confirmed``  True when the user explicitly chose this action
        ``high_impact``   request a second-model support check
        """
        try:
            return self._draft_action(context, payload)
        except Exception as exc:  # pragma: no cover - the contract is "never raises"
            logger.warning(
                "ai_draft_action_failed",
                extra={"event": "ai_draft_action_failed", "error_type": type(exc).__name__},
            )
            merchant = str((payload or {}).get("merchant") or "this merchant")
            return self._blocked_draft(
                merchant, "draft_unavailable", [], [], BAND_NEEDS_REVIEW
            )

    def _draft_action(
        self, context: Optional[ValidationContext], payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = dict(payload or {})
        merchant = str(payload.get("merchant") or "").strip()
        action_type = str(payload.get("action_type") or "review").strip().lower()
        usage_status = str(payload.get("usage_status") or "usage_unknown")
        facts = self._clean_facts(payload.get("facts"))
        ctx = self._context_for(context, facts, merchant or None, None, usage_status)
        band = _band(payload.get("confidence"))
        injection = self._injection_in(merchant, facts)

        protected = bool(payload.get("protected")) or ctx.merchant_protected(merchant)
        confirmed = bool(payload.get("user_confirmed")) or usage_status in _CONFIRMED_UNUSED

        # 1. An essential obligation never receives cancellation wording (§3.15).
        if protected and action_type in ("cancel", "downgrade"):
            return self._blocked_draft(
                merchant or "this merchant", "essential_obligation", [], [], band
            )
        # 2. Below 70 no consequential recommendation is produced at all (§14).
        if band == BAND_NEEDS_REVIEW:
            return self._blocked_draft(
                merchant or "this merchant", "confidence_below_threshold", [], [], band
            )
        # 3. Bank data alone can never justify a cancellation (§3.12, §25.9).
        if action_type == "cancel" and not confirmed:
            return self._blocked_draft(
                merchant or "this merchant", "usage_not_confirmed", [], [], band
            )
        # 4. Instruction-shaped text in the source data is never acted on (§3.23).
        if injection:
            return self._blocked_draft(
                merchant or "this merchant", "suspicious_source_text", [], [], band,
                injection=True,
            )

        subject, body = self._deterministic_draft(action_type, merchant, facts)
        subject = self._self_check(subject, ctx, merchant)
        body = self._self_check(body, ctx, merchant)

        failures: List[str] = []
        errors: List[str] = []
        source = SOURCE_DETERMINISTIC
        provider = None
        model_id = None

        if not self.deterministic_only():
            prompt = prompts.action_draft_context(action_type, merchant, facts)
            attempt = self._call(ROLE_EXPLANATION, prompt, ActionDraft, ctx)
            errors.extend(attempt.errors)
            failures.extend(attempt.failures)
            if attempt.accepted:
                proposed = attempt.value
                disagreement = False
                if payload.get("high_impact"):
                    supported, verifier = self._verify(
                        proposed.body, facts, ctx, exclude=(attempt.provider or "",)
                    )
                    errors.extend(verifier.errors)
                    failures.extend(verifier.failures)
                    if supported is False:
                        disagreement = True
                        failures.append(validators.MODEL_DISAGREEMENT)
                if not disagreement:
                    subject = proposed.subject
                    body = proposed.body
                    source = SOURCE_LLM
                    provider = attempt.provider
                    model_id = attempt.model

        result = {
            "action_type": action_type,
            "merchant": merchant,
            "subject": subject,
            "body": body,
            "facts_used": sorted(facts),
            "refused": False,
            "refusal_reason": None,
            "requires_user_approval": True,
            "executed": False,
            "review_status": band,
            "review_required": band == BAND_NEEDS_REVIEW or bool(failures),
            "source": source,
            "provider": provider,
            "model": model_id,
            "validation_failures": failures,
            "provider_errors": errors,
            "injection_detected": injection,
            "disclaimer": DISCLAIMER,
        }
        self._log("draft_action", result)
        return result

    def _blocked_draft(
        self,
        merchant: str,
        reason: str,
        failures: List[str],
        errors: List[str],
        band: str,
        injection: bool = False,
    ) -> Dict[str, Any]:
        """A refusal is always deterministic — a model is never asked to say no."""
        bodies = {
            "essential_obligation": (
                "%s is recorded as an essential obligation. SafeSpare never drafts a "
                "message to stop an essential payment such as housing, loans, "
                "insurance, tax, medical, utility, childcare or education costs. If "
                "the amount is a problem, ask the provider about payment options or "
                "a review of the rate instead." % merchant
            ),
            "confidence_below_threshold": (
                "SafeSpare is not confident enough about this payment to put a "
                "message in your hands yet. Confirm the merchant and the pattern on "
                "the review screen, and the draft becomes available."
            ),
            "usage_not_confirmed": (
                "SafeSpare will not draft this message until you have answered "
                "whether you still use %s. Bank data shows the payment, never the "
                "use, so that answer has to come from you." % merchant
            ),
            "suspicious_source_text": (
                "The statement text behind this payment contains instruction-like "
                "wording, so SafeSpare has held the draft back for your review. The "
                "figures on your dashboard are unaffected."
            ),
            "draft_unavailable": (
                "SafeSpare could not prepare this draft. Nothing has changed on your "
                "account, and every figure on your dashboard is unaffected."
            ),
        }
        result = {
            "action_type": "review",
            "merchant": merchant,
            "subject": "Review needed before contacting %s" % merchant,
            "body": bodies.get(reason, bodies["draft_unavailable"]),
            "facts_used": [],
            "refused": True,
            "refusal_reason": reason,
            "requires_user_approval": True,
            "executed": False,
            "review_status": BAND_NEEDS_REVIEW,
            "review_required": True,
            "source": SOURCE_DETERMINISTIC,
            "provider": None,
            "model": None,
            "validation_failures": failures,
            "provider_errors": errors,
            "injection_detected": injection,
            "disclaimer": DISCLAIMER,
        }
        self._log("draft_action", result)
        return result

    @staticmethod
    def _deterministic_draft(
        action_type: str, merchant: str, facts: Dict[str, Any]
    ) -> Tuple[str, str]:
        """A real, sendable message built only from verified values."""
        name = merchant or "your provider"
        monthly = _dec(facts, "monthly_cost")
        annual = _dec(facts, "annual_cost")
        previous = _dec(facts, "previous_amount")
        current = _dec(facts, "current_amount")
        percentage = _dec(facts, "percentage_increase")

        cost_line = ""
        if monthly is not None:
            cost_line = "My plan is currently billed at %s a month" % _money(monthly)
            if annual is not None:
                cost_line += " (%s a year)" % _money(annual)
            cost_line += "."

        change_line = ""
        if previous is not None and current is not None:
            change_line = "The charge moved from %s to %s" % (
                _money(previous),
                _money(current),
            )
            if percentage is not None:
                change_line += ", an increase of %s%%" % percentage
            change_line += "."

        if action_type == "downgrade":
            subject = "Moving my %s plan to a lower tier" % name
            ask = (
                "I would like to move to a lower-priced plan. Could you tell me which "
                "tiers are available, what each one costs, and what changes if I move?"
            )
        elif action_type == "renegotiate":
            subject = "Reviewing the price of my %s plan" % name
            ask = (
                "I would like to review what I pay. Could you tell me what options are "
                "available to bring the cost back down, including any current offers?"
            )
        elif action_type == "cancel":
            subject = "Closing my %s account" % name
            ask = (
                "I would like to cancel this subscription. Please confirm in writing "
                "the date my access finishes and that no further payments will be taken."
            )
        else:
            subject = "A question about my %s plan" % name
            ask = "Could you confirm what I am currently being charged for and why?"

        body = "\n\n".join(
            part
            for part in (
                "Hello %s team," % name,
                " ".join(p for p in (cost_line, change_line) if p) or None,
                ask,
                "Thank you.",
            )
            if part
        )
        return subject, body

    # -- §6.11 AI Coach -----------------------------------------------------

    def coach_reply(
        self,
        context: Optional[ValidationContext],
        question: str,
        facts: Optional[Dict[str, Any]] = None,
        evidence_rows: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Answer a question using only values the backend already verified.

        `question` is untrusted user text: it is redacted and neutralized before
        it goes anywhere near a prompt, and it is never placed in a system
        message. Every refusal is deterministic — a model is never asked to
        decline on the product's behalf.
        """
        try:
            return self._coach_reply(context, question, facts, evidence_rows)
        except Exception as exc:  # pragma: no cover - the contract is "never raises"
            logger.warning(
                "ai_coach_failed",
                extra={"event": "ai_coach_failed", "error_type": type(exc).__name__},
            )
            return {
                "answer": COACH_DEFAULT,
                "citations": [],
                "refusal_reason": "coach_unavailable",
                "source": SOURCE_DETERMINISTIC,
                "provider": None,
                "model": None,
                "validation_failures": [],
                "provider_errors": [],
                "injection_detected": False,
                "review_required": False,
                "disclaimer": DISCLAIMER,
            }

    def _coach_reply(
        self,
        context: Optional[ValidationContext],
        question: str,
        facts: Optional[Dict[str, Any]],
        evidence_rows: Optional[Sequence[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        raw_question = question if isinstance(question, str) else str(question or "")
        clean_facts = self._clean_facts(facts)
        ctx = self._context_for(context, clean_facts)
        injection = prompts.contains_injection(raw_question)
        rows = [r for r in (evidence_rows or []) if isinstance(r, dict)][
            : prompts.MAX_EVIDENCE_ROWS
        ]

        refusal, answer = self._coach_refusal(raw_question, injection)
        citations: List[str] = []
        failures: List[str] = []
        errors: List[str] = []
        source = SOURCE_DETERMINISTIC
        provider = None
        model_id = None

        if refusal is None:
            answer, citations = self._coach_answer(raw_question, clean_facts, ctx)
            if not self.deterministic_only():
                prompt = self._coach_prompt(raw_question, clean_facts, rows)
                attempt = self._call(ROLE_EXPLANATION, prompt, InsightExplanation, ctx)
                errors.extend(attempt.errors)
                failures.extend(attempt.failures)
                if attempt.accepted:
                    answer = attempt.value.explanation
                    citations = [
                        i for i in (attempt.value.evidence_transaction_ids or []) if i
                    ] or citations
                    source = SOURCE_LLM
                    provider = attempt.provider
                    model_id = attempt.model

        answer = self._self_check(answer, ctx)
        result = {
            "answer": answer,
            "citations": citations,
            "refusal_reason": refusal,
            "source": source,
            "provider": provider,
            "model": model_id,
            "validation_failures": failures,
            "provider_errors": errors,
            "injection_detected": injection,
            "review_required": bool(failures),
            "disclaimer": DISCLAIMER,
        }
        self._log("coach_reply", result)
        return result

    @staticmethod
    def _coach_prompt(
        question: str, facts: Dict[str, Any], rows: Sequence[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Question goes in as fenced, neutralized *data* — never as instruction."""
        return prompts.build_prompt(
            task="Answer one question about a user's own verified finances.",
            instruction=(
                "Answer the question in USER_QUESTION using ONLY the values in "
                "VERIFIED_BACKEND_FACTS and the listed evidence rows. If the answer "
                "is not in those values, say that the figure is not available. Never "
                "compute a new number. Never describe a service as unused."
            ),
            verified_facts=facts,
            evidence_rows=rows,
            untrusted_text="USER_QUESTION: %s" % question,
            schema_hint=(
                '{"insight_type": str, "title": str, "explanation": str, '
                '"evidence_transaction_ids": [str], "suggested_action": str|null, '
                '"confidence": float}'
            ),
        )

    @staticmethod
    def _coach_refusal(question: str, injection: bool) -> Tuple[Optional[str], str]:
        """Deterministic §24 refusals, checked in descending order of harm."""
        text = question or ""
        if injection:
            return "instruction_injection", REFUSAL_RULES
        if _ASK_SECRET.search(text):
            return "secret_or_pii", REFUSAL_SECRET
        if _ASK_MUTATE.search(text):
            return "cannot_alter_backend_values", REFUSAL_MUTATE
        if _ASK_GUARANTEE.search(text):
            return "no_guaranteed_returns", REFUSAL_GUARANTEE
        if _ASK_SECURITY.search(text):
            return "no_specific_securities", REFUSAL_SECURITY
        if _ASK_CANCEL.search(text) and _ASK_ESSENTIAL.search(text):
            return "essential_payment_protected", REFUSAL_ESSENTIAL
        if _ASK_EXECUTE.search(text):
            return "no_execution", REFUSAL_EXECUTE
        if _ASK_INVENT.search(text):
            return "no_invented_data", REFUSAL_INVENT
        if _ASK_UNUSED.search(text):
            return "usage_requires_confirmation", REFUSAL_UNUSED
        return None, COACH_DEFAULT

    @staticmethod
    def _coach_answer(
        question: str, facts: Dict[str, Any], ctx: ValidationContext
    ) -> Tuple[str, List[str]]:
        """Deterministic answers for the questions that are safe to answer."""
        citations = sorted(ctx.allowed_transaction_ids)[:5]

        if _ASK_USAGE.search(question):
            return REFUSAL_UNUSED, citations
        if _ASK_EVIDENCE.search(question):
            if citations:
                return (
                    "The transactions behind this finding are %s. Each one is shown "
                    "with its date and amount under the finding." % ", ".join(citations),
                    citations,
                )
            return (
                "The transactions behind this finding are listed underneath it on "
                "your dashboard, with the date and amount of each one.",
                citations,
            )
        if _ASK_SPEND.search(question) and facts:
            rendered = _compose_generic(facts)
            return rendered, citations
        if facts:
            return _compose_generic(facts), citations
        return COACH_DEFAULT, citations

    # -- §9 step 5: LLM merchant fallback -----------------------------------

    def resolve_merchant(
        self,
        raw: str,
        candidates: Optional[Iterable[str]],
        context: Optional[ValidationContext],
        backend_confidence: Optional[float] = None,
        high_impact: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Rung 5 of the merchant ladder: ask a model to disambiguate.

        Returns **None** when no model was consulted — the caller keeps whatever
        the deterministic ladder produced. That happens when the backend is
        already confident (≥90, §14 "no LLM needed for detection"), when there
        are no candidates to choose between, or when no provider is configured.

        Returns a **dict** whenever a model *was* consulted. `normalized_merchant`
        is None in that dict when nothing was accepted — a rejected response or a
        disagreement between two models. A disagreement is never resolved by
        averaging or by preferring one model: the row goes to review (§14).
        """
        try:
            return self._resolve_merchant(
                raw, candidates, context, backend_confidence, high_impact
            )
        except Exception as exc:  # pragma: no cover - the contract is "never raises"
            logger.warning(
                "ai_resolve_merchant_failed",
                extra={
                    "event": "ai_resolve_merchant_failed",
                    "error_type": type(exc).__name__,
                },
            )
            return None

    def _resolve_merchant(
        self,
        raw: str,
        candidates: Optional[Iterable[str]],
        context: Optional[ValidationContext],
        backend_confidence: Optional[float],
        high_impact: bool,
    ) -> Optional[Dict[str, Any]]:
        options = [str(c).strip() for c in (candidates or []) if str(c).strip()]
        confidence = (
            75.0 if backend_confidence is None else _as_float_confidence(backend_confidence)
        )
        band = _band(confidence)

        # §14: at or above 90 the deterministic resolution stands on its own.
        if band == BAND_CONFIRMED or not options or self.deterministic_only():
            return None

        ctx = self._copy_context(context)
        ctx.allowed_merchants.update(options)
        injection = prompts.contains_injection(raw or "")

        prompt = prompts.merchant_context(raw or "", options, confidence)
        attempt = self._call(ROLE_AMBIGUITY, prompt, MerchantResolution, ctx)

        disagreeing: List[str] = []
        failures = list(attempt.failures)
        errors = list(attempt.errors)
        resolved = None
        model_confidence: Optional[float] = None
        category = None
        explanation = None
        evidence_tokens: List[str] = []
        source = SOURCE_DETERMINISTIC
        provider = None
        model_id = None

        if attempt.accepted:
            disagreement = False
            if high_impact:
                disagreement, second = self._cross_check(
                    ROLE_AMBIGUITY, prompt, MerchantResolution, ctx, attempt
                )
                errors.extend(second.errors)
                failures.extend(second.failures)
                if disagreement:
                    # §14: never average, never pick a side — mark Needs Review.
                    failures.append(validators.MODEL_DISAGREEMENT)
                    disagreeing = [
                        name for name in (attempt.provider, second.provider) if name
                    ]
            if not disagreement:
                proposed = attempt.value
                resolved = proposed.normalized_merchant
                category = proposed.category
                explanation = proposed.explanation
                model_confidence = float(proposed.confidence)
                evidence_tokens = list(proposed.evidence_tokens or [])
                source = SOURCE_LLM
                provider = attempt.provider
                model_id = attempt.model

        review_required = resolved is None or band == BAND_NEEDS_REVIEW or bool(failures)
        result = {
            "normalized_merchant": resolved,
            "category": category,
            "explanation": explanation,
            # The model's own confidence, reported as-is and never blended with
            # the backend's. When two models disagreed there is no number here.
            "model_confidence": model_confidence,
            "backend_confidence": confidence,
            "evidence_tokens": evidence_tokens,
            "candidates": options,
            "disagreeing_providers": disagreeing,
            "review_status": BAND_NEEDS_REVIEW if review_required else BAND_LIKELY,
            "review_required": review_required,
            "source": source,
            "provider": provider,
            "model": model_id,
            "validation_failures": failures,
            "provider_errors": errors,
            "injection_detected": injection,
        }
        self._log("resolve_merchant", result)
        return result

    # -- §6.12 voice --------------------------------------------------------

    def synthesize_voice(self, transcript: str) -> VoiceResult:
        """Read a finished, verified transcript aloud (§14: TTS only).

        The transcript is produced by the backend before this call. The provider
        may return audio for it or fail; it may not return *different words*. If
        the transcript that comes back differs by one character the audio is
        discarded, because audio the user cannot verify against the displayed
        text is exactly how a voice layer would introduce a new amount (§26).
        """
        try:
            text = prompts.redact_text(transcript or "")
            if not text.strip():
                return VoiceResult(
                    transcript=text,
                    provider="unavailable",
                    available=False,
                    fallback_reason="empty_transcript",
                )
            if len(text) > MAX_TRANSCRIPT_CHARS:
                # Truncating would make spoken and displayed text differ (§26).
                return VoiceResult(
                    transcript=text,
                    provider="elevenlabs",
                    available=False,
                    fallback_reason="transcript_too_long",
                )
            if self._tts is None:
                return VoiceResult(
                    transcript=text,
                    provider="unavailable",
                    available=False,
                    fallback_reason="no_tts_provider_configured",
                )

            try:
                result = self._tts.synthesize(text)
            except Exception as exc:
                return VoiceResult(
                    transcript=text,
                    provider="elevenlabs",
                    available=False,
                    fallback_reason=type(exc).__name__,
                )

            if not isinstance(result, VoiceResult):
                return VoiceResult(
                    transcript=text,
                    provider="elevenlabs",
                    available=False,
                    fallback_reason="unexpected_provider_result",
                )
            if (result.transcript or "") != text:
                return VoiceResult(
                    transcript=text,
                    provider=result.provider,
                    model=result.model,
                    available=False,
                    fallback_reason="transcript_modified_by_provider",
                )
            if result.available and not (result.audio_base64 or "").strip():
                return VoiceResult(
                    transcript=text,
                    provider=result.provider,
                    model=result.model,
                    available=False,
                    fallback_reason="empty_audio",
                )
            return result
        except Exception as exc:  # pragma: no cover - the contract is "never raises"
            return VoiceResult(
                transcript=str(transcript or ""),
                provider="unavailable",
                available=False,
                fallback_reason=type(exc).__name__,
            )


# ---------------------------------------------------------------------------
# Module-level accessor
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_default: List[AIRouter] = []


def get_router(settings: Optional[Settings] = None) -> AIRouter:
    """The process-wide router. Cached, and guaranteed never to raise.

    A router that cannot be built from the environment is still a router: the
    fallback instance has no providers configured and therefore runs entirely on
    deterministic templates, which is the product's supported operating mode
    (§3.21).
    """
    if settings is not None:
        try:
            return AIRouter(settings)
        except Exception:  # pragma: no cover - defensive
            return _blank_router()

    with _lock:
        if _default:
            return _default[0]
        try:
            router = AIRouter(load_settings())
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "ai_router_fallback",
                extra={"event": "ai_router_fallback", "error_type": type(exc).__name__},
            )
            router = _blank_router()
        _default.append(router)
        return router


def _blank_router() -> AIRouter:
    """A router with nothing configured — deterministic templates only."""
    router = AIRouter.__new__(AIRouter)
    router.settings = Settings()
    router._llms = []
    router._tts = None
    return router


def reset_router() -> None:
    """Test seam — drop the cached default router."""
    with _lock:
        _default[:] = []
