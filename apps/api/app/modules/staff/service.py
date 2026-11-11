from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.db import set_rls_context
from app.core.deps import Principal
from app.core.enums import (
    AuditAction,
    MembershipStatus,
    RestaurantStatus,
    Role,
)
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.ids import new_token, uuid7
from app.core.passwords import token_digest
from app.core.permissions import can_assign_role
from app.modules.audit import service as audit_service
from app.modules.auth.models import RefreshToken, User
from app.modules.billing import service as billing_service
from app.modules.staff.schemas import (
    InvitationCreate,
    InvitationCreatedOut,
    InvitationOut,
    MembershipOut,
    MembershipUpdate,
)
from app.modules.tenants.models import Invitation, Membership, Restaurant

INVITATION_TTL_DAYS = 7
PENDING = "pending"
EXPIRED = "expired"


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def membership_to_out(membership: Membership) -> MembershipOut:
    return MembershipOut(
        id=membership.id,
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        email=membership.user.email,
        full_name=membership.user.full_name,
        role=membership.role,
        status=membership.status,
        restaurant_id=membership.restaurant_id,
        restaurant_name=membership.restaurant.name if membership.restaurant else None,
        created_at=membership.created_at,
    )


def _invitation_status(invitation: Invitation, now: datetime) -> str:
    return EXPIRED if invitation.expires_at <= now else PENDING


async def _active_membership_count(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.status != MembershipStatus.REMOVED,
        )
    )
    return int(count or 0)


