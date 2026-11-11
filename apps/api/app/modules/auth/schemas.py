from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.enums import Role


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    business_name: str | None = Field(default=None, min_length=2, max_length=160)
    restaurant_name: str | None = Field(default=None, min_length=2, max_length=160)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    invitation_token: str | None = Field(default=None, min_length=20, max_length=200)

    @model_validator(mode="after")
    def _require_business_for_new_tenant(self) -> RegisterRequest:
        if not self.invitation_token and not self.business_name:
            raise ValueError("business_name is required for self-service registration")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class SwitchContextRequest(BaseModel):
    membership_id: uuid.UUID | None = None
    restaurant_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_target(self) -> SwitchContextRequest:
        if self.membership_id is None and self.restaurant_id is None:
            raise ValueError("membership_id or restaurant_id is required")
        return self


class ContextOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    restaurant_id: uuid.UUID | None
    restaurant_name: str | None
    role: Role
    tenant_wide: bool
    permissions: list[str]


class ContextOption(BaseModel):
    membership_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    restaurant_id: uuid.UUID | None
    role: Role


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type label
    expires_in: int
    context: ContextOut
    available_contexts: list[ContextOption]


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_platform_admin: bool


class MeOut(BaseModel):
    user: UserOut
    context: ContextOut
    available_contexts: list[ContextOption]


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class InvitationCreatedOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: Role
    restaurant_id: uuid.UUID | None
    expires_at: datetime
    invite_token: str
