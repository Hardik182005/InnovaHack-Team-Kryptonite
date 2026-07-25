"""ElevenLabs adapter — text-to-speech only (§6.12, §14).

The transcript is produced by the backend from verified values *before* this
adapter is called. ElevenLabs is never asked to write, summarize or alter
financial content; it receives a finished string and returns audio.

When the provider is unavailable the caller still gets a `VoiceResult` carrying
the transcript, so the UI degrades to a readable summary instead of an error
(§6.12 "quota/error fallback", §3.21).
"""

from __future__ import annotations

import base64

from ..config import ElevenLabsConfig
from .base import ProviderStatus, TTSProvider, VoiceResult


class ElevenLabsProvider(TTSProvider):
    def __init__(self, config: ElevenLabsConfig) -> None:
        self.config = config
        self._last_error = None

    def status(self) -> ProviderStatus:
        if not self.config.api_key:
            detail = "no_api_key_configured"
        elif not self.config.voice_id:
            detail = "no_voice_id_configured"
        elif not self.config.model_id:
            detail = "no_model_id_configured"
        else:
            detail = self._last_error or "ready"
        return ProviderStatus(
            name="elevenlabs",
            configured=self.config.configured,
            available=self.config.configured and self._last_error is None,
            model=self.config.model_id,
            detail=detail,
            roles=["text_to_speech"],
        )

    def synthesize(self, transcript: str) -> VoiceResult:
        """Render `transcript` to audio, or return a transcript-only fallback."""
        if not self.config.configured:
            return VoiceResult(
                transcript=transcript,
                provider="elevenlabs",
                available=False,
                fallback_reason=self.status().detail,
            )

        try:
            import httpx

            response = httpx.post(
                "%s/text-to-speech/%s"
                % (self.config.base_url.rstrip("/"), self.config.voice_id),
                headers={
                    "xi-api-key": self.config.api_key or "",
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={"text": transcript, "model_id": self.config.model_id},
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            audio = base64.b64encode(response.content).decode("ascii")
        except Exception as exc:  # network, quota, HTTP status
            self._last_error = type(exc).__name__
            return VoiceResult(
                transcript=transcript,
                provider="elevenlabs",
                model=self.config.model_id,
                available=False,
                fallback_reason=type(exc).__name__,
            )

        self._last_error = None
        return VoiceResult(
            transcript=transcript,
            audio_base64=audio,
            content_type="audio/mpeg",
            provider="elevenlabs",
            model=self.config.model_id,
            available=True,
        )
