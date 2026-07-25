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

from ..config import get_logger, is_placeholder

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


def _model(name: str, default: str) -> str:
    """A model id from the environment, ignoring deployment stubs.

    `os.environ.get(name) or default` is not enough: SSM hands the container
    `OPENAI_MODEL=REPLACE_ME`, which is truthy, so the default never fires and
    every request 404s on a model that does not exist.
    """
    value = (os.environ.get(name) or "").strip()
    return default if not value or is_placeholder(value) else value


def _api_key() -> Optional[str]:
    """Read the credential at call time so a restart is not needed to add one."""
    return _env_key("GOOGLE_TRANSLATE_API_KEY", "GOOGLE_API_KEY")


#: A credential shorter than this is a placeholder, not a key. SSM is seeded
#: with stub values for providers that were never signed up for, and treating
#: those as configured makes every translation call fail with a 400 instead of
#: cleanly falling through to a provider that actually works.
_MIN_KEY_LENGTH = 20


def _env_key(*names: str) -> Optional[str]:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if len(value) >= _MIN_KEY_LENGTH and not is_placeholder(value):
            return value
    return None


def _gemini_key() -> Optional[str]:
    """Google's other translation endpoint.

    Cloud Translation is a separate, separately-billed API: a Google AI Studio
    key authorises `generativelanguage.googleapis.com` but not
    `translation.googleapis.com`. Both are Google translation; only the
    endpoint and the billing differ.
    """
    return _env_key("GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY")


def _openai_key() -> Optional[str]:
    return _env_key("OPENAI_API_KEY")


def _groq_key() -> Optional[str]:
    return _env_key("GROQ_API_KEY", "GROQ_FALLBACK_API_KEY")


#: Ordered best-first. Google proper wins whenever a key for it exists; the
#: rest are here so the language switcher works on a deployment that has not
#: been given one, rather than silently serving English in 20 languages.
_PROVIDER_ORDER = (
    ("google_cloud_translation_v2", _api_key),
    ("gemini", _gemini_key),
    ("openai", _openai_key),
    ("groq", _groq_key),
)


def available_providers() -> List[str]:
    """Every provider holding a usable-looking credential, best first.

    Plural on purpose. A key being *present* says nothing about it being
    *accepted* — the deployed OpenAI key was well-formed, 164 characters, and
    401d on every call, which took translation down even though a working Groq
    key sat right behind it. Having the list means a rejected credential costs
    one wasted request rather than the whole feature.
    """
    return [name for name, key_fn in _PROVIDER_ORDER if key_fn()]


def active_provider() -> Optional[str]:
    """The provider that will be tried first."""
    providers = available_providers()
    return providers[0] if providers else None


def is_configured() -> bool:
    return active_provider() is not None


def _mask(text: str) -> tuple:
    """Replace amounts, numbers and protected terms with placeholders.

    Returns (masked_text, restore_map). Translators reorder and re-case words;
    without masking, "₹31,240" can come back as "31,240 ₹" or a term like EMI
    can be expanded into something meaningless.
    """
    restore: Dict[str, str] = {}
    index = 0

    def next_token() -> str:
        # Visible ASCII, deliberately. This used to wrap the index in private-use
        # code points (U+E000/U+E001) on the theory that nothing would translate
        # them — but models strip characters they cannot render, so the sentinels
        # came back gone and "Safe Spare" arrived as the bare digit "0". A token
        # only works if the model can see it, and "[[0]]" is unmistakably not a
        # word to translate.
        #
        # Brackets also make unmasking safe: "[[1]]" is not a substring of
        # "[[10]]", so restoring one token cannot rewrite the inside of another.
        return "[[%d]]" % index

    # Amounts and numbers first, while the text still holds no token of our own
    # for the number pattern to match.
    def swap(match):
        nonlocal index
        key = next_token()
        restore[key] = match.group(0)
        index += 1
        return key

    masked = _PRESERVE.sub(swap, text)

    for term in PROTECTED_TERMS:
        if term in masked:
            key = next_token()
            restore[key] = term
            masked = masked.replace(term, key)
            index += 1

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

    if pending:
        masked_pairs = [_mask(texts[i]) for i in pending]
        masked = [m for m, _ in masked_pairs]

        # Try each configured provider in turn. A provider failure must never
        # break the UI, and must not take the next provider down with it: the
        # only outcome worse than a slow language switch is an English one.
        for provider in available_providers():
            try:
                translated = _call_provider(masked, target, provider)
            except Exception as exc:
                # The type alone, never the body — a provider error can echo the
                # prompt back (§22).
                logger.warning(
                    "translation_unavailable",
                    extra={
                        "event": "translation_unavailable",
                        "provider": provider,
                        "detail": type(exc).__name__,
                    },
                )
                continue
            for slot, raw, (_, restore) in zip(pending, translated, masked_pairs):
                final = _unmask(raw, restore)
                _cache.put(target, texts[slot], final)
                results[slot] = TranslationResult(final, provider, target)
            break

    # Anything still unresolved falls back to the original text.
    for i, value in enumerate(results):
        if value is None:
            results[i] = TranslationResult(texts[i], "passthrough", target)

    return [r for r in results if r is not None]



