"""Application settings and structured logging — §15, §17, §22.

Every provider model ID comes from an environment variable with **no default**
(§14: "Use environment-variable model IDs. Do not permanently hardcode
assumptions about current model availability."). A provider with no key, or a
key but no model ID, is simply reported as not configured; nothing raises and
nothing crashes (§14.6, §3.21).

Logging is JSON, carries the request ID, and passes every record through the
same PII redactor used for prompts, so an account number cannot reach a log file
even if a careless caller interpolates a raw description (§22, §25.18).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

from .ai.prompts import redact_text

#: Populated by the request-ID middleware; read by the log formatter.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_TRUE = {"1", "true", "yes", "on", "y"}


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    return default if raw is None else raw.lower() in _TRUE


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = _env(name)
    if raw is None:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class ProviderConfig:
    """One LLM provider's credentials and model IDs. Never logged."""

    name: str
    api_key: Optional[str]
    model: Optional[str]
    fallback_model: Optional[str]
    base_url: str
    timeout_seconds: float = 20.0
    #: Second credential, tried only when the primary is rejected or rate
    #: limited (401/403/429). Distinct from fallback_model, which switches
    #: model on the same key.
    fallback_api_key: Optional[str] = None

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key)

    @property
    def api_keys(self) -> List[str]:
        """Credentials to try in order, de-duplicated, blanks dropped."""
        ordered = [k for k in (self.api_key, self.fallback_api_key) if k]
        return list(dict.fromkeys(ordered))

    @property
    def active_model(self) -> Optional[str]:
        """Primary model, else the configured fallback, else nothing."""
        return self.model or self.fallback_model

    @property
    def configured(self) -> bool:
        """A provider is usable only with both a key and a model identifier."""
        return bool(self.api_key and self.active_model)

    def describe(self) -> Dict[str, Any]:
        """Safe-to-log description: identifiers and status only, never secrets."""
        return {
            "provider": self.name,
            "credentials_present": self.has_credentials,
            "fallback_credentials_present": bool(self.fallback_api_key),
            "model": self.model or None,
            "fallback_model": self.fallback_model or None,
            "configured": self.configured,
        }


@dataclass(frozen=True)
class ElevenLabsConfig:
    api_key: Optional[str]
    voice_id: Optional[str]
    model_id: Optional[str]
    base_url: str = "https://api.elevenlabs.io/v1"
    timeout_seconds: float = 30.0

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.voice_id and self.model_id)

    def describe(self) -> Dict[str, Any]:
        return {
            "provider": "elevenlabs",
            "credentials_present": bool(self.api_key),
            "voice_id_present": bool(self.voice_id),
            "model": self.model_id or None,
            "configured": self.configured,
        }


@dataclass(frozen=True)
class Settings:
    app_name: str = "SafeSpare AI"
    version: str = "0.4.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # §17 restricted CORS — an explicit allowlist, never "*".
    cors_allow_origins: List[str] = field(default_factory=list)

    # §17 rate limiting (fixed window per client per window).
    rate_limit_requests: int = 240
    rate_limit_window_seconds: int = 60

    # §22 upload safety.
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_upload_extensions: FrozenSet[str] = frozenset(
        {".csv", ".txt", ".pdf", ".xlsx", ".xls"}
    )
    allowed_upload_content_types: FrozenSet[str] = frozenset(
        {
            "text/csv",
            "text/plain",
            "application/csv",
            "application/pdf",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/octet-stream",
        }
    )
    upload_url_ttl_seconds: int = 900

    demo_statement_path: str = ""

    openai: ProviderConfig = field(
        default_factory=lambda: ProviderConfig("openai", None, None, None, "")
    )
    gemini: ProviderConfig = field(
        default_factory=lambda: ProviderConfig("gemini", None, None, None, "")
    )
    groq: ProviderConfig = field(
        default_factory=lambda: ProviderConfig("groq", None, None, None, "")
    )
    elevenlabs: ElevenLabsConfig = field(
        default_factory=lambda: ElevenLabsConfig(None, None, None)
    )

    def provider_status(self) -> List[Dict[str, Any]]:
        return [
            self.openai.describe(),
            self.gemini.describe(),
            self.groq.describe(),
            self.elevenlabs.describe(),
        ]

    @property
    def any_llm_configured(self) -> bool:
        return any((self.openai.configured, self.gemini.configured, self.groq.configured))


