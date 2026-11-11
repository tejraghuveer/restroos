from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.core.db import set_rls_context
from app.core.enums import (
    AuditAction,
    MembershipStatus,
    RestaurantStatus,
    Role,
    TenantStatus,
)
from app.core.errors import Conflict, Forbidden, NotFound, Unauthorized
from app.core.ids import new_token, uuid7
from app.core.passwords import hash_password, token_digest, verify_password
from app.core.permissions import permissions_for
from app.core.security import create_access_token
from app.modules.audit import service as audit_service
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.schemas import (
    ContextOption,
    ContextOut,
    MeOut,
    SessionOut,
    UserOut,
)
from app.modules.billing.service import create_free_subscription
from app.modules.tenants.models import Invitation, Membership, Restaurant, Tenant

# Pre-computed hash so unknown emails cost roughly the same as known ones.
_DUMMY_HASH = hash_password("restroos-dummy-password-for-timing")

_REQUEST_META = dict[str, str | None]


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "restaurant")[:60]


async def _unique_tenant_slug(session: AsyncSession, base: str) -> str:
    root = _slugify(base)
    candidate = root
    suffix = 2
    while await session.scalar(select(Tenant.id).where(Tenant.slug == candidate)):
        candidate = f"{root}-{suffix}"
        suffix += 1
    return candidate


async def _unique_restaurant_slug(
    session: AsyncSession, tenant_id: uuid.UUID, base: str
) -> str:
    root = _slugify(base)
    candidate = root
    suffix = 2
    while await session.scalar(
        select(Restaurant.id).where(
            Restaurant.tenant_id == tenant_id, Restaurant.slug == candidate
        )
    ):
        candidate = f"{root}-{suffix}"
        suffix += 1
    return candidate


def _context(membership: Membership, tenant: Tenant, restaurant: Restaurant | None) -> ContextOut:
    return ContextOut(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        restaurant_id=restaurant.id if restaurant else None,
        restaurant_name=restaurant.name if restaurant else None,
        role=membership.role,
        tenant_wide=membership.restaurant_id is None,
        permissions=sorted(permission.value for permission in permissions_for(membership.role)),
    )


def _option(membership: Membership, tenant: Tenant) -> ContextOption:
    return ContextOption(
        membership_id=membership.id,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        restaurant_id=membership.restaurant_id,
        role=membership.role,
    )


async def _memberships_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[Membership]:
    rows = await session.scalars(
        select(Membership)
        .options(joinedload(Membership.tenant))
        .where(
            Membership.user_id == user_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
        .order_by(Membership.created_at.asc())
    )
    return list(rows.unique())


async def _load_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFound("Tenant not found")
    if tenant.status is TenantStatus.SUSPENDED:
        raise Forbidden("This restaurant account is suspended")
    return tenant


async def _load_restaurant(
    session: AsyncSession, tenant_id: uuid.UUID, restaurant_id: uuid.UUID
) -> Restaurant:
    restaurant = await session.scalar(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.tenant_id == tenant_id,
        )
    )
    if restaurant is None:
        raise NotFound("Restaurant not found")
    return restaurant


async def _create_session(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    membership: Membership,
    tenant: Tenant,
    restaurant: Restaurant | None,
    request_meta: _REQUEST_META,
    family_id: uuid.UUID | None = None,
) -> tuple[SessionOut, str]:
    raw_refresh = new_token(48)
    record = RefreshToken(
        id=uuid7(),
        user_id=user.id,
        tenant_id=tenant.id,
        membership_id=membership.id,
        family_id=family_id or uuid7(),
        token_hash=token_digest(raw_refresh),
        expires_at=datetime.now(UTC)
        + timedelta(days=settings.refresh_token_days),
        user_agent=(request_meta.get("user_agent") or "")[:255] or None,
        ip_address=request_meta.get("ip_address"),
    )
    session.add(record)
    await session.flush()

    access = create_access_token(
        settings,
        user_id=user.id,
        tenant_id=tenant.id,
        membership_id=membership.id,
        restaurant_id=restaurant.id if restaurant else None,
        role=membership.role,
    )
    options = [
        _option(item, item.tenant)
        for item in await _memberships_for_user(session, user.id)
        if item.tenant is not None
    ]
    payload = SessionOut(
        access_token=access,
        expires_in=settings.access_token_minutes * 60,
        context=_context(membership, tenant, restaurant),
        available_contexts=options,
    )
    return payload, raw_refresh


