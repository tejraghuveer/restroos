from __future__ import annotations

from pathlib import Path

import pytest_asyncio
from app.db.base import Base  # noqa: F401  (ensures metadata is populated)

from tests.helpers import client_for, create_test_app, dispose_test_app


@pytest_asyncio.fixture
async def app(tmp_path: Path):
    application = await create_test_app(tmp_path)
    yield application
    await dispose_test_app(application)


@pytest_asyncio.fixture
async def client(app):
    async with client_for(app) as http_client:
        yield http_client


@pytest_asyncio.fixture
async def make_app(tmp_path: Path):
    created = []

    async def factory(**overrides):
        application = await create_test_app(tmp_path, **overrides)
        created.append(application)
        return application

    yield factory
    for application in created:
        await dispose_test_app(application)
