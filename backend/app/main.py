"""SafeSpare AI — FastAPI application (§17).

Assembles the app: settings, repositories, structured logging with request IDs,
rate limiting, a centralized exception handler that never leaks internals, and
the §18 routers.

Track: FinTech — Problem Statement 2: Smart Expense & Micro-Investment Assistant.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, configure_logging, get_logger, load_settings
from .dependencies import ApiError, RateLimiter, client_key
from .repositories.memory import build_in_memory_repositories

logger = get_logger(__name__)

DESCRIPTION = (
    "SafeSpare analyzes transaction history, protects essential obligations, "
    "identifies safely redirectable spending, applies controlled round-ups and "
    "simulates how confirmed savings could support financial goals.\n\n"
    "SafeSpare never executes a real investment, transfer or cancellation, and "
    "never guarantees a return. Every financial value is computed by the backend "
    "from the user's own statement; language models may only phrase values that "
    "have already been calculated."
)


def create_app(settings: Settings = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=DESCRIPTION,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.state.settings = settings
    app.state.repositories = build_in_memory_repositories()
    app.state.rate_limiter = RateLimiter(
        settings.rate_limit_requests, settings.rate_limit_window_seconds
    )

    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-Session-Id", "Idempotency-Key"],
            expose_headers=["X-Request-ID"],
        )

    _register_middleware(app)
    _register_exception_handlers(app)
    _register_routers(app)

    logger.info(
        "application_ready",
        extra={"event": "application_ready", "version": settings.version},
    )
    return app


def _register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """Attach a request ID, apply rate limiting, and time the request."""
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.time()

        # Probes and docs are exempt so a health check can never be rate-limited
        # out of service.
        limiter: RateLimiter = request.app.state.rate_limiter
        if not request.url.path.startswith(("/health", "/ready", "/docs", "/openapi")):
            allowed, retry_after = limiter.check(client_key(request))
            if not allowed:
                response = _error_response(
                    429,
                    "RATE_LIMITED",
                    "Too many requests. Please wait a moment and try again.",
                    request_id,
                )
                response.headers["Retry-After"] = str(retry_after)
                return response

        try:
            response = await call_next(request)
        except ApiError:
            raise
        except Exception:
            # The last line of defence: an unexpected error must still return a
            # safe, structured body rather than a stack trace (§5, §27).
            logger.exception(
                "unhandled_exception",
                extra={"event": "unhandled_exception", "request_id": request_id},
            )
            return _error_response(
                500,
                "INTERNAL_ERROR",
                "Something went wrong on our side. Please try again.",
                request_id,
            )

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "event": "request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": int((time.time() - started) * 1000),
            },
        )
        return response


def _error_response(
    status_code: int, code: str, message: str, request_id: str = None
) -> JSONResponse:
    body: Dict[str, Any] = {"error": {"code": code, "message": message}}
    if request_id:
        body["request_id"] = request_id
    response = JSONResponse(status_code=status_code, content=body)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        # `log_detail` carries the internal reason; only `message` reaches the user.
        detail = getattr(exc, "log_detail", None)
        if detail:
            logger.info(
                "api_error",
                extra={"event": "api_error", "code": exc.code, "detail": detail},
            )
        return _error_response(
            exc.status_code,
            exc.code,
            exc.message,
            getattr(request.state, "request_id", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        """422 with field-level detail, but no internal paths or types."""
        fields = []
        for error in exc.errors():
            location = [str(p) for p in error.get("loc", []) if p not in ("body", "query")]
            fields.append(
                {"field": ".".join(location) or "body", "message": error.get("msg", "invalid")}
            )
        request_id = getattr(request.state, "request_id", None)
        body = {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Some values were not accepted. Please check and try again.",
                "fields": fields,
            }
        }
        if request_id:
            body["request_id"] = request_id
        return JSONResponse(status_code=422, content=body)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHORIZED"}
        messages = {
            404: "We could not find that.",
            405: "That action is not allowed here.",
            401: "Please start a session first.",
        }
        return _error_response(
            exc.status_code,
            codes.get(exc.status_code, "HTTP_ERROR"),
            messages.get(exc.status_code, "The request could not be completed."),
            getattr(request.state, "request_id", None),
        )


def _register_routers(app: FastAPI) -> None:
    from .api import (
        analyses,
        goals,
        health,
        insights,
        leaks,
        settings_routes,
        transactions,
        uploads,
        voice_entry,
    )

    app.include_router(health.router)
    app.include_router(uploads.router)
    app.include_router(analyses.router)
    app.include_router(settings_routes.router)
    app.include_router(transactions.router)
    app.include_router(leaks.router)
    app.include_router(goals.router)
    app.include_router(insights.router)
    app.include_router(voice_entry.router)


app = create_app()