async def _revoke_family(
    session: AsyncSession, family_id: uuid.UUID, *, except_id: uuid.UUID | None = None
) -> None:
    now = datetime.now(UTC)
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if except_id is not None:
        stmt = stmt.where(RefreshToken.id != except_id)
    await session.execute(stmt)


async def register(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
    full_name: str,
    business_name: str | None,
    restaurant_name: str | None,
    timezone_name: str,
    invitation_token: str | None,
    request_meta: _REQUEST_META,
) -> tuple[SessionOut, str]:
    normalized_email = _normalize_email(email)
    existing = await session.scalar(select(User.id).where(User.email == normalized_email))
    if existing:
        raise Conflict("email_already_registered", "An account with this email already exists")

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
    )
    session.add(user)

    if invitation_token:
        digest = token_digest(invitation_token)
        await set_rls_context(session, invitation_token=digest)
        invitation = await session.scalar(
            select(Invitation).where(Invitation.token_hash == digest)
        )
        now = datetime.now(UTC)
        if invitation is None:
            raise NotFound("Invitation not found")
        if invitation.email != normalized_email:
            raise Forbidden("This invitation was issued to a different email address")
        if invitation.accepted_at is not None or invitation.revoked_at is not None:
            raise Conflict("invitation_used", "This invitation has already been used")
        if invitation.expires_at <= now:
            raise Conflict("invitation_expired", "This invitation has expired")

        await session.flush()
        await set_rls_context(
            session, tenant_id=invitation.tenant_id, user_id=user.id
        )
        membership = Membership(
            tenant_id=invitation.tenant_id,
            user_id=user.id,
            restaurant_id=invitation.restaurant_id,
            role=invitation.role,
            status=MembershipStatus.ACTIVE,
        )
        session.add(membership)
        invitation.accepted_at = now
        tenant = await _load_tenant(session, invitation.tenant_id)
        restaurant = (
            await _load_restaurant(session, tenant.id, invitation.restaurant_id)
            if invitation.restaurant_id
            else None
        )
        await audit_service.record(
            session,
            tenant_id=tenant.id,
            action=AuditAction.INVITATION_ACCEPTED,
            actor_user_id=user.id,
            actor_membership_id=membership.id,
            entity_type="invitation",
            entity_id=str(invitation.id),
            ip_address=request_meta.get("ip_address"),
            request_id=request_meta.get("request_id"),
        )
        await session.flush()
        return await _create_session(
            session,
            settings,
            user=user,
            membership=membership,
            tenant=tenant,
            restaurant=restaurant,
            request_meta=request_meta,
        )

    if not business_name:
        raise Conflict("business_required", "Business name is required")

    tenant_id = uuid7()
    await set_rls_context(session, tenant_id=tenant_id)
    tenant = Tenant(
        id=tenant_id,
        slug=await _unique_tenant_slug(session, business_name),
        name=business_name.strip(),
        status=TenantStatus.ACTIVE,
        timezone=timezone_name,
    )
    session.add(tenant)
    await session.flush()

    restaurant = Restaurant(
        tenant_id=tenant.id,
        name=(restaurant_name or business_name).strip(),
        slug=await _unique_restaurant_slug(session, tenant.id, restaurant_name or business_name),
        status=RestaurantStatus.ACTIVE,
        timezone=timezone_name,
    )
    session.add(restaurant)
    membership = Membership(
        tenant_id=tenant.id,
        user_id=user.id,
        restaurant_id=None,
        role=Role.OWNER,
        status=MembershipStatus.ACTIVE,
    )
    session.add(membership)
    await create_free_subscription(session, settings, tenant.id)
    await audit_service.record(
        session,
        tenant_id=tenant.id,
        action=AuditAction.TENANT_REGISTERED,
        actor_user_id=user.id,
        actor_membership_id=membership.id,
        entity_type="tenant",
        entity_id=str(tenant.id),
        ip_address=request_meta.get("ip_address"),
        request_id=request_meta.get("request_id"),
    )
    await session.flush()
    return await _create_session(
        session,
        settings,
        user=user,
        membership=membership,
        tenant=tenant,
        restaurant=restaurant,
        request_meta=request_meta,
    )


