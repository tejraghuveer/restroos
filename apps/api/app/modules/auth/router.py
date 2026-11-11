from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import (
    Principal,
    get_app_settings,
    get_db,
    get_principal,
    request_meta,
)
from app.core.errors import Forbidden, Unauthorized
from app.core.ratelimit import client_ip
from app.modules.auth import service
from app.modules.auth.schemas import (
    LoginRequest,
    MeOut,
    RegisterRequest,
    SessionOut,
    SwitchContextRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_PATH_SUFFIX = "/auth"


def _check_origin(request: Request) -> None:
    """Cookie-authenticated endpoints need an origin allowlist (CSRF defence)."""

    origin = request.headers.get("origin")
    settings: Settings = request.app.state.settings
    if origin and origin not in settings.cors_origins:
        raise Forbidden("Origin is not allowed")


def _apply_rate_limit(request: Request) -> None:
    limiter = getattr(request.app.state, "auth_rate_limiter", None)
    if limiter is not None:
        limiter.check(f"auth:{client_ip(request)}")


def _set_refresh_cookie(response: Response, settings: Settings, raw: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=f"{settings.api_v1_prefix}{REFRESH_COOKIE_PATH_SUFFIX}",
        domain=settings.cookie_domain,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=f"{settings.api_v1_prefix}{REFRESH_COOKIE_PATH_SUFFIX}",
        domain=settings.cookie_domain,
    )


@router.post("/register", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionOut:
    _apply_rate_limit(request)
    result, raw_refresh = await service.register(
        session,
        settings,
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        business_name=payload.business_name,
        restaurant_name=payload.restaurant_name,
        timezone_name=payload.timezone,
        invitation_token=payload.invitation_token,
        request_meta=request_meta(request),
    )
    _set_refresh_cookie(response, settings, raw_refresh)
    return result


@router.post("/login", response_model=SessionOut)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionOut:
    _apply_rate_limit(request)
    result, raw_refresh = await service.login(
        session,
        settings,
        email=str(payload.email),
        password=payload.password,
        request_meta=request_meta(request),
    )
    _set_refresh_cookie(response, settings, raw_refresh)
    return result


@router.post("/refresh", response_model=SessionOut)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionOut:
    _check_origin(request)
    _apply_rate_limit(request)
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise Unauthorized("No active session")
    result, new_raw = await service.refresh(
        session, settings, raw_refresh=raw, request_meta=request_meta(request)
    )
    _set_refresh_cookie(response, settings, new_raw)
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    _check_origin(request)
    raw = request.cookies.get(settings.refresh_cookie_name)
    await service.logout(session, raw_refresh=raw, request_meta=request_meta(request))
    _clear_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeOut)
async def me(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> MeOut:
    return await service.build_me(
        session,
        user=principal.user,
        membership=principal.membership,
        tenant=principal.tenant,
        restaurant=principal.restaurant,
    )


@router.post("/switch-context", response_model=SessionOut)
async def switch_context(
    payload: SwitchContextRequest,
    request: Request,
    response: Response,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionOut:
    result, raw_refresh = await service.switch_context(
        session,
        settings,
        user=principal.user,
        current_membership=principal.membership,
        current_tenant=principal.tenant,
        membership_id=payload.membership_id,
        restaurant_id=payload.restaurant_id,
        request_meta=request_meta(request),
    )
    _set_refresh_cookie(response, settings, raw_refresh)
    return result
