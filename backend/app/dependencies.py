"""Shared FastAPI dependencies — spec §17, §22, §29.

Everything a route needs that is *not* business logic lives here: settings,
repositories, session identity, authorization, identifier parsing and the
in-memory rate limiter.

Two design decisions worth stating:

1. Settings and repositories are read from ``request.app.state`` rather than
   module-level singletons. A test can therefore build a fully isolated
   application with its own storage, and swapping the in-memory repositories for
   a DynamoDB bundle is a change to ``main.create_app`` alone (§20).

2. Session authorization returns **404, not 403**, when one session asks for
   another session's analysis (§29). A 403 confirms the identifier exists, which
   turns the endpoint into an enumeration oracle for uploaded bank statements.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, Request, Response

from .config import Settings, get_logger, load_settings
from .models.entities import AnalysisSession, AnalysisStatus, User
from .repositories.base import Repositories

logger = get_logger(__name__)

SESSION_HEADER = "X-Session-Id"
SESSION_COOKIE = "safespare_session"
REQUEST_ID_HEADER = "X-Request-ID"
IDEMPOTENCY_HEADER = "Idempotency-Key"

#: Session keys are opaque; we only bound their length and character set so that
#: a hostile value cannot poison a log line or a dictionary key.
_MAX_SESSION_KEY = 128


# ---------------------------------------------------------------------------
# Error type (§5, §17 centralized exception handling)
# ---------------------------------------------------------------------------


class ApiError(Exception):
    """A safe, user-facing failure.

    ``message`` is written for a non-technical person and is the *only* string
    that reaches the client. Internal detail stays in ``log_detail``, which the
    exception handler records but never serialises (§5, §22).
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        log_detail: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.log_detail = log_detail
        self.headers = headers or {}


def bad_request(code: str, message: str, log_detail: Optional[str] = None) -> ApiError:
    return ApiError(400, code, message, log_detail)


