from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.core.enums import AuditAction, RestaurantStatus
from app.core.errors import NotFound
from app.modules.audit import service as audit_service
from app.modules.billing import service as billing_service
from app.modules.tenants.models import Restaurant, Tenant
from app.modules.tenants.schemas import (
    RestaurantCreate,
    RestaurantOut,
    SubscriptionOut,
    TenantOut,
    TenantUpdate,
)


def _slugify(value: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "branch")[:60]


async def _unique_branch_slug(
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


def tenant_to_out(tenant: Tenant) -> TenantOut:
    return TenantOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status,
        currency=tenant.currency,
        timezone=tenant.timezone,
        created_at=tenant.created_at,
    )


def restaurant_to_out(restaurant: Restaurant) -> RestaurantOut:
    return RestaurantOut(
        id=restaurant.id,
        name=restaurant.name,
        slug=restaurant.slug,
        status=restaurant.status,
        address_line1=restaurant.address_line1,
        address_line2=restaurant.address_line2,
        city=restaurant.city,
        state=restaurant.state,
        postal_code=restaurant.postal_code,
        country=restaurant.country,
        timezone=restaurant.timezone,
        currency=restaurant.currency,
        gstin=restaurant.gstin,
        tax_inclusive=restaurant.tax_inclusive,
        service_charge_bp=restaurant.service_charge_bp,
        created_at=restaurant.created_at,
    )


async def update_tenant(
    session: AsyncSession,
    principal: Principal,
    payload: TenantUpdate,
    *,
    request_meta: dict,
) -> TenantOut:
    tenant = principal.tenant
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return tenant_to_out(tenant)

    for key, value in changes.items():
        setattr(tenant, key, value)

    await audit_service.record(
        session,
        tenant_id=tenant.id,
        action=AuditAction.TENANT_UPDATED,
        actor_user_id=principal.user.id,
        actor_membership_id=principal.membership.id,
        entity_type="tenant",
        entity_id=str(tenant.id),
        ip_address=request_meta.get("ip_address"),
        request_id=request_meta.get("request_id"),
        meta={"fields": sorted(changes)},
    )
    await session.flush()
    return tenant_to_out(tenant)


async def list_restaurants(
    session: AsyncSession, principal: Principal
) -> list[RestaurantOut]:
    stmt = select(Restaurant).where(Restaurant.tenant_id == principal.tenant.id)
    if not principal.tenant_wide:
        stmt = stmt.where(Restaurant.id == principal.membership.restaurant_id)
    rows = await session.scalars(stmt.order_by(Restaurant.created_at.asc()))
    return [restaurant_to_out(item) for item in rows]


async def get_restaurant(
    session: AsyncSession, principal: Principal, restaurant_id: uuid.UUID
) -> RestaurantOut:
    if not principal.tenant_wide and principal.membership.restaurant_id != restaurant_id:
        raise NotFound("Restaurant not found")
    restaurant = await session.scalar(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.tenant_id == principal.tenant.id,
        )
    )
    if restaurant is None:
        raise NotFound("Restaurant not found")
    return restaurant_to_out(restaurant)


async def create_restaurant(
    session: AsyncSession,
    principal: Principal,
    payload: RestaurantCreate,
    *,
    request_meta: dict,
) -> RestaurantOut:
    count = await session.scalar(
        select(func.count())
        .select_from(Restaurant)
        .where(Restaurant.tenant_id == principal.tenant.id)
    )
    await billing_service.assert_restaurant_limit(
        session, principal.tenant.id, int(count or 0)
    )

    base = payload.slug or payload.name
    slug = await _unique_branch_slug(session, principal.tenant.id, base)
    restaurant = Restaurant(
        tenant_id=principal.tenant.id,
        name=payload.name.strip(),
        slug=slug,
        status=RestaurantStatus.ACTIVE,
        address_line1=payload.address_line1,
        address_line2=payload.address_line2,
        city=payload.city,
        state=payload.state,
        postal_code=payload.postal_code,
        timezone=payload.timezone,
        gstin=payload.gstin,
        tax_inclusive=payload.tax_inclusive,
        service_charge_bp=payload.service_charge_bp,
    )
    session.add(restaurant)
    await audit_service.record(
        session,
        tenant_id=principal.tenant.id,
        action=AuditAction.RESTAURANT_CREATED,
        actor_user_id=principal.user.id,
        actor_membership_id=principal.membership.id,
        entity_type="restaurant",
        entity_id=str(restaurant.id),
        ip_address=request_meta.get("ip_address"),
        request_id=request_meta.get("request_id"),
    )
    await session.flush()
    return restaurant_to_out(restaurant)


async def get_subscription(
    session: AsyncSession, principal: Principal
) -> SubscriptionOut:
    subscription = await billing_service.get_subscription(session, principal.tenant.id)
    return SubscriptionOut(
        plan_code=subscription.plan.code,
        plan_name=subscription.plan.name,
        status=subscription.status.value,
        price_cents=subscription.plan.price_cents,
        currency=subscription.plan.currency,
        limits=dict(subscription.plan.limits or {}),
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
    )
