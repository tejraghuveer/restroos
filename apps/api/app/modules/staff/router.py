from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    Principal,
    get_db,
    get_principal,
    request_meta,
    require_permission,
)
from app.core.permissions import Permission
from app.modules.auth.schemas import InvitationAcceptRequest
from app.modules.staff import service
from app.modules.staff.schemas import (
    InvitationAcceptResult,
    InvitationCreate,
    InvitationCreatedOut,
    InvitationOut,
    MembershipOut,
    MembershipUpdate,
)

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("", response_model=list[MembershipOut])
async def list_staff(
    principal: Principal = Depends(require_permission(Permission.STAFF_READ)),
    session: AsyncSession = Depends(get_db),
) -> list[MembershipOut]:
    return await service.list_memberships(session, principal)


@router.post("/invitations", response_model=InvitationCreatedOut, status_code=201)
async def create_invitation(
    payload: InvitationCreate,
    request: Request,
    principal: Principal = Depends(require_permission(Permission.STAFF_INVITE)),
    session: AsyncSession = Depends(get_db),
) -> InvitationCreatedOut:
    return await service.create_invitation(
        session, principal, payload, request_meta=request_meta(request)
    )


@router.get("/invitations", response_model=list[InvitationOut])
async def list_invitations(
    principal: Principal = Depends(require_permission(Permission.STAFF_READ)),
    session: AsyncSession = Depends(get_db),
) -> list[InvitationOut]:
    return await service.list_invitations(session, principal)


@router.post("/invitations/accept", response_model=InvitationAcceptResult)
async def accept_invitation(
    payload: InvitationAcceptRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> InvitationAcceptResult:
    membership = await service.accept_invitation(
        session, principal, payload.token, request_meta=request_meta(request)
    )
    return InvitationAcceptResult(
        membership=membership,
        tenant_id=membership.tenant_id,
        membership_id=membership.id,
    )


@router.delete("/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_permission(Permission.STAFF_INVITE)),
    session: AsyncSession = Depends(get_db),
) -> None:
    await service.revoke_invitation(
        session, principal, invitation_id, request_meta=request_meta(request)
    )


@router.patch("/{membership_id}", response_model=MembershipOut)
async def update_membership(
    membership_id: uuid.UUID,
    payload: MembershipUpdate,
    request: Request,
    principal: Principal = Depends(require_permission(Permission.STAFF_MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> MembershipOut:
    return await service.update_membership(
        session,
        principal,
        membership_id,
        payload,
        request_meta=request_meta(request),
    )


@router.delete("/{membership_id}", status_code=204)
async def remove_membership(
    membership_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_permission(Permission.STAFF_MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> None:
    await service.remove_membership(
        session, principal, membership_id, request_meta=request_meta(request)
    )
