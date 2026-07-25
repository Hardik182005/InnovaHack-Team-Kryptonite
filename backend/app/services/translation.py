"""Machine translation for UI strings — the fallback behind the curated dictionaries.

Why this lives on the backend: §3.16 forbids an API key in frontend code. The
browser asks *this* service for translations; the Google credential never leaves
the server.

Order of resolution, cheapest and most trustworthy first:

  1. curated translation shipped in the frontend  (reviewed wording)
  2. this service's cache                          (already translated once)
  3. Google Cloud Translation                      (only when a key is set)
  4. English                                       (always available)

Financial vocabulary is deliberately *not* left to a machine. A curated string
always wins, and terms in `PROTECTED_TERMS` are shielded from translation
entirely, because a mistranslated "Safe Spare" or "EMI" would misinform exactly
the users this feature exists to serve.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..config import get_logger

logger = get_logger(__name__)

CALCULATION_VERSION = "translation.v1"

GOOGLE_ENDPOINT = "https://translation.googleapis.com/language/translate/v2"

#: Never handed to a translator. Product names, currency codes and units whose
#: meaning would be damaged by translation.
PROTECTED_TERMS = (
    "SafeSpare", "Safe Spare", "UPI", "EMI", "NEFT", "IMPS", "RTGS",
    "PDF", "CSV", "XLSX", "AI", "INR", "SMS", "OTP", "KYC",
)

#: Anything matching these is passed through untouched: amounts, dates,
#: percentages and placeholders must never be "translated".
_PRESERVE = re.compile(
    r"(₹[\d,]+(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?%?|\{\w+\}|https?://\S+)"
)


@dataclass
class TranslationResult:
    text: str
    source: str          # "google" | "cache" | "passthrough"
    language: str
    cached: bool = False


@dataclass
class _Cache:
    """Process-local cache. A real deployment would back this with DynamoDB.

    Keyed on (language, sha1(text)) so the same string is never paid for twice.
    """

    data: Dict[str, str] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @staticmethod
    def key(language: str, text: str) -> str:
        return "%s:%s" % (language, hashlib.sha1(text.encode("utf-8")).hexdigest())

    def get(self, language: str, text: str) -> Optional[str]:
        with self.lock:
            return self.data.get(self.key(language, text))

    def put(self, language: str, text: str, value: str) -> None:
        with self.lock:
            if len(self.data) > 20000:      # crude bound; entries are small
                self.data.clear()
            self.data[self.key(language, text)] = value


_cache = _Cache()


def _api_key() -> Optional[str]:
    """Read the credential at call time so a restart is not needed to add one."""
    return os.environ.get("GOOGLE_TRANSLATE_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def is_configured() -> bool:
    return bool(_api_key())


def _mask(text: str) -> tuple:
    """Replace amounts, numbers and protected terms with placeholders.

    Returns (masked_text, restore_map). Translators reorder and re-case words;
    without masking, "₹31,240" can come back as "31,240 ₹" or a term like EMI
    can be expanded into something meaningless.
    """
    restore: Dict[str, str] = {}
    masked = text
    index = 0

    for term in PROTECTED_TERMS:
        if term in masked:
            token = "%d" % index
            restore[token] = term
            masked = masked.replace(term, token)
            index += 1

    def swap(match):
        nonlocal index
        token = "%d" % index
        restore[token] = match.group(0)
        index += 1
        return token

    masked = _PRESERVE.sub(swap, masked)
    return masked, restore


def _unmask(text: str, restore: Dict[str, str]) -> str:
    for token, original in restore.items():
        text = text.replace(token, original)
    return text


def translate_batch(texts: List[str], target: str) -> List[TranslationResult]:
    """Translate a batch. Never raises — an untranslatable string returns as-is.

    Batching matters: one request for 40 strings rather than 40 requests is the
    difference between a usable language switch and a visibly slow one.
    """
    results: List[Optional[TranslationResult]] = [None] * len(texts)
    pending: List[int] = []

    for i, text in enumerate(texts):
        if not text or not text.strip():
            results[i] = TranslationResult(text, "passthrough", target)
            continue
        hit = _cache.get(target, text)
        if hit is not None:
            results[i] = TranslationResult(hit, "cache", target, cached=True)
        else:
            pending.append(i)

    if pending and is_configured():
        masked_pairs = [_mask(texts[i]) for i in pending]
        try:
            translated = _call_google([m for m, _ in masked_pairs], target)
            for slot, raw, (_, restore) in zip(pending, translated, masked_pairs):
                final = _unmask(raw, restore)
                _cache.put(target, texts[slot], final)
                results[slot] = TranslationResult(final, "google", target)
        except Exception as exc:  # provider failure must never break the UI
            logger.warning(
                "translation_unavailable",
                extra={"event": "translation_unavailable", "detail": type(exc).__name__},
            )

    # Anything still unresolved falls back to the original text.
    for i, value in enumerate(results):
        if value is None:
            results[i] = TranslationResult(texts[i], "passthrough", target)

    return [r for r in results if r is not None]


def _call_google(texts: List[str], target: str) -> List[str]:
    """POST to Google Cloud Translation v2. Raises on any failure."""
    import httpx

    key = _api_key()
    if not key:
        raise RuntimeError("no translation key configured")

    response = httpx.post(
        GOOGLE_ENDPOINT,
        params={"key": key},
        json={"q": texts, "target": target, "format": "text"},
        timeout=12.0,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("data", {}).get("translations", [])
    if len(items) != len(texts):
        raise RuntimeError("translation count mismatch")
    return [item.get("translatedText", "") for item in items]


def cache_stats() -> Dict[str, object]:
    with _cache.lock:
        return {
            "entries": len(_cache.data),
            "configured": is_configured(),
            "provider": "google_cloud_translation_v2" if is_configured() else None,
        }
