"""Groq adapter — §14 role: fast explanation and drafting.

Groq is the *phrasing* provider: dashboard summaries, insight wording, action
drafts and AI Coach replies. It is never asked to compute anything, and its
output is rejected outright if it states a number the backend did not calculate.
"""

from __future__ import annotations

from typing import Dict, Optional

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
        # Try the primary credential, then the spare. Only a credential-shaped
        # rejection is worth retrying: 401/403 means this key is dead and 429
        # means it is exhausted, and in both cases the other key may still
        # work. Any other status is a real error and is raised immediately, so
        # a malformed prompt is not silently sent twice.
        keys = self.config.api_keys or [self.config.api_key]
        last_error: Optional[Exception] = None
        for index, key in enumerate(keys):
            response = httpx.post(
                "%s/chat/completions" % self.config.base_url.rstrip("/"),
                headers={
                    "Authorization": "Bearer %s" % key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.config.timeout_seconds,
            )
            if response.status_code in (401, 403, 429) and index < len(keys) - 1:
                last_error = httpx.HTTPStatusError(
                    "groq credential rejected with %s" % response.status_code,
                    request=response.request,
                    response=response,
                )
                continue
            break
        if last_error is not None and response.status_code in (401, 403, 429):
            raise ProviderUnavailable(self.name, "all_credentials_rejected")
        response.raise_for_status()
        body = response.json()
        try:
            return body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderUnavailable(self.name, "unexpected_response_shape")
