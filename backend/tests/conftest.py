"""Shared fixtures for the backend test suite.

Admin-plane tests (users, OIDC providers, signing keys) never touch a real
Postgres -- ``db_session`` gives each test its own in-memory SQLite engine
with the ORM schema created directly from ``Base.metadata`` (bypassing
Alembic, which is the production migration path; see ``app/db.py``).
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base
from app.db import models  # noqa: F401  (registers models on Base.metadata)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A fresh in-memory SQLite session, schema created, torn down after the test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def wire_db_session(db_session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Override the app's ``get_db_session`` dependency with the in-memory SQLite
    ``db_session`` above, for the duration of one test -- for tests that exercise a
    router through ``TestClient`` rather than the ORM layer directly."""
    from app.db import get_db_session
    from app.main import app

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override
    try:
        yield db_session
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture(autouse=True)
def admin_db_encryption_key(monkeypatch):
    """Every test gets a valid Fernet key for app.crypto by default.

    Individual tests that need to exercise the "unconfigured" path should
    monkeypatch settings.admin_db_encryption_key back to "" themselves.
    """
    from cryptography.fernet import Fernet

    from app.config import settings

    monkeypatch.setattr(settings, "admin_db_encryption_key", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def no_real_admin_db_migrations(monkeypatch):
    """app.main.lifespan() runs Alembic against admin-db on every startup.

    The test suite never has a live admin-db to migrate -- Alembic itself is
    exercised manually (see docs/dev notes) and the ORM layer is exercised
    against in-memory SQLite via ``db_session`` above. Stub the migration
    step out so tests that invoke ``lifespan()`` directly (e.g. test_config.py's
    BLK-3 guard tests) don't need a live Postgres. Tests that specifically
    want to assert migrations run should monkeypatch this back themselves.
    """
    import app.main

    monkeypatch.setattr(app.main, "_run_admin_db_migrations", lambda: None)
