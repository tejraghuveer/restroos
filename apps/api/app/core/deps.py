from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.core.db import set_rls_context
from app.core.enums import MembershipStatus, Role, TenantStatus
from app.core.errors import Forbidden, Unauthorized
from app.core.permissions import Permission, permissions_for
from app.core.security import AccessClaims, TokenError, decode_access_token
from app.modules.auth.models import User
from app.modules.tenants.models import Membership, Restaurant, Tenant

bearer_scheme = HTTPBearer(auto_error=False)


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    database = request.app.state.db
    async with database.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def request_meta(request: Request) -> dict[str, str | None]:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


@dataclass(slots=True)
class Principal:
    user: User
    membership: Membership
    tenant: Tenant
    restaurant: Restaurant | None
    claims: AccessClaims

    @property
    def role(self) -> Role:
        return self.membership.role

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.membership.role)

    @property
    def tenant_wide(self) -> bool:
        return self.membership.restaurant_id is None

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions


async def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthorized("Authentication required")

    settings: Settings = request.app.state.settings
    try:
        claims = decode_access_token(settings, credentials.credentials)
    except TokenError as exc:
        raise Unauthorized(str(exc)) from exc

    await set_rls_context(
        session, tenant_id=claims.tenant_id, user_id=claims.user_id
    )
    membership = await session.scalar(
        select(Membership)
        .options(
            joinedload(Membership.user),
            joinedload(Membership.tenant),
            joinedload(Membership.restaurant),
        )
        .where(
            Membership.id == claims.membership_id,
            Membership.tenant_id == claims.tenant_id,
            Membership.user_id == claims.user_id,
        )
    )
    if membership is None:
        raise Unauthorized("Your membership is no longer valid")
    if membership.status is not MembershipStatus.ACTIVE:
        raise Forbidden("Your membership is not active")
    if not membership.user.is_active:
        raise Forbidden("This account has been disabled")
    if membership.tenant.status is TenantStatus.SUSPENDED:
        raise Forbidden("This restaurant account is suspended")

    restaurant: Restaurant | None = None
    if membership.restaurant_id is not None:
        if (
            claims.restaurant_id is not None
            and claims.restaurant_id != membership.restaurant_id
        ):
            raise Forbidden("Token branch does not match membership")
        restaurant = membership.restaurant
        if restaurant is None:
            raise Forbidden("Branch not found for this membership")
    elif claims.restaurant_id is not None:
        restaurant = await session.scalar(
            select(Restaurant).where(
                Restaurant.id == claims.restaurant_id,
                Restaurant.tenant_id == membership.tenant_id,
            )
        )
        if restaurant is None:
            raise Forbidden("Branch not found for this tenant")

    request.state.tenant_id = str(membership.tenant_id)
    return Principal(
        user=membership.user,
        membership=membership,
        tenant=membership.tenant,
        restaurant=restaurant,
        claims=claims,
    )


def require_permission(
    *required: Permission, tenant_wide: bool = False
):
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if tenant_wide and not principal.tenant_wide:
            raise Forbidden("This action requires tenant-wide access")
        missing = [permission.value for permission in required if not principal.has(permission)]
        if missing:
            raise Forbidden(
                "Missing required permission(s): " + ", ".join(sorted(missing))
            )
        return principal

    return dependency
