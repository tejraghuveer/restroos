from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import SubscriptionStatus
from app.core.errors import Forbidden, NotFound
from app.modules.billing.models import Plan, Subscription

FREE_PLAN_CODE = "free"


async def ensure_free_plan(session: AsyncSession, settings: Settings) -> Plan:
    plan = await session.scalar(select(Plan).where(Plan.code == FREE_PLAN_CODE))
    limits = {
        "max_restaurants": settings.free_plan_max_restaurants,
        "max_staff": settings.free_plan_max_staff,
        "max_menu_items": 50,
    }
    if plan is None:
        plan = Plan(
            code=FREE_PLAN_CODE,
            name="Free",
            price_cents=0,
            currency="INR",
            limits=limits,
            is_active=True,
        )
        session.add(plan)
    else:
        plan.name = "Free"
        plan.limits = limits
        plan.is_active = True
    await session.flush()
    return plan


async def create_free_subscription(
    session: AsyncSession, settings: Settings, tenant_id: uuid.UUID
) -> Subscription:
    plan = await ensure_free_plan(session, settings)
    now = datetime.now(UTC)
    subscription = Subscription(
        tenant_id=tenant_id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=None,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def get_subscription(session: AsyncSession, tenant_id: uuid.UUID) -> Subscription:
    subscription = await session.scalar(
        select(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    if subscription is None:
        raise NotFound("No subscription found for this tenant")
    return subscription


async def get_limits(session: AsyncSession, tenant_id: uuid.UUID) -> dict:
    subscription = await get_subscription(session, tenant_id)
    return dict(subscription.plan.limits or {})


async def assert_restaurant_limit(
    session: AsyncSession, tenant_id: uuid.UUID, current: int
) -> None:
    limits = await get_limits(session, tenant_id)
    maximum = limits.get("max_restaurants")
    if maximum is not None and current >= int(maximum):
        raise Forbidden(
            f"Your plan allows {maximum} restaurant(s). Upgrade to add another branch."
        )


async def assert_staff_limit(session: AsyncSession, tenant_id: uuid.UUID, current: int) -> None:
    limits = await get_limits(session, tenant_id)
    maximum = limits.get("max_staff")
    if maximum is not None and current >= int(maximum):
        raise Forbidden(f"Your plan allows {maximum} staff member(s). Upgrade to invite more.")
