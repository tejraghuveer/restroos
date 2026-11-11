"""PostgreSQL row-level-security regression tests.

These tests exercise the database-level isolation layer that protects tenant
data even if application code forgets a ``WHERE tenant_id = ...`` clause. They
run only against a real PostgreSQL database, because SQLite has no RLS.

Preparation (mirrors the CI job):

1. Create the low-privilege runtime role and grants: ``infra/postgres/init.sql``
2. Apply migrations as the schema owner: ``alembic upgrade head``
3. Lock down audit history: ``infra/postgres/harden.sql``
4. Export the runtime role URL::

       TEST_POSTGRES_URL=postgresql+asyncpg://restroos_app:<password>@localhost:5432/restroos

Without ``TEST_POSTGRES_URL`` the whole module is skipped, so the normal SQLite
development and test workflow is unaffected.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from app.core.ids import uuid7
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL is not set; PostgreSQL isolation tests need a real database",
)

TENANT_SETTING = "app.tenant_id"
USER_SETTING = "app.user_id"


@dataclass(frozen=True)
class TenantFixture:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    branch_name: str


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    assert POSTGRES_URL, "skipif should have prevented this"
    engine = create_async_engine(POSTGRES_URL, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _set_context(
    connection: AsyncConnection,
    *,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    invitation_token: str | None = None,
) -> None:
    """Set transaction-local RLS variables, exactly like app.core.db does."""

    await connection.execute(
        text("SELECT set_config(:key, :value, true)"),
        {"key": TENANT_SETTING, "value": str(tenant_id) if tenant_id else ""},
    )
    await connection.execute(
        text("SELECT set_config(:key, :value, true)"),
        {"key": USER_SETTING, "value": str(user_id) if user_id else ""},
    )
    await connection.execute(
        text("SELECT set_config('app.invitation_token', :value, true)"),
        {"value": invitation_token or ""},
    )


async def _create_tenant_with_branch(engine: AsyncEngine, *, name: str) -> TenantFixture:
    suffix = uuid.uuid4().hex[:10]
    tenant_id = uuid7()
    branch_id = uuid7()
    branch_name = f"Branch {name}"

    async with engine.begin() as connection:
        await _set_context(connection, tenant_id=tenant_id)
        await connection.execute(
            text(
                "INSERT INTO tenants (id, slug, name, status, currency, timezone) "
                "VALUES (:id, :slug, :name, 'trial', 'INR', 'Asia/Kolkata')"
            ),
            {"id": tenant_id, "slug": f"{name}-{suffix}", "name": name},
        )
        await connection.execute(
            text(
                "INSERT INTO restaurants ("
                "id, tenant_id, name, slug, status, country, timezone, currency, "
                "tax_inclusive, service_charge_bp"
                ") VALUES ("
                ":id, :tenant_id, :name, :slug, 'active', 'IN', 'Asia/Kolkata', "
                "'INR', false, 0"
                ")"
            ),
            {
                "id": branch_id,
                "tenant_id": tenant_id,
                "name": branch_name,
                "slug": f"{name}-{suffix}",
            },
        )
        # Give the fail-closed test a tenant-scoped audit row to (not) see.
        await connection.execute(
            text(
                "INSERT INTO audit_logs (id, tenant_id, action, meta) "
                "VALUES (:id, :tenant_id, 'test.bootstrap', '{}')"
            ),
            {"id": uuid7(), "tenant_id": tenant_id},
        )

    return TenantFixture(tenant_id=tenant_id, branch_id=branch_id, branch_name=branch_name)


async def _delete_tenant(engine: AsyncEngine, tenant_id: uuid.UUID) -> None:
    async with engine.begin() as connection:
        await _set_context(connection, tenant_id=tenant_id)
        await connection.execute(
            text("DELETE FROM memberships WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        await connection.execute(
            text("DELETE FROM restaurants WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        await connection.execute(
            text("DELETE FROM tenants WHERE id = :tenant_id"),
            {"tenant_id": tenant_id},
        )


async def test_runtime_role_cannot_bypass_row_level_security(engine: AsyncEngine) -> None:
    """An owner role would silently bypass every policy, so fail loudly."""

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT current_user, "
                    "       pg_get_userbyid(c.relowner) AS table_owner, "
                    "       c.relrowsecurity "
                    "FROM pg_class c WHERE c.relname = 'restaurants'"
                )
            )
        ).one()

    current_user, table_owner, rls_enabled = row
    assert current_user == "restroos_app", (
        "Point TEST_POSTGRES_URL at the low-privilege runtime role"
    )
    assert current_user != table_owner, "RLS is bypassed when the app owns the tables"
    assert rls_enabled is True


async def test_audit_history_is_append_only(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        can_update = (
            await connection.execute(
                text("SELECT has_table_privilege(current_user, 'audit_logs', 'UPDATE')")
            )
        ).scalar_one()
        can_delete = (
            await connection.execute(
                text("SELECT has_table_privilege(current_user, 'audit_logs', 'DELETE')")
            )
        ).scalar_one()

    assert can_update is False, "Apply infra/postgres/harden.sql after migrations"
    assert can_delete is False, "Apply infra/postgres/harden.sql after migrations"


async def test_cross_tenant_reads_and_writes_are_blocked(engine: AsyncEngine) -> None:
    tenant_a = await _create_tenant_with_branch(engine, name="rls-a")
    tenant_b = await _create_tenant_with_branch(engine, name="rls-b")

    try:
        # Reads and writes are confined to the tenant claim.
        async with engine.begin() as connection:
            await _set_context(connection, tenant_id=tenant_a.tenant_id)

            visible = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM restaurants "
                        "WHERE tenant_id IN (:a, :b)"
                    ),
                    {"a": tenant_a.tenant_id, "b": tenant_b.tenant_id},
                )
            ).scalar_one()
            assert visible == 1, "only the caller's branch must be visible"

            foreign_branch = (
                await connection.execute(
                    text("SELECT id FROM restaurants WHERE id = :id"),
                    {"id": tenant_b.branch_id},
                )
            ).one_or_none()
            assert foreign_branch is None

            update = await connection.execute(
                text("UPDATE restaurants SET name = 'hijacked' WHERE id = :id"),
                {"id": tenant_b.branch_id},
            )
            assert update.rowcount == 0

            delete = await connection.execute(
                text("DELETE FROM restaurants WHERE id = :id"),
                {"id": tenant_b.branch_id},
            )
            assert delete.rowcount == 0

            visible_tenants = (
                await connection.execute(
                    text("SELECT count(*) FROM tenants WHERE id IN (:a, :b)"),
                    {"a": tenant_a.tenant_id, "b": tenant_b.tenant_id},
                )
            ).scalar_one()
            assert visible_tenants == 1, "only the caller's tenant must be visible"

        # A forged INSERT with another tenant's id fails the WITH CHECK clause.
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await _set_context(connection, tenant_id=tenant_a.tenant_id)
                await connection.execute(
                    text(
                        "INSERT INTO restaurants ("
                        "id, tenant_id, name, slug, status, country, timezone, currency, "
                        "tax_inclusive, service_charge_bp"
                        ") VALUES ("
                        ":id, :tenant_id, 'forged', 'forged', 'active', 'IN', "
                        "'Asia/Kolkata', 'INR', false, 0"
                        ")"
                    ),
                    {"id": uuid7(), "tenant_id": tenant_b.tenant_id},
                )

        # Tenant B's data is intact after the attempts above.
        async with engine.begin() as connection:
            await _set_context(connection, tenant_id=tenant_b.tenant_id)
            name = (
                await connection.execute(
                    text("SELECT name FROM restaurants WHERE id = :id"),
                    {"id": tenant_b.branch_id},
                )
            ).scalar_one()
            assert name == tenant_b.branch_name
    finally:
        await _delete_tenant(engine, tenant_a.tenant_id)
        await _delete_tenant(engine, tenant_b.tenant_id)


async def test_missing_tenant_context_fails_closed(engine: AsyncEngine) -> None:
    tenant = await _create_tenant_with_branch(engine, name="rls-closed")

    try:
        async with engine.begin() as connection:
            await _set_context(connection)  # no tenant, no user, no invitation

            assert (
                await connection.execute(
                    text("SELECT count(*) FROM restaurants WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant.tenant_id},
                )
            ).scalar_one() == 0
            assert (
                await connection.execute(
                    text("SELECT count(*) FROM tenants WHERE id = :tenant_id"),
                    {"tenant_id": tenant.tenant_id},
                )
            ).scalar_one() == 0
            assert (
                await connection.execute(
                    text("SELECT count(*) FROM memberships WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant.tenant_id},
                )
            ).scalar_one() == 0
            assert (
                await connection.execute(
                    text("SELECT count(*) FROM audit_logs WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant.tenant_id},
                )
            ).scalar_one() == 0
    finally:
        await _delete_tenant(engine, tenant.tenant_id)


async def test_user_membership_discovery_is_scoped_to_the_user(engine: AsyncEngine) -> None:
    """Login/tenant switching needs cross-tenant membership reads for the user only."""

    tenant_a = await _create_tenant_with_branch(engine, name="rls-user-a")
    tenant_b = await _create_tenant_with_branch(engine, name="rls-user-b")
    user_id = uuid7()
    stranger_id = uuid7()
    suffix = uuid.uuid4().hex[:10]

    async with engine.begin() as connection:
        for user, label in ((user_id, "member"), (stranger_id, "stranger")):
            await connection.execute(
                text(
                    "INSERT INTO users ("
                    "id, email, password_hash, full_name, is_active, is_platform_admin"
                    ") VALUES (:id, :email, 'not-a-real-hash', :name, true, false)"
                ),
                {
                    "id": user,
                    "email": f"{label}-{suffix}@rls.example",
                    "name": label,
                },
            )

    async with engine.begin() as connection:
        await _set_context(connection, tenant_id=tenant_a.tenant_id)
        await connection.execute(
            text(
                "INSERT INTO memberships (id, tenant_id, user_id, role, status) "
                "VALUES (:id, :tenant_id, :user_id, 'owner', 'active')"
            ),
            {"id": uuid7(), "tenant_id": tenant_a.tenant_id, "user_id": user_id},
        )
    async with engine.begin() as connection:
        await _set_context(connection, tenant_id=tenant_b.tenant_id)
        await connection.execute(
            text(
                "INSERT INTO memberships (id, tenant_id, user_id, role, status) "
                "VALUES (:id, :tenant_id, :user_id, 'owner', 'active')"
            ),
            {"id": uuid7(), "tenant_id": tenant_b.tenant_id, "user_id": user_id},
        )

    try:
        async with engine.begin() as connection:
            await _set_context(connection, user_id=user_id)

            # The user can discover both memberships and both tenants...
            member_tenants = (
                await connection.execute(text("SELECT tenant_id FROM memberships"))
            ).scalars().all()
            assert set(member_tenants) == {tenant_a.tenant_id, tenant_b.tenant_id}

            visible_tenants = (
                await connection.execute(text("SELECT id FROM tenants"))
            ).scalars().all()
            assert set(visible_tenants) == {tenant_a.tenant_id, tenant_b.tenant_id}

            # ...but still cannot read the tenant's business rows without a
            # tenant claim.
            assert (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM restaurants "
                        "WHERE tenant_id IN (:a, :b)"
                    ),
                    {"a": tenant_a.tenant_id, "b": tenant_b.tenant_id},
                )
            ).scalar_one() == 0

        async with engine.begin() as connection:
            await _set_context(connection, user_id=stranger_id)
            assert (
                await connection.execute(text("SELECT count(*) FROM memberships"))
            ).scalar_one() == 0
            assert (
                await connection.execute(text("SELECT count(*) FROM tenants"))
            ).scalar_one() == 0

        # A user claim alone must not allow writing tenant-scoped rows.
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await _set_context(connection, user_id=user_id)
                await connection.execute(
                    text(
                        "INSERT INTO memberships (id, tenant_id, user_id, role, status) "
                        "VALUES (:id, :tenant_id, :user_id, 'cashier', 'active')"
                    ),
                    {"id": uuid7(), "tenant_id": tenant_a.tenant_id, "user_id": stranger_id},
                )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM memberships WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            await connection.execute(
                text("DELETE FROM users WHERE id IN (:a, :b)"),
                {"a": user_id, "b": stranger_id},
            )
        await _delete_tenant(engine, tenant_a.tenant_id)
        await _delete_tenant(engine, tenant_b.tenant_id)
