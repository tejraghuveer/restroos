from __future__ import annotations

from pathlib import Path

import httpx
from app.core.config import Settings
from app.db.base import Base
from app.main import create_app
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

TEST_PASSWORD = "RestroOS-Test-Pass-1"


def test_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "debug": False,
        "database_url": f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        "jwt_secret": "test-secret-that-is-longer-than-32-characters",
        "cors_origins": ["http://testserver"],
        "auth_rate_limit_per_minute": 10_000,
        "access_token_minutes": 15,
        "free_plan_max_restaurants": 5,
        "free_plan_max_staff": 50,
    }
    values.update(overrides)
    return Settings(**values)


async def create_test_app(tmp_path: Path, **overrides: object) -> FastAPI:
    settings = test_settings(tmp_path, **overrides)
    app = create_app(settings)
    async with app.state.db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    manager = LifespanManager(app)
    await manager.__aenter__()
    app.state._test_lifespan = manager
    return app


async def dispose_test_app(app: FastAPI) -> None:
    manager: LifespanManager = app.state._test_lifespan
    await manager.__aexit__(None, None, None)


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Origin": "http://testserver"},
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def register_owner(
    client: httpx.AsyncClient,
    *,
    email: str,
    business_name: str,
    full_name: str = "Test Owner",
    password: str = TEST_PASSWORD,
) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "business_name": business_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def register_with_invitation(
    client: httpx.AsyncClient,
    *,
    email: str,
    token: str,
    full_name: str = "Invited User",
    password: str = TEST_PASSWORD,
) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "invitation_token": token,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login(
    client: httpx.AsyncClient, *, email: str, password: str = TEST_PASSWORD
) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
