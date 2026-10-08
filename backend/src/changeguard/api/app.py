"""FastAPI application factory."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from changeguard import __version__
from changeguard.ai.cache import SQLiteCache
from changeguard.ai.providers import build_provider
from changeguard.ai.synthesizer import AISynthesizer
from changeguard.api.jobs import JobRunner
from changeguard.api.routes import analyses, meta, samples
from changeguard.api.security import (
    BodySizeLimitMiddleware,
    RateLimiter,
    security_headers_middleware,
)
from changeguard.api.state import AppState
from changeguard.config import Settings, get_settings
from changeguard.errors import ChangeGuardError
from changeguard.storage import AnalysisStore, Database

log = logging.getLogger("changeguard")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger("changeguard")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        _JsonFormatter()
        if settings.env == "production"
        else logging.Formatter("%(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


def _problem(
    request: Request, status: int, title: str, detail: str, code: str, **extra: Any
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
        **extra,
    }
    headers = {}
    if code == "rate_limited" and "retry_after" in extra.get("meta", {}):
        headers["Retry-After"] = str(extra["meta"]["retry_after"])
    return JSONResponse(
        body, status_code=status, media_type="application/problem+json", headers=headers
    )


def build_state(settings: Settings) -> AppState:
    db = Database(settings.database_path)
    store = AnalysisStore(db)
    provider = build_provider(settings)
    synthesizer = None
    if provider is not None:
        synthesizer = AISynthesizer(
            provider,
            cache=SQLiteCache(settings.database_path) if settings.ai_cache_enabled else None,
            max_context_chars=settings.ai_max_context_chars,
            max_findings=settings.ai_max_findings,
            temperature=settings.ai_temperature,
            seed=settings.ai_seed,
        )
    runner = JobRunner(
        store,
        workers=settings.worker_threads,
        timeout_seconds=settings.analysis_timeout_seconds,
        synthesizer=synthesizer,
        max_stored=settings.max_stored_analyses,
    )
    return AppState(
        settings=settings,
        store=store,
        runner=runner,
        limiter=RateLimiter(settings.rate_limit_per_minute),
        provider=provider,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = build_state(settings)
        interrupted = state.store.fail_incomplete()
        if interrupted:
            log.warning("marked %d interrupted analyses as failed", interrupted)
        app.state.changeguard = state
        log.info(
            "ChangeGuard %s ready (db=%s, ai=%s, auth=%s)",
            __version__, settings.database_path, settings.ai_provider, "on" if settings.auth_required else "off",
        )  # fmt: skip
        try:
            yield
        finally:
            state.runner.shutdown()

    docs = settings.expose_docs
    app = FastAPI(
        title="ChangeGuard API",
        version=__version__,
        summary="Evidence-grounded code-change risk analysis.",
        description=(
            "Analyse a git diff (optionally with a repository snapshot and a coverage report) and receive a structured "
            "risk report. Every finding states its provenance (deterministic, heuristic, or AI-generated), severity and "
            "confidence separately, and cites evidence extracted from the inputs.\n\n"
            "Authentication: when the server is configured with API keys, send `Authorization: Bearer <key>` or `X-API-Key`."
        ),
        lifespan=lifespan,
        docs_url="/api/docs" if docs else None,
        redoc_url="/api/redoc" if docs else None,
        openapi_url="/api/openapi.json" if docs else None,
    )

    @app.exception_handler(ChangeGuardError)
    async def _domain_error(request: Request, exc: ChangeGuardError) -> JSONResponse:
        return _problem(request, exc.status, exc.title, exc.message, exc.code, meta=exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg", "")}
            for e in exc.errors()
        ][:10]
        return _problem(
            request,
            422,
            "Invalid request",
            "the request parameters are invalid",
            "invalid_request",
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception(
            "unhandled error on %s %s (request %s)",
            request.method,
            request.url.path,
            getattr(request.state, "request_id", "-"),
        )
        return _problem(
            request,
            500,
            "Internal error",
            "an unexpected error occurred; it has been logged",
            "internal_error",
        )

    app.middleware("http")(security_headers_middleware)
    max_body = (
        settings.max_patch_bytes
        + settings.max_archive_bytes
        + settings.max_coverage_bytes
        + 1_000_000
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_body)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "X-API-Key", "Content-Type", "Last-Event-ID"],
            max_age=600,
        )
    app.include_router(meta.router)
    app.include_router(analyses.router)
    app.include_router(samples.router)
    return app


def create_default_app() -> FastAPI:
    """Entry point for ``uvicorn changeguard.api.app:create_default_app --factory``."""
    return create_app()