async def login(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
    request_meta: _REQUEST_META,
) -> tuple[SessionOut, str]:
    user = await session.scalar(select(User).where(User.email == _normalize_email(email)))
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok:
        raise Unauthorized("Invalid email or password")
    if not user.is_active:
        raise Forbidden("This account has been disabled")

    await set_rls_context(session, user_id=user.id)
    memberships = await _memberships_for_user(session, user.id)
    if not memberships:
        raise Forbidden("No active restaurant membership found for this account")

    membership = memberships[0]
    await set_rls_context(session, tenant_id=membership.tenant_id, user_id=user.id)
    tenant = await _load_tenant(session, membership.tenant_id)
    restaurant = None
    if membership.restaurant_id:
        restaurant = await _load_restaurant(session, tenant.id, membership.restaurant_id)
    else:
        restaurant = await session.scalar(
            select(Restaurant)
            .where(
                Restaurant.tenant_id == tenant.id,
                Restaurant.status == RestaurantStatus.ACTIVE,
            )
            .order_by(Restaurant.created_at.asc())
            .limit(1)
        )

    user.last_login_at = datetime.now(UTC)
    await audit_service.record(
        session,
        tenant_id=tenant.id,
        action=AuditAction.USER_LOGGED_IN,
        actor_user_id=user.id,
        actor_membership_id=membership.id,
        ip_address=request_meta.get("ip_address"),
        request_id=request_meta.get("request_id"),
    )
    return await _create_session(
        session,
        settings,
        user=user,
        membership=membership,
        tenant=tenant,
        restaurant=restaurant,
        request_meta=request_meta,
    )


async def refresh(
    session: AsyncSession,
    settings: Settings,
    *,
    raw_refresh: str,
    request_meta: _REQUEST_META,
) -> tuple[SessionOut, str]:
    digest = token_digest(raw_refresh)
    record = await session.scalar(
        select(RefreshToken)
        .options(joinedload(RefreshToken.user))
        .where(RefreshToken.token_hash == digest)
    )
    if record is None:
        raise Unauthorized("Session expired. Please log in again.")

    now = datetime.now(UTC)
    if record.revoked_at is not None:
        if record.replaced_by_id is not None:
            await _revoke_family(session, record.family_id)
            if record.tenant_id:
                await set_rls_context(
                    session, tenant_id=record.tenant_id, user_id=record.user_id
                )
                await audit_service.record(
                    session,
                    tenant_id=record.tenant_id,
                    action=AuditAction.TOKEN_REUSE_DETECTED,
                    actor_user_id=record.user_id,
                    ip_address=request_meta.get("ip_address"),
                    request_id=request_meta.get("request_id"),
                    meta={"family_id": str(record.family_id)},
                )
            # The request dependency rolls back on raised errors, so persist the
            # family revocation explicitly before rejecting the reuse attempt.
            await session.commit()
        raise Unauthorized("Session expired. Please log in again.")

    if record.expires_at <= now:
        raise Unauthorized("Session expired. Please log in again.")
    if not record.user.is_active:
        raise Forbidden("This account has been disabled")
    if record.tenant_id is None or record.membership_id is None:
        raise Unauthorized("Invalid session context")

    await set_rls_context(session, tenant_id=record.tenant_id, user_id=record.user_id)
    membership = await session.scalar(
        select(Membership).where(
            Membership.id == record.membership_id,
            Membership.user_id == record.user_id,
            Membership.tenant_id == record.tenant_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    if membership is None:
        raise Unauthorized("Your membership is no longer active")

    tenant = await _load_tenant(session, record.tenant_id)
    restaurant = (
        await _load_restaurant(session, tenant.id, membership.restaurant_id)
        if membership.restaurant_id
        else await session.scalar(
            select(Restaurant)
            .where(
                Restaurant.tenant_id == tenant.id,
                Restaurant.status == RestaurantStatus.ACTIVE,
            )
            .order_by(Restaurant.created_at.asc())
            .limit(1)
        )
    )

    record.revoked_at = now
    payload, new_raw = await _create_session(
        session,
        settings,
        user=record.user,
        membership=membership,
        tenant=tenant,
        restaurant=restaurant,
        request_meta=request_meta,
        family_id=record.family_id,
    )
    new_id = await session.scalar(
        select(RefreshToken.id).where(RefreshToken.token_hash == token_digest(new_raw))
    )
    record.replaced_by_id = new_id
    await audit_service.record(
        session,
        tenant_id=tenant.id,
        action=AuditAction.TOKEN_REFRESHED,
        actor_user_id=record.user_id,
        actor_membership_id=membership.id,
        ip_address=request_meta.get("ip_address"),
        request_id=request_meta.get("request_id"),
    )
    return payload, new_raw


async def logout(
    session: AsyncSession, *, raw_refresh: str | None, request_meta: _REQUEST_META
) -> None:
    if not raw_refresh:
        return
    record = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_digest(raw_refresh))
    )
    if record is None:
        return
    await _revoke_family(session, record.family_id)
    if record.tenant_id:
        await set_rls_context(session, tenant_id=record.tenant_id, user_id=record.user_id)
        await audit_service.record(
            session,
            tenant_id=record.tenant_id,
            action=AuditAction.USER_LOGGED_OUT,
            actor_user_id=record.user_id,
            actor_membership_id=record.membership_id,
            ip_address=request_meta.get("ip_address"),
            request_id=request_meta.get("request_id"),
        )


