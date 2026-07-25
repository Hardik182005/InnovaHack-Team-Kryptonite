"""UI string translation — the endpoint behind the language switcher.

The frontend ships curated dictionaries for a handful of languages. For the rest
of the 22 scheduled languages, and for any key added to `strings.ts` after a
dictionary was written, the curated lookup misses and the UI silently falls back
to English. That gap is what this route fills: the browser posts the English
strings it could not resolve and gets machine translations back.

The Google credential stays on the server (§3.16); the browser never sees it.
Results are cached per (language, string), so the second visitor to a language
pays nothing and the switch is instant.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..config import get_logger
from ..dependencies import bad_request
from ..services import translation

logger = get_logger(__name__)

router = APIRouter(prefix="/api/translate", tags=["translate"])

#: One switch of the language selector should be one request. Above this a
#: caller is no longer translating a UI and is using us as a free translation
#: proxy, which is what the cap exists to prevent.
MAX_TEXTS = 200
MAX_CHARS = 600


class TranslateRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1)
    target: str = Field(..., min_length=2, max_length=8)


@router.post("", summary="Translate UI strings into the selected language")
def translate_strings(payload: TranslateRequest) -> Dict[str, Any]:
    target = payload.target.strip().lower()

    if target in ("", "en"):
        # Nothing to do, and worth short-circuiting: English is the source, so a
        # round trip could only ever return the input.
        return {
            "target": "en",
            "translations": [{"text": t, "source": "passthrough"} for t in payload.texts],
            "provider": None,
        }

    if len(payload.texts) > MAX_TEXTS:
        raise bad_request(
            "TOO_MANY_STRINGS",
            "Too many strings in one request (limit %d)." % MAX_TEXTS,
        )
    for text in payload.texts:
        if len(text) > MAX_CHARS:
            raise bad_request(
                "STRING_TOO_LONG",
                "One of the strings is too long to translate (limit %d characters)."
                % MAX_CHARS,
            )

    results = translation.translate_batch(payload.texts, target)
    return {
        "target": target,
        "provider": translation.active_provider(),
        "translations": [{"text": r.text, "source": r.source} for r in results],
    }


@router.get("/status", summary="Whether machine translation is available")
def translate_status() -> Dict[str, Any]:
    """Lets the UI decide whether to bother asking, and never leaks the key."""
    return translation.cache_stats()
