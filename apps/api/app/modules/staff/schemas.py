from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, model_validator

from app.core.enums import MembershipStatus, Role


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Role
    restaurant_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _no_owner_invites(self) -> InvitationCreate:
        if self.role is Role.OWNER:
            raise ValueError("Ownership cannot be transferred by invitation")
        return self


class InvitationCreatedOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: Role
    restaurant_id: uuid.UUID | None
    expires_at: datetime
    invite_token: str


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: Role
    restaurant_id: uuid.UUID | None
    restaurant_name: str | None
    status: str
    expires_at: datetime
    created_at: datetime


class MembershipOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: Role
    status: MembershipStatus
    restaurant_id: uuid.UUID | None
    restaurant_name: str | None
    created_at: datetime


class MembershipUpdate(BaseModel):
    role: Role | None = None
    status: Literal["active", "suspended"] | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> MembershipUpdate:
        if self.role is None and self.status is None:
            raise ValueError("role or status is required")
        return self


class InvitationAcceptResult(BaseModel):
    membership: MembershipOut
    tenant_id: uuid.UUID
    membership_id: uuid.UUID