async def _pending_invitation_count(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    now = datetime.now(UTC)
    count = await session.scalar(
        select(func.count())
        .select_from(Invitation)
        .where(
            Invitation.tenant_id == tenant_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > now,
        )
    )
    return int(count or 0)


async def _revoke_membership_tokens(
    session: AsyncSession, membership_id: uuid.UUID
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.membership_id == membership_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )


async def list_memberships(
    session: AsyncSession, principal: Principal
) -> list[MembershipOut]:
    stmt = (
        select(Membership)
        .options(joinedload(Membership.user), joinedload(Membership.restaurant))
        .where(
            Membership.tenant_id == principal.tenant.id,
            Membership.status != MembershipStatus.REMOVED,
        )
    )
    if not principal.tenant_wide:
        stmt = stmt.where(Membership.restaurant_id == principal.membership.restaurant_id)
    rows = await session.scalars(stmt.order_by(Membership.created_at.asc()))
    return [membership_to_out(item) for item in rows.unique()]


async def create_invitation(
    session: AsyncSession,
    principal: Principal,
    payload: InvitationCreate,
    *,
    request_meta: dict,
) -> InvitationCreatedOut:
    if not can_assign_role(principal.role, payload.role):
        raise Forbidden("You cannot invite a user with that role")

    target_restaurant_id = payload.restaurant_id
    if not principal.tenant_wide:
        if target_restaurant_id is None:
            target_restaurant_id = principal.membership.restaurant_id
        elif target_restaurant_id != principal.membership.restaurant_id:
            raise Forbidden("You can only invite staff to your own branch")

    if target_restaurant_id is not None:
        restaurant = await session.scalar(
            select(Restaurant).where(
                Restaurant.id == target_restaurant_id,
                Restaurant.tenant_id == principal.tenant.id,
            )
        )
        if restaurant is None:
            raise NotFound("Restaurant not found")
        if restaurant.status is not RestaurantStatus.ACTIVE:
            raise Conflict("branch_inactive", "Cannot invite staff to an inactive branch")

    email = _normalize_email(payload.email)
    if email == principal.user.email:
        raise Conflict("self_invite", "You cannot invite yourself")

    existing_user = await session.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        existing_membership = await session.scalar(
            select(Membership.id).where(
                Membership.tenant_id == principal.tenant.id,
                Membership.user_id == existing_user.id,
                Membership.status != MembershipStatus.REMOVED,
            )
        )
        if existing_membership:
            raise Conflict("already_member", "This user is already a member of your team")

    now = datetime.now(UTC)
    pending = await session.scalar(
        select(Invitation.id).where(
            Invitation.tenant_id == principal.tenant.id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > now,
        )
    )
    if pending:
        raise Conflict("invitation_pending", "An invitation is already pending for this email")

    staff_count = await _active_membership_count(session, principal.tenant.id)
    pending_count = await _pending_invitation_count(session, principal.tenant.id)
    await billing_service.assert_staff_limit(
        session, principal.tenant.id, staff_count + pending_count
    )

    raw_token = new_token(32)
    invitation = Invitation(
        id=uuid7(),
        tenant_id=principal.tenant.id,
        email=email,
        restaurant_id=target_restaurant_id,
        role=payload.role,
        token_hash=token_digest(raw_token),
        invited_by_user_id=principal.user.id,
        expires_at=now + timedelta(days=INVITATION_TTL_DAYS),
    )
    session.add(invitation)
    await audit_service.record(
        session,
        tenant_id=principal.tenant.id,
        action=AuditAction.INVITATION_CREATED,
        actor_user_id=principal.user.id,
        actor_membership_id=principal.membership.id,
        entity_type="invitation",
        entity_id=str(invitation.id),
        ip_address=request_meta.get("ip_address"),
        request_id=request_meta.get("request_id"),
        meta={"email": email, "role": payload.role.value},
    )
    await session.flush()
    return InvitationCreatedOut(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        restaurant_id=invitation.restaurant_id,
        expires_at=invitation.expires_at,
        invite_token=raw_token,
    )


async def list_invitations(
    session: AsyncSession, principal: Principal
) -> list[InvitationOut]:
    stmt = (
        select(Invitation)
        .options(joinedload(Invitation.restaurant))
        .where(
            Invitation.tenant_id == principal.tenant.id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    )
    if not principal.tenant_wide:
        stmt = stmt.where(Invitation.restaurant_id == principal.membership.restaurant_id)
    rows = await session.scalars(stmt.order_by(Invitation.created_at.desc()))
    now = datetime.now(UTC)
    return [
        InvitationOut(
            id=item.id,
            email=item.email,
            role=item.role,
            restaurant_id=item.restaurant_id,
            restaurant_name=item.restaurant.name if item.restaurant else None,
            status=_invitation_status(item, now),
            expires_at=item.expires_at,
            created_at=item.created_at,
        )
        for item in rows.unique()
    ]


async def revoke_invitation(
    session: AsyncSession,
    principal: Principal,
    invitation_id: uuid.UUID,
    *,
    request_meta: dict,
) -> None:
    stmt = select(Invitation).where(
        Invitation.id == invitation_id,
        Invitation.tenant_id == principal.tenant.id,
    )
    if not principal.tenant_wide:
        stmt = stmt.where(Invitation.restaurant_id == principal.membership.restaurant_id)
    invitation = await session.scalar(stmt)
    if invitation is None:
        raise NotFound("Invitation not found")
    if invitation.accepted_at is not None:
        raise Conflict("invitation_accepted", "This invitation has already been accepted")
    if invitation.revoked_at is not None:
        return
    invitation.revoked_at = datetime.now(UTC)
    await audit_service.record(
        session,
        tenant_id=principal.tenant.id,
        action=AuditAction.INVITATION_REVOKED,
        actor_user_id=principal.user.id,
        actor_membership_id=principal.membership.id,
        entity_type="invitation",
        entity_id=str(invitation.id),
        ip_address=request_meta.get("ip_address"),
        request_id=request_meta.get("request_id"),
    )


async def accept_invitation(
    session: AsyncSession,
    principal: Principal,
    raw_token: str,
    *,
    request_meta: dict,
) -> MembershipOut:
    digest = token_digest(raw_token)
    await set_rls_context(session, invitation_token=digest)
    invitation = await session.scalar(
        select(Invitation)
        .options(joinedload(Invitation.restaurant))
        .where(Invitation.token_hash == digest)
    )
    now = datetime.now(UTC)
    if invitation is None:
        raise NotFound("Invitation not found")
    if _normalize_email(invitation.email) != principal.user.email:
        raise Forbidden("This invitation was issued to a different email address")
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise Conflict("invitation_used", "This invitation has already been used")
    if invitation.expires_at <= now:
        raise Conflict("invitation_expired", "This invitation has expired")

    await set_rls_context(
        session, tenant_id=invitation.tenant_id, user_id=principal.user.id
    )
    existing = await session.scalar(
        select(Membership).where(
            Membership.tenant_id == invitation.tenant_id,
            Membership.user_id == principal.user.id,
            Membership.status != MembershipStatus.REMOVED,
        )
    )
    if existing is not None:
        raise Conflict("already_member", "You are already a member of this restaurant")

    staff_count = await _active_membership_count(session, invitation.tenant_id)
    await billing_service.assert_staff_limit(session, invitation.tenant_id, staff_count)

    if invitation.restaurant_id is not None:
        restaurant = await session.scalar(
            select(Restaurant).where(
                Restaurant.id == invitation.restaurant_id,
                Restaurant.tenant_id == invitation.tenant_id,
            )
        )
        if restaurant is None:
            raise NotFound("Restaurant not found")

    membership = Membership(
        tenant_id=invitation.tenant_id,
        user_id=principal.user.id,
        restaurant_id=invitation.restaurant_id,
        role=invitation.role,
        status=MembershipStatus.ACTIVE,
    )
    session.add(membership)
    invitation.accepted_at = now
    await audit_service.record(
        session,
        tenant_id=invitation.tenant_id,
        action=AuditAction.INVITATION_ACCEPTED,
        actor_user_id=principal.user.id,
        actor_membership_id=membership.id,
        entity_type="invitation",
        entity_id=str(invitation.id),
        ip_address=request_meta.get("ip_address"),
        request_id=request_meta.get("request_id"),
    )
    await session.flush()
    await session.refresh(membership, attribute_names=["user", "restaurant"])
    return membership_to_out(membership)


async def _load_staff_membership(
    session: AsyncSession, principal: Principal, membership_id: uuid.UUID
) -> Membership:
    stmt = (
        select(Membership)
        .options(joinedload(Membership.user), joinedload(Membership.restaurant))
        .where(
            Membership.id == membership_id,
            Membership.tenant_id == principal.tenant.id,
            Membership.status != MembershipStatus.REMOVED,
        )
    )
    if not principal.tenant_wide:
        stmt = stmt.where(Membership.restaurant_id == principal.membership.restaurant_id)
    membership = await session.scalar(stmt)
    if membership is None:
        raise NotFound("Staff member not found")
    return membership


async def update_membership(
    session: AsyncSession,
    principal: Principal,
    membership_id: uuid.UUID,
    payload: MembershipUpdate,
    *,
    request_meta: dict,
) -> MembershipOut:
    target = await _load_staff_membership(session, principal, membership_id)
    if target.role is Role.OWNER:
        raise Forbidden("The owner membership cannot be modified")
    if target.user_id == principal.user.id:
        raise Forbidden("You cannot modify your own membership")
    if not can_assign_role(principal.role, target.role):
        raise Forbidden("You cannot modify a member with that role")

    changes: dict = {}
    if payload.role is not None and payload.role is not target.role:
        if not can_assign_role(principal.role, payload.role):
            raise Forbidden("You cannot assign that role")
        target.role = payload.role
        changes["role"] = payload.role.value
    if payload.status is not None and payload.status != target.status.value:
        target.status = MembershipStatus(payload.status)
        changes["status"] = payload.status
        if payload.status == "suspended":
            await _revoke_membership_tokens(session, target.id)

    if changes:
        await audit_service.record(
            session,
            tenant_id=principal.tenant.id,
            action=AuditAction.MEMBERSHIP_UPDATED,
            actor_user_id=principal.user.id,
            actor_membership_id=principal.membership.id,
            entity_type="membership",
            entity_id=str(target.id),
            ip_address=request_meta.get("ip_address"),
            request_id=request_meta.get("request_id"),
            meta=changes,
        )
        await session.flush()
    return membership_to_out(target)


async def remove_membership(
    session: AsyncSession,
    principal: Principal,
    membership_id: uuid.UUID,
    *,
    request_meta: dict,
) -> None:
    target = await _load_staff_membership(session, principal, membership_id)
    if target.role is Role.OWNER:
        raise Forbidden("The owner membership cannot be removed")
    if target.user_id == principal.user.id:
        raise Forbidden("You cannot remove your own membership")
    if not can_assign_role(principal.role, target.role):
        raise Forbidden("You cannot remove a member with that role")

    target.status = MembershipStatus.REMOVED
    await _revoke_membership_tokens(session, target.id)
    await audit_service.record(
        session,
        tenant_id=principal.tenant.id,
        action=AuditAction.MEMBERSHIP_REMOVED,
        actor_user_id=principal.user.id,
        actor_membership_id=principal.membership.id,
        entity_type="membership",
        entity_id=str(target.id),
        ip_address=request_meta.get("ip_address"),
        request_id=request_meta.get("request_id"),
    )