def _default_demo_path() -> str:
    """Where to find the synthetic demo statement (§23).

    The packaged copy at ``app/data/demo_statement.csv`` is preferred and is the
    only one that exists in the container image: the backend image is built with
    ``backend/`` as its build context (see infra/scripts/deploy.sh), so the repo
    root's ``demo_data/`` is outside the context and never ships. Anything the
    service needs at *runtime* therefore has to live under ``backend/``.

    The repo-root ``demo_data/`` copy is kept as a fallback so a source checkout
    that has only run ``scripts/generate_demo_statement.py`` still works.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    packaged = os.path.join(here, "data", "demo_statement.csv")
    if os.path.exists(packaged):
        return packaged
    repo_root = os.path.dirname(os.path.dirname(here))
    return os.path.join(repo_root, "demo_data", "demo_statement.csv")


def load_settings() -> Settings:
    """Read settings from the environment. Called once at import of `dependencies`."""
    return Settings(
        app_name=_env("APP_NAME", "SafeSpare AI"),
        version=_env("APP_VERSION", "0.4.0"),
        environment=_env("ENVIRONMENT", "development"),
        debug=_env_bool("DEBUG", False),
        log_level=_env("LOG_LEVEL", "INFO").upper(),
        cors_allow_origins=_env_list(
            "CORS_ALLOW_ORIGINS",
            ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
        ),
        rate_limit_requests=_env_int("RATE_LIMIT_REQUESTS", 240),
        rate_limit_window_seconds=_env_int("RATE_LIMIT_WINDOW_SECONDS", 60),
        max_upload_bytes=_env_int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
        upload_url_ttl_seconds=_env_int("UPLOAD_URL_TTL_SECONDS", 900),
        demo_statement_path=_env("DEMO_STATEMENT_PATH", _default_demo_path()),
        openai=ProviderConfig(
            name="openai",
            api_key=_env("OPENAI_API_KEY"),
            model=_env("OPENAI_MODEL"),
            fallback_model=_env("OPENAI_FALLBACK_MODEL"),
            base_url=_env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            timeout_seconds=_env_float("OPENAI_TIMEOUT_SECONDS", 20.0),
        ),
        gemini=ProviderConfig(
            name="gemini",
            api_key=_env("GEMINI_API_KEY"),
            model=_env("GEMINI_MODEL"),
            fallback_model=_env("GEMINI_FALLBACK_MODEL"),
            base_url=_env(
                "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
            ),
            timeout_seconds=_env_float("GEMINI_TIMEOUT_SECONDS", 20.0),
        ),
        groq=ProviderConfig(
            name="groq",
            api_key=_env("GROQ_API_KEY"),
            fallback_api_key=_env("GROQ_FALLBACK_API_KEY"),
            model=_env("GROQ_MODEL"),
            fallback_model=_env("GROQ_FALLBACK_MODEL"),
            base_url=_env("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            timeout_seconds=_env_float("GROQ_TIMEOUT_SECONDS", 15.0),
        ),
        elevenlabs=ElevenLabsConfig(
            api_key=_env("ELEVENLABS_API_KEY"),
            voice_id=_env("ELEVENLABS_VOICE_ID"),
            model_id=_env("ELEVENLABS_MODEL_ID"),
            base_url=_env("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1"),
            timeout_seconds=_env_float("ELEVENLABS_TIMEOUT_SECONDS", 30.0),
        ),
    )


# ---------------------------------------------------------------------------
# Structured logging (§17, §22)
# ---------------------------------------------------------------------------

#: Field names that must never be emitted even if a caller passes them as extra.
_FORBIDDEN_LOG_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "statement_text",
    "raw_prompt",
    "account_number",
}

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class RedactingFilter(logging.Filter):
    """Run every record's rendered message through the prompt PII redactor.

    §25.18 requires that raw account numbers never enter logs. Enforcing it in a
    filter rather than at each call site means a future caller cannot regress it.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:  # pragma: no cover - malformed logging call
            rendered = str(record.msg)
        record.msg = redact_text(rendered)
        record.args = ()
        for key in list(record.__dict__):
            if key.lower() in _FORBIDDEN_LOG_KEYS:
                record.__dict__[key] = "[REDACTED]"
            elif key not in _RESERVED and isinstance(record.__dict__[key], str):
                record.__dict__[key] = redact_text(record.__dict__[key])
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the current request ID attached."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                payload[key] = value
        if record.exc_info:
            # The type and message only — a traceback can contain statement data.
            exc_type = record.exc_info[0]
            payload["error_type"] = getattr(exc_type, "__name__", "Exception")
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Install the JSON handler and the redaction filter on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level, logging.INFO))

    # Uvicorn's own handlers would bypass the redaction filter.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger
