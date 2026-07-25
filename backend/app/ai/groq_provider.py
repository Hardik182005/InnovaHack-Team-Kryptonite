"""Groq adapter — §14 role: fast explanation and drafting.

Groq is the *phrasing* provider: dashboard summaries, insight wording, action
drafts and AI Coach replies. It is never asked to compute anything, and its
output is rejected outright if it states a number the backend did not calculate.
"""

from __future__ import annotations

from typing import Dict

from ..config import ProviderConfig
from .base import LLMProvider, ProviderUnavailable


class GroqProvider(LLMProvider):
    roles = ["explanations", "summaries", "action_drafts", "ai_coach"]

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)

    def _invoke(self, prompt: Dict[str, str], model: str, max_tokens: int) -> str:
        try:
            import httpx
        except ImportError:  # pragma: no cover - httpx is a declared dependency
            raise ProviderUnavailable(self.name, "httpx_not_installed")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        response = httpx.post(
            "%s/chat/completions" % self.config.base_url.rstrip("/"),
            headers={
                "Authorization": "Bearer %s" % self.config.api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        try:
            return body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderUnavailable(self.name, "unexpected_response_shape")
