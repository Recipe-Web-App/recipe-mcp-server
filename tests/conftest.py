"""Shared test fixtures for the Recipe MCP Server test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from recipe_mcp_server.config import Settings
from recipe_mcp_server.db.repository import (
    AuditRepo,
    FavoriteRepo,
    MealPlanRepo,
    RecipeRepo,
    UserRepo,
)
from recipe_mcp_server.db.tables import Base


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings configured for testing."""
    monkeypatch.setenv("RECIPE_MCP_DB_PATH", ":memory:")
    monkeypatch.setenv("RECIPE_MCP_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("RECIPE_MCP_LOG_FORMAT", "console")
    # Clear lru_cache so new env vars are picked up
    from recipe_mcp_server.config import get_settings

    get_settings.cache_clear()
    settings = Settings()
    return settings


@pytest_asyncio.fixture
async def engine():
    """In-memory SQLite engine with all tables created.

    Uses NullPool to avoid aiosqlite background-thread warnings:
    connections are closed immediately on return, so no idle threads
    race against pytest-asyncio's event-loop teardown.
    """
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the in-memory engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def recipe_repo(session_factory: async_sessionmaker[AsyncSession]) -> RecipeRepo:
    return RecipeRepo(session_factory)


@pytest_asyncio.fixture
async def user_repo(session_factory: async_sessionmaker[AsyncSession]) -> UserRepo:
    return UserRepo(session_factory)


@pytest_asyncio.fixture
async def favorite_repo(session_factory: async_sessionmaker[AsyncSession]) -> FavoriteRepo:
    return FavoriteRepo(session_factory)


@pytest_asyncio.fixture
async def meal_plan_repo(session_factory: async_sessionmaker[AsyncSession]) -> MealPlanRepo:
    return MealPlanRepo(session_factory)


@pytest_asyncio.fixture
async def audit_repo(session_factory: async_sessionmaker[AsyncSession]) -> AuditRepo:
    return AuditRepo(session_factory)


@pytest_asyncio.fixture
async def fake_redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    """In-memory Redis client for testing."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()
