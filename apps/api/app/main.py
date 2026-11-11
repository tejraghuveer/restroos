from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.db import Database
from app.core.errors import AppError, ProblemDetail
from app.core.logging import RequestContextMiddleware, configure_logging
from app.core.ratelimit import InMemoryRateLimiter
from app.modules.billing.service import ensure_free_plan

logger = structlog.get_logger("app")


def _problem_response(
    *,
    status_code: int,
    code: str,
    detail: str,
    title: str | None = None,
    instance: str | None = None,
    headers: dict[str, str] | None = None,
    errors: list[dict] | None = None,
) -> JSONResponse:
    problem = ProblemDetail(
        type="about:blank",
        title=title or "Request failed",
        status=status_code,
        detail=detail,
        code=code,
        instance=instance,
        errors=errors,
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.as_dict(),
        media_type="application/problem+json",
        headers=headers,
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if request.app.state.settings.environment == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(
        settings.log_level, json_logs=settings.environment == "production"
    )
    database = Database(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            async with database.session_factory() as session:
                await ensure_free_plan(session, settings)
                await session.commit()
        except Exception:
            if settings.environment == "production":
                raise
            logger.warning(
                "plan_seed_skipped",
                hint="Run 'alembic upgrade head' to create the schema.",
            )
        yield
        await database.dispose()

    docs_enabled = settings.environment != "production"
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        debug=settings.debug,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = database
    app.state.auth_rate_limiter = InMemoryRateLimiter(
        settings.auth_rate_limit_per_minute
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return _problem_response(
            status_code=exc.status_code,
            code=exc.code,
            detail=exc.detail,
            title=str(exc.title),
            instance=request.url.path,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(part) for part in error.get("loc", [])[1:]),
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return _problem_response(
            status_code=422,
            code="validation_error",
            detail="The request payload is invalid",
            title="Validation failed",
            instance=request.url.path,
            errors=errors,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        logger.warning("integrity_error", path=request.url.path, error=str(exc.orig))
        return _problem_response(
            status_code=409,
            code="conflict",
            detail="The request conflicts with existing data",
            title="Conflict",
            instance=request.url.path,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _problem_response(
            status_code=exc.status_code,
            code="http_error",
            detail=str(exc.detail),
            instance=request.url.path,
            headers=dict(exc.headers) if exc.headers else None,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", path=request.url.path)
        return _problem_response(
            status_code=500,
            code="internal_error",
            detail="An unexpected error occurred",
            title="Internal server error",
            instance=request.url.path,
        )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    @app.get("/ready", tags=["system"])
    async def ready() -> JSONResponse:
        try:
            async with database.session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return JSONResponse(status_code=200, content={"status": "ready"})

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