def not_found(code: str = "NOT_FOUND", message: str = "We could not find that item.") -> ApiError:
    return ApiError(404, code, message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def unprocessable(code: str, message: str) -> ApiError:
    return ApiError(422, code, message)


# ---------------------------------------------------------------------------
# Application state accessors
# ---------------------------------------------------------------------------


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:  # pragma: no cover - create_app always sets it
        settings = load_settings()
        request.app.state.settings = settings
    return settings


def get_repositories(request: Request) -> Repositories:
    return request.app.state.repositories


# ---------------------------------------------------------------------------
# Session identity (§22 "session authorization", §29)
# ---------------------------------------------------------------------------


def _sanitize_session_key(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cleaned = "".join(ch for ch in raw.strip() if ch.isalnum() or ch in "-_")
    cleaned = cleaned[:_MAX_SESSION_KEY]
    return cleaned or None


def session_key_from_request(request: Request) -> Optional[str]:
    return _sanitize_session_key(
        request.headers.get(SESSION_HEADER) or request.cookies.get(SESSION_COOKIE)
    )


def get_session(
    request: Request,
    response: Response,
    repos: Repositories = Depends(get_repositories),
) -> User:
    """Resolve (or mint) the caller's anonymous session.

    There are no accounts in the MVP; a session *is* the tenant boundary. The
    key is echoed back on both a header and a cookie so a browser client and a
    scripted client can each hold onto it.
    """
    key = session_key_from_request(request) or uuid.uuid4().hex
    user = repos.users.get_or_create_by_session_key(key)
    response.headers[SESSION_HEADER] = key
    response.set_cookie(
        SESSION_COOKIE,
        key,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24,
        path="/",
    )
    return user


# ---------------------------------------------------------------------------
# Identifier parsing
# ---------------------------------------------------------------------------


def parse_uuid(value: str, field: str = "id") -> str:
    """Reject anything that is not a UUID before it reaches a repository.

    §20 mandates UUIDs everywhere, so a non-UUID path segment is a client error
    (400), never a lookup miss (404) — the distinction matters to the frontend,
    which retries 404s but not 400s.
    """
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise bad_request(
            "INVALID_IDENTIFIER",
            "That identifier is not valid.",
            log_detail="field=%s" % field,
        )
    return str(value)


def authorize_analysis(
    repos: Repositories, session: User, analysis_id: str
) -> AnalysisSession:
    """Load an analysis the caller is allowed to see, or raise 404 (§29)."""
    parse_uuid(analysis_id, "analysis_id")
    analysis = repos.analyses.get(analysis_id)
    if analysis is None or analysis.user_id != session.id:
        if analysis is not None:
            # Deliberately indistinguishable from "missing" in the response.
            logger.warning(
                "cross_session_access_denied",
                extra={"event": "cross_session_access_denied"},
            )
        raise ApiError(
            404,
            "ANALYSIS_NOT_FOUND",
            "We could not find that analysis. It may have been deleted.",
        )
    return analysis


def get_analysis(
    analysis_id: str,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> AnalysisSession:
    """Path-parameter dependency for every ``/api/analyses/{analysis_id}`` route."""
    return authorize_analysis(repos, session, analysis_id)


def require_completed(analysis: AnalysisSession) -> AnalysisSession:
    """Guard for read endpoints that only exist once the pipeline finished."""
    if analysis.status is AnalysisStatus.FAILED:
        raise conflict(
            "ANALYSIS_FAILED",
            analysis.error_message or "That analysis could not be completed.",
        )
    if analysis.status is not AnalysisStatus.COMPLETED:
        raise conflict(
            "ANALYSIS_NOT_READY",
            "That analysis is still being prepared. Confirm the extracted "
            "transactions to finish it.",
        )
    return analysis


# ---------------------------------------------------------------------------
# Rate limiting (§17, §22)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Fixed-window counter, per client, in process memory.

    Sufficient for a single-instance hackathon deployment and honest about it:
    behind more than one worker the effective limit multiplies. The interface is
    the one a Redis-backed limiter would expose, so the swap is local.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = max(1, window_seconds)
        self._lock = threading.Lock()
        self._windows: Dict[str, Tuple[int, int]] = {}

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    def check(self, key: str, now: Optional[float] = None) -> Tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)``."""
        if not self.enabled:
            return True, 0
        now = time.time() if now is None else now
        window = int(now // self.window_seconds)
        with self._lock:
            if len(self._windows) > 10000:  # crude bound; entries are tiny
                self._windows = {
                    k: v for k, v in self._windows.items() if v[0] >= window - 1
                }
            current_window, count = self._windows.get(key, (window, 0))
            if current_window != window:
                current_window, count = window, 0
            count += 1
            self._windows[key] = (current_window, count)
        if count > self.limit:
            retry_after = int((current_window + 1) * self.window_seconds - now) + 1
            return False, max(1, retry_after)
        return True, 0

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


def client_key(request: Request) -> str:
    """Rate-limit bucket: the session when known, the peer address otherwise."""
    key = session_key_from_request(request)
    if key:
        return "session:%s" % key
    host = request.client.host if request.client else "unknown"
    return "ip:%s" % host


# ---------------------------------------------------------------------------
# AI router access (§14) — optional by construction
# ---------------------------------------------------------------------------


_router_lock = threading.Lock()
_router_cache: List[Any] = []


def get_ai_router() -> Optional[Any]:
    """Return the AI router, or ``None`` when the AI layer is absent.

    The deterministic core is the product (§3.21): every caller of this function
    must have a template fallback, so an ImportError here is a normal state and
    not an error. The import is lazy and the result memoised.
    """
    with _router_lock:
        if _router_cache:
            return _router_cache[0]
        router: Optional[Any] = None
        try:
            from .ai.router import get_router  # type: ignore

            router = get_router()
        except Exception as exc:  # ImportError, or a router that failed to build
            logger.info(
                "ai_router_unavailable",
                extra={"event": "ai_router_unavailable", "error_type": type(exc).__name__},
            )
            router = None
        _router_cache.append(router)
        return router


def reset_ai_router() -> None:
    """Test seam — drop the memoised router."""
    with _router_lock:
        _router_cache.clear()


def call_ai(method: str, *args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
    """Invoke one router method defensively.

    The contract says router methods never raise, but this module cannot depend
    on that being true of a component built in parallel: a failure here must
    degrade the wording, never the endpoint.
    """
    router = get_ai_router()
    if router is None:
        return None
    fn = getattr(router, method, None)
    if fn is None:
        return None
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "ai_call_failed",
            extra={"event": "ai_call_failed", "ai_method": method,
                   "error_type": type(exc).__name__},
        )
        return None
    if isinstance(result, dict):
        return result
    return {"value": result}


def ai_provider_status() -> List[Dict[str, Any]]:
    """Provider health for ``/ready``. Never contains a secret (§14, §22)."""
    router = get_ai_router()
    if router is not None:
        try:
            status = router.provider_status()
            if isinstance(status, list):
                return [s for s in status if isinstance(s, dict)]
        except Exception:  # pragma: no cover - defensive
            pass
    return []
