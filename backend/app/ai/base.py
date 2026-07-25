"""Provider adapter interface — spec §14.

One interface, four adapters, zero direct provider calls in business logic. A
route or service that wants model help asks `AIRouter`; the router asks a
`LLMProvider`. Nothing else in the codebase imports httpx or a provider SDK.

Availability is a first-class concept: `ProviderStatus` is what `/ready` reports
and what makes "all providers down" a normal operating mode rather than an
error (§3.21, §14 "Do not crash because one provider is unavailable").
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import ProviderConfig


class ProviderUnavailable(RuntimeError):
    """Raised when a provider has no credentials, no model ID, or fails a call.

    Always caught by the router, which then falls back to the next provider and
    finally to a deterministic template.
    """

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__("%s unavailable: %s" % (provider, reason))
        self.provider = provider
        self.reason = reason


@dataclass
class ProviderStatus:
    """Safe-to-log health record. Contains identifiers and states only."""

    name: str
    configured: bool
    available: bool
    model: Optional[str] = None
    fallback_model: Optional[str] = None
    detail: str = ""
    roles: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "configured": self.configured,
            "available": self.available,
            "model": self.model,
            "fallback_model": self.fallback_model,
            "detail": self.detail,
            "roles": list(self.roles),
        }


@dataclass
class ProviderResponse:
    """Raw text from a provider, plus the identifiers we are allowed to log."""

    provider: str
    model: str
    text: str
    latency_ms: int = 0
    used_fallback_model: bool = False


@dataclass
class VoiceResult:
    """Text-to-speech outcome. Transcript is always present; audio may not be."""

    transcript: str
    audio_base64: Optional[str] = None
    content_type: Optional[str] = None
    provider: str = "unavailable"
    model: Optional[str] = None
    available: bool = False
    fallback_reason: Optional[str] = None


class LLMProvider(ABC):
    """A text-in / JSON-text-out model adapter."""

    #: Which §14 roles this provider is preferred for.
    roles: List[str] = []

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._last_error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def configured(self) -> bool:
        return self.config.configured

    def status(self) -> ProviderStatus:
        """Credential/model validation, performed at startup and on /ready (§14)."""
        if not self.config.has_credentials:
            detail = "no_api_key_configured"
        elif not self.config.active_model:
            detail = "no_model_id_configured"
        else:
            detail = self._last_error or "ready"
        return ProviderStatus(
            name=self.name,
            configured=self.config.configured,
            available=self.config.configured and self._last_error is None,
            model=self.config.model,
            fallback_model=self.config.fallback_model,
            detail=detail,
            roles=list(self.roles),
        )

    def _require_configured(self) -> str:
        if not self.config.has_credentials:
            raise ProviderUnavailable(self.name, "no_api_key_configured")
        model = self.config.active_model
        if not model:
            raise ProviderUnavailable(self.name, "no_model_id_configured")
        return model

    def complete_json(self, prompt: Dict[str, str], max_tokens: int = 700) -> ProviderResponse:
        """Send a `{system, user}` prompt and return the raw response text.

        Timing and error bookkeeping live here so each adapter only implements
        the transport.
        """
        model = self._require_configured()
        started = time.time()
        try:
            text = self._invoke(prompt, model, max_tokens)
        except ProviderUnavailable:
            raise
        except Exception as exc:  # network, decode, HTTP status
            # Only the exception type is retained: a provider error body can
            # contain the prompt, which may contain financial detail (§22).
            self._last_error = type(exc).__name__
            raise ProviderUnavailable(self.name, type(exc).__name__)
        self._last_error = None
        return ProviderResponse(
            provider=self.name,
            model=model,
            text=text,
            latency_ms=int((time.time() - started) * 1000),
            used_fallback_model=model != self.config.model,
        )

    @abstractmethod
    def _invoke(self, prompt: Dict[str, str], model: str, max_tokens: int) -> str:
        """Transport-specific call. Must return the model's raw text."""


class TTSProvider(ABC):
    """Text-to-speech only (§14: ElevenLabs is never used to generate content)."""

    @abstractmethod
    def status(self) -> ProviderStatus:
        ...

    @abstractmethod
    def synthesize(self, transcript: str) -> VoiceResult:
        ...
