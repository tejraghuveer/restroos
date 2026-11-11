from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuditAction
from app.modules.audit.models import AuditLog


async def record(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: AuditAction,
    actor_user_id: uuid.UUID | None = None,
    actor_membership_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_membership_id=actor_membership_id,
        action=action.value,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        request_id=request_id,
        meta=meta or {},
    )
    session.add(entry)
    return entry
