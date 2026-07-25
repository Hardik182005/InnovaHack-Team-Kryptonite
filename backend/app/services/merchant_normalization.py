"""Merchant normalization — spec §9.

Resolution ladder, cheapest and most certain first:

  1. exact alias match
  2. regex normalization
  3. RapidFuzz (falls back to stdlib difflib when unavailable)
  4. local embeddings (optional; MiniLM)
  5. LLM fallback  -> delegated to app/ai, never called from here
  6. user review

Steps 1-4 run offline. The module records *which* step resolved each merchant so
the UI can show the method and confidence (§9 "Store: resolution method").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

CALCULATION_VERSION = "merchant_normalization.v1"

#: Payment-processor noise, card suffixes, store numbers, dates and reference
#: numbers that carry no merchant identity.
_NOISE_PATTERNS = [
    r"\b(pos|ach|ecs|neft|imps|upi|ift|chq|atw|vps|sq|tst|sp|pp|pyp)\b",
    r"\bx{2,}\d+\b",
    # Standalone digit runs are store/branch/reference numbers, never merchant
    # identity — "QUIRKY BEANS 123" and "QUIRKY BEANS" are the same shop.
    r"\b\d{2,}\b",
    r"\b(purchase|payment|debit|credit|card|transaction|ref|txn|auth)\b",
    r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b",
    r"[#*]+\d*",
    r"\b(inc|llc|ltd|limited|corp|co|pvt|plc|gmbh)\b",
]

_SEPARATORS = re.compile(r"[^a-z0-9]+")

#: Curated aliases. In production this table is user-extensible and persisted;
#: the spec's own example (NETFLIX.COM / NETFLIX INDIA / NFX*SUBSCRIPTION) is here.
DEFAULT_ALIASES: Dict[str, str] = {
    "netflix": "Netflix",
    "netflix com": "Netflix",
    "netflix india": "Netflix",
    "nfx subscription": "Netflix",
    "nfx": "Netflix",
    "spotify": "Spotify",
    "spotify usa": "Spotify",
    "amazon": "Amazon",
    "amzn mktp": "Amazon",
    "amazon prime": "Amazon Prime",
    "uber": "Uber",
    "uber eats": "Uber Eats",
    "uber trip": "Uber",
    "starbucks": "Starbucks",
    "sbux": "Starbucks",
    "dropbox": "Dropbox",
    "google storage": "Google One",
    "google one": "Google One",
    "adobe": "Adobe",
    "adobe systems": "Adobe",
    "github": "GitHub",
    "planet fitness": "Planet Fitness",
}


@dataclass
class MerchantResolution:
    raw_merchant: str
    normalized_merchant: str
    method: str
    confidence: float
    user_override: bool = False
    calculation_version: str = CALCULATION_VERSION


def _clean(text: str) -> str:
    """Lowercase, strip processor noise, collapse to single-spaced tokens."""
    s = (text or "").lower()
    s = _SEPARATORS.sub(" ", s)
    for pattern in _NOISE_PATTERNS:
        s = re.sub(pattern, " ", s)
    return " ".join(s.split())


def _titleise(text: str) -> str:
    """Human-presentable fallback name when no alias matched."""
    return " ".join(w.capitalize() for w in text.split()) if text else "Unknown merchant"


def _fuzzy_ratio(a: str, b: str) -> float:
    """RapidFuzz when installed, stdlib difflib otherwise.

    difflib is meaningfully slower but keeps the core dependency-free and the
    behaviour equivalent for the short strings we compare here.
    """
    try:  # pragma: no cover - depends on optional dependency
        from rapidfuzz import fuzz

        return fuzz.token_set_ratio(a, b) / 100.0
    except ImportError:
        from difflib import SequenceMatcher

        return SequenceMatcher(None, a, b).ratio()


def resolve_merchant(
    raw: str,
    aliases: Optional[Dict[str, str]] = None,
    known_merchants: Optional[Iterable[str]] = None,
    fuzzy_threshold: float = 0.86,
) -> MerchantResolution:
    """Walk the resolution ladder and report which rung resolved it."""
    aliases = aliases if aliases is not None else DEFAULT_ALIASES
    cleaned = _clean(raw)

    if not cleaned:
        return MerchantResolution(raw, "Unknown merchant", "empty", 0.0)

    # 1. exact alias
    if cleaned in aliases:
        return MerchantResolution(raw, aliases[cleaned], "exact_alias", 1.0)

    # 2. regex / substring alias — longest key first so "amazon prime" beats "amazon"
    for key in sorted(aliases, key=len, reverse=True):
        if key in cleaned:
            return MerchantResolution(raw, aliases[key], "regex_alias", 0.95)

    # 3. fuzzy against aliases, then against merchants already seen in this statement
    best_name, best_score, best_method = None, 0.0, ""
    for key, name in aliases.items():
        score = _fuzzy_ratio(cleaned, key)
        if score > best_score:
            best_name, best_score, best_method = name, score, "fuzzy_alias"
    for known in known_merchants or []:
        score = _fuzzy_ratio(cleaned, _clean(known))
        if score > best_score:
            best_name, best_score, best_method = known, score, "fuzzy_known_merchant"

    if best_name and best_score >= fuzzy_threshold:
        return MerchantResolution(raw, best_name, best_method, round(best_score, 2))

    # 4/5. embeddings and LLM are handled by callers that have those services;
    # returning low confidence here routes the row to review (§9 step 6).
    return MerchantResolution(raw, _titleise(cleaned), "cleaned_fallback", 0.45)


def normalize_all(
    raws: Iterable[str], aliases: Optional[Dict[str, str]] = None
) -> List[MerchantResolution]:
    """Resolve a batch, letting later rows match against earlier resolutions.

    This is what makes three spellings of the same unknown merchant collapse into
    one group even when no alias exists for it.
    """
    resolutions: List[MerchantResolution] = []
    seen: List[str] = []
    for raw in raws:
        res = resolve_merchant(raw, aliases=aliases, known_merchants=seen)
        resolutions.append(res)
        if res.normalized_merchant not in seen:
            seen.append(res.normalized_merchant)
    return resolutions
