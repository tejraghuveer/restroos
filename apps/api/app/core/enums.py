from __future__ import annotations

from enum import StrEnum


class TenantStatus(StrEnum):
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"


class RestaurantStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    CASHIER = "cashier"
    WAITER = "waiter"
    KITCHEN = "kitchen"
    INVENTORY = "inventory"
    VIEWER = "viewer"


class MembershipStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    TRIAL = "trial"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class AuditAction(StrEnum):
    TENANT_REGISTERED = "tenant.registered"
    USER_LOGGED_IN = "user.logged_in"
    USER_LOGGED_OUT = "user.logged_out"
    TOKEN_REFRESHED = "token.refreshed"  # noqa: S105 - audit action code
    TOKEN_REUSE_DETECTED = "token.reuse_detected"  # noqa: S105 - audit action code
    CONTEXT_SWITCHED = "context.switched"
    TENANT_UPDATED = "tenant.updated"
    RESTAURANT_CREATED = "restaurant.created"
    INVITATION_CREATED = "invitation.created"
    INVITATION_REVOKED = "invitation.revoked"
    INVITATION_ACCEPTED = "invitation.accepted"
    MEMBERSHIP_UPDATED = "membership.updated"
    MEMBERSHIP_REMOVED = "membership.removed"