def _call_provider(texts: List[str], target: str, provider: str) -> List[str]:
    """Dispatch to one provider. Raises on any failure, for the caller to catch."""
    if provider == "google_cloud_translation_v2":
        return _call_google(texts, target)
    if provider == "gemini":
        return _call_gemini(texts, target)
    return _call_chat(texts, target, provider)

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


#: Gemini is a chat model, so the contract has to be stated explicitly or it
#: will "helpfully" explain, re-order or drop items. A JSON array in and a JSON
#: array out is the only shape that survives batching.
_GEMINI_INSTRUCTION = (
    "Translate each string in the JSON array below into the language with BCP-47 "
    "code '%s'. This is a personal-finance app for Indian users.\n"
    "Rules:\n"
    "- Return ONLY a JSON array of strings, same length and same order as the input.\n"
    "- Translate nothing else: no commentary, no markdown, no code fences.\n"
    "- Copy every token of the form [[0]], [[1]], [[2]] ... through exactly as it "
    "appears, brackets included. They are placeholders for amounts, dates and "
    "product names. Never translate, renumber, reformat or drop one.\n"
    "- Keep the register plain and everyday, as a bank would speak to a customer.\n"
    "- If a string is already in the target language, return it unchanged.\n"
    '- Wrap the array as {"translations": [...]} if you must return an object.\n\n'
    "Input:\n%s"
)


def _gemini_model() -> str:
    return _model("GEMINI_MODEL", "gemini-2.0-flash")


def _call_gemini(texts: List[str], target: str) -> List[str]:
    """Translate a batch with Gemini. Raises on any failure.

    Same contract as `_call_google`: same length, same order, or raise. Callers
    fall back to the original English, which is always safe to display.
    """
    import httpx

    key = _gemini_key()
    if not key:
        raise RuntimeError("no translation key configured")

    prompt = _GEMINI_INSTRUCTION % (target, json.dumps(texts, ensure_ascii=False))
    response = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
        % _gemini_model(),
        params={"key": key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            # temperature 0: a translation is a lookup, not a creative act, and
            # the same string must not drift between requests.
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        },
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()

    try:
        raw = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError("gemini returned no content") from exc

    items = json.loads(raw)
    if not isinstance(items, list) or len(items) != len(texts):
        raise RuntimeError("translation count mismatch")
    return [str(item) for item in items]


#: OpenAI and Groq both speak the OpenAI chat-completions shape, so one client
#: covers both; only the base URL, model and key differ.
_CHAT_PROVIDERS = {
    "openai": (
        "https://api.openai.com/v1/chat/completions",
        lambda: _model("OPENAI_MODEL", "gpt-4o-mini"),
        _openai_key,
    ),
    "groq": (
        "https://api.groq.com/openai/v1/chat/completions",
        lambda: _model("GROQ_MODEL", "llama-3.3-70b-versatile"),
        _groq_key,
    ),
}


def _call_chat(texts: List[str], target: str, provider: str) -> List[str]:
    """Translate a batch via an OpenAI-compatible chat endpoint."""
    import httpx

    config = _CHAT_PROVIDERS.get(provider)
    if config is None:
        raise RuntimeError("unknown translation provider: %s" % provider)
    url, model_fn, key_fn = config
    key = key_fn()
    if not key:
        raise RuntimeError("no translation key configured")

    response = httpx.post(
        url,
        headers={"Authorization": "Bearer %s" % key},
        json={
            "model": model_fn(),
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a translation engine. You reply with JSON only: "
                        '{"translations": [...]}, one entry per input string, in '
                        "the same order. You never explain and never add text."
                    ),
                },
                {
                    "role": "user",
                    "content": _GEMINI_INSTRUCTION
                    % (target, json.dumps(texts, ensure_ascii=False)),
                },
            ],
        },
        timeout=25.0,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]

    parsed = json.loads(content)
    items = parsed.get("translations") if isinstance(parsed, dict) else parsed
    if not isinstance(items, list) or len(items) != len(texts):
        raise RuntimeError("translation count mismatch")
    return [str(item) for item in items]


def cache_stats() -> Dict[str, object]:
    with _cache.lock:
        return {
            "entries": len(_cache.data),
            "configured": is_configured(),
            "provider": active_provider(),
            # The whole chain, because "provider" alone is the one that is tried
            # first, not necessarily the one that answered.
            "providers": available_providers(),
        }
