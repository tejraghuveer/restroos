from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    Principal,
    get_db,
    request_meta,
    require_permission,
)
from app.core.permissions import Permission
from app.modules.tenants import service
from app.modules.tenants.schemas import (
    RestaurantCreate,
    RestaurantOut,
    SubscriptionOut,
    TenantOut,
    TenantUpdate,
)

router = APIRouter(tags=["tenants"])


@router.get("/tenant", response_model=TenantOut)
async def get_tenant(
    principal: Principal = Depends(require_permission(Permission.TENANT_READ)),
) -> TenantOut:
    return service.tenant_to_out(principal.tenant)


@router.patch("/tenant", response_model=TenantOut)
async def update_tenant(
    payload: TenantUpdate,
    request: Request,
    principal: Principal = Depends(
        require_permission(Permission.TENANT_MANAGE, tenant_wide=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> TenantOut:
    return await service.update_tenant(
        session, principal, payload, request_meta=request_meta(request)
    )


@router.get("/restaurants", response_model=list[RestaurantOut])
async def list_restaurants(
    principal: Principal = Depends(require_permission(Permission.BRANCH_READ)),
    session: AsyncSession = Depends(get_db),
) -> list[RestaurantOut]:
    return await service.list_restaurants(session, principal)


@router.post("/restaurants", response_model=RestaurantOut, status_code=201)
async def create_restaurant(
    payload: RestaurantCreate,
    request: Request,
    principal: Principal = Depends(
        require_permission(Permission.BRANCH_MANAGE, tenant_wide=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> RestaurantOut:
    return await service.create_restaurant(
        session, principal, payload, request_meta=request_meta(request)
    )


@router.get("/restaurants/{restaurant_id}", response_model=RestaurantOut)
async def get_restaurant(
    restaurant_id: uuid.UUID,
    principal: Principal = Depends(require_permission(Permission.BRANCH_READ)),
    session: AsyncSession = Depends(get_db),
) -> RestaurantOut:
    return await service.get_restaurant(session, principal, restaurant_id)


@router.get("/billing/subscription", response_model=SubscriptionOut)
async def get_subscription(
    principal: Principal = Depends(require_permission(Permission.BILLING_READ)),
    session: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    return await service.get_subscription(session, principal)
