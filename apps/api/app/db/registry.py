"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.modules.audit.models import AuditLog
from app.modules.auth.models import RefreshToken, User
from app.modules.billing.models import Plan, Subscription
from app.modules.tenants.models import Invitation, Membership, Restaurant, Tenant

__all__ = [
    "AuditLog",
    "Invitation",
    "Membership",
    "Plan",
    "RefreshToken",
    "Restaurant",
    "Subscription",
    "Tenant",
    "User",
]
