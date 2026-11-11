from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
        )
        if settings.is_sqlite:
            event.listen(self.engine.sync_engine, "connect", _configure_sqlite)

        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session


async def set_rls_context(
    session: AsyncSession,
    *,
    tenant_id: object | None = None,
    user_id: object | None = None,
    invitation_token: str | None = None,
) -> None:
    """Apply transaction-local Postgres RLS variables.

    On SQLite this is a no-op; tenant filtering is enforced by repositories and
    by the cross-tenant test suite. On Postgres this is the second isolation
    layer that fails closed if application code forgets a WHERE clause.
    """
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return

    await session.execute(
        text("SELECT set_config('app.tenant_id', :value, true)"),
        {"value": str(tenant_id) if tenant_id else ""},
    )
    await session.execute(
        text("SELECT set_config('app.user_id', :value, true)"),
        {"value": str(user_id) if user_id else ""},
    )
    await session.execute(
        text("SELECT set_config('app.invitation_token', :value, true)"),
        {"value": invitation_token or ""},
    )
