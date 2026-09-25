"""FastAPI app factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import sentry_sdk
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.responses import JSONResponse

from app import models as _models  # noqa: F401  # registers every mapper
from app.core.config import Settings, get_settings
from app.core.db import get_engine
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.middleware import CsrfOriginMiddleware, RequestContextMiddleware
from app.modules.accounts.router import admin_router as accounts_admin_router
from app.modules.accounts.router import router as accounts_router
from app.modules.audit.router import router as audit_router
from app.modules.inventory.router import router as inventory_router
from app.modules.platform.router import router as platform_router

log = logging.getLogger(__name__)


def _scrub_event(event: Any, _hint: Any) -> Any:
    """Sentry must never receive cookies, headers, bodies or query strings (OTPs, tokens, phone numbers)."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("cookies", "headers", "data", "query_string", "env"):
            request.pop(key, None)
    event.pop("user", None)
    return event


def _init_sentry(settings: Settings) -> None:
    if settings.sentry_dsn is None:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.app_env,
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=_scrub_event,
        before_send_transaction=_scrub_event,
        max_request_body_size="never",
    )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()  # fails fast if a required variable is missing
    configure_logging(settings.log_level)
    _init_sentry(settings)

    public_docs = settings.app_env != "production"
    app = FastAPI(
        title="Cocreat API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if public_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if public_docs else None,
    )

    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=exc.status_code)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            log.exception("readyz.db_unreachable")
            return JSONResponse({"status": "db_unreachable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    api = APIRouter(prefix="/api")
    for router in (accounts_router, accounts_admin_router, platform_router, inventory_router, audit_router):
        api.include_router(router)
    app.include_router(api)

    # outermost last: RequestContext wraps everything so even CORS/CSRF rejections get an ID and a log line
    app.add_middleware(CsrfOriginMiddleware, allowed_origins=settings.cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Idempotent-Replayed"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware, hsts=settings.is_production_like)
    return app


app = create_app()
