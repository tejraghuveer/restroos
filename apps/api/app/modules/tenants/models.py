from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    MembershipStatus,
    RestaurantStatus,
    Role,
    TenantStatus,
)
from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import UTCDateTime, enum_type

if TYPE_CHECKING:
    from app.modules.auth.models import User


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        enum_type(TenantStatus, "tenant_status"), nullable=False, default=TenantStatus.TRIAL
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")

    restaurants: Mapped[list[Restaurant]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class Restaurant(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "restaurants"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_restaurants_tenant_slug"),)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[RestaurantStatus] = mapped_column(
        enum_type(RestaurantStatus, "restaurant_status"),
        nullable=False,
        default=RestaurantStatus.ACTIVE,
    )

    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(16))
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="IN")

    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    gstin: Mapped[str | None] = mapped_column(String(15))
    tax_inclusive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    service_charge_bp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    tenant: Mapped[Tenant] = relationship(back_populates="restaurants")
    memberships: Mapped[list[Membership]] = relationship(back_populates="restaurant")


class Membership(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        # A user has at most one tenant-wide membership per tenant...
        Index(
            "uq_memberships_tenant_user_wide",
            "tenant_id",
            "user_id",
            unique=True,
            postgresql_where=text("restaurant_id IS NULL"),
            sqlite_where=text("restaurant_id IS NULL"),
        ),
        # ...and at most one membership per branch.
        Index(
            "uq_memberships_tenant_user_branch",
            "tenant_id",
            "user_id",
            "restaurant_id",
            unique=True,
            postgresql_where=text("restaurant_id IS NOT NULL"),
            sqlite_where=text("restaurant_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    restaurant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[Role] = mapped_column(enum_type(Role, "membership_role"), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(
        enum_type(MembershipStatus, "membership_status"),
        nullable=False,
        default=MembershipStatus.ACTIVE,
    )
    pin_hash: Mapped[str | None] = mapped_column(String(255))

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
    restaurant: Mapped[Restaurant | None] = relationship(back_populates="memberships")


class Invitation(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    __tablename__ = "invitations"

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    restaurant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(enum_type(Role, "invitation_role"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    restaurant: Mapped[Restaurant | None] = relationship()