async def switch_context(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    current_membership: Membership,
    current_tenant: Tenant,
    membership_id: uuid.UUID | None,
    restaurant_id: uuid.UUID | None,
    request_meta: _REQUEST_META,
) -> tuple[SessionOut, str]:
    if membership_id is not None:
        target = await session.scalar(
            select(Membership)
            .options(joinedload(Membership.tenant))
            .where(
                Membership.id == membership_id,
                Membership.user_id == user.id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        if target is None:
            raise NotFound("Membership not found")
        await set_rls_context(session, tenant_id=target.tenant_id, user_id=user.id)
        tenant = await _load_tenant(session, target.tenant_id)
        restaurant = (
            await _load_restaurant(session, tenant.id, target.restaurant_id)
            if target.restaurant_id
            else await session.scalar(
                select(Restaurant)
                .where(
                    Restaurant.tenant_id == tenant.id,
                    Restaurant.status == RestaurantStatus.ACTIVE,
                )
                .order_by(Restaurant.created_at.asc())
                .limit(1)
            )
        )
        membership = target
    else:
        if restaurant_id is None:
            raise NotFound("Restaurant not found")
        if (
            current_membership.restaurant_id is not None
            and current_membership.restaurant_id != restaurant_id
        ):
            raise Forbidden("Your membership is limited to a different branch")
        restaurant = await _load_restaurant(
            session, current_membership.tenant_id, restaurant_id
        )
        tenant = current_tenant
        membership = current_membership

    if restaurant is not None and restaurant.status is RestaurantStatus.INACTIVE:
        raise Forbidden("This branch is inactive")

    payload, raw_refresh = await _create_session(
        session,
        settings,
        user=user,
        membership=membership,
        tenant=tenant,
        restaurant=restaurant,
        request_meta=request_meta,
    )
    await audit_service.record(
        session,
        tenant_id=tenant.id,
        action=AuditAction.CONTEXT_SWITCHED,
        actor_user_id=user.id,
        actor_membership_id=membership.id,
        ip_address=request_meta.get("ip_address"),
        request_id=request_meta.get("request_id"),
        meta={"restaurant_id": str(restaurant.id) if restaurant else None},
    )
    return payload, raw_refresh


async def build_me(
    session: AsyncSession,
    *,
    user: User,
    membership: Membership,
    tenant: Tenant,
    restaurant: Restaurant | None,
) -> MeOut:
    options = [
        _option(item, item.tenant)
        for item in await _memberships_for_user(session, user.id)
        if item.tenant is not None
    ]
    return MeOut(
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_platform_admin=user.is_platform_admin,
        ),
        context=_context(membership, tenant, restaurant),
        available_contexts=options,
    )
