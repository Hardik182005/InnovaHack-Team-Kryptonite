"""Gemini adapter — §14 role: ambiguity resolution and extraction fallback.

Used only for the 70-89 confidence band (§14 routing). It never produces a
number that reaches the user: its output is schema-parsed and content-checked by
`validators.py` before anything is stored.
"""

from __future__ import annotations

from typing import Dict

from ..config import ProviderConfig
from .base import LLMProvider, ProviderUnavailable


class GeminiProvider(LLMProvider):
    roles = [
        "multimodal_extraction_fallback",
        "ambiguous_merchant",
        "ambiguous_classification",
    ]

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)

    def _invoke(self, prompt: Dict[str, str], model: str, max_tokens: int) -> str:
        try:
            import httpx
        except ImportError:  # pragma: no cover - httpx is a declared dependency
            raise ProviderUnavailable(self.name, "httpx_not_installed")

        url = "%s/models/%s:generateContent" % (self.config.base_url.rstrip("/"), model)
        payload = {
            "systemInstruction": {"parts": [{"text": prompt["system"]}]},
            "contents": [{"role": "user", "parts": [{"text": prompt["user"]}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        response = httpx.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.config.api_key or "",
            },
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        try:
            parts = body["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError):
            raise ProviderUnavailable(self.name, "unexpected_response_shape")
