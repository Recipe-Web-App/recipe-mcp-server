"""Shared fixtures for integration tests with realistic API response mocking."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import respx
from fastmcp import Client, FastMCP
from sqlalchemy.pool import NullPool

import recipe_mcp_server.db.engine as _engine_mod

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "api_responses"


@pytest.fixture
def _test_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Configure environment variables for a test server instance."""
    monkeypatch.setenv("RECIPE_MCP_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("RECIPE_MCP_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("RECIPE_MCP_LOG_FORMAT", "console")
    monkeypatch.setenv("RECIPE_MCP_REDIS_URL", "redis://localhost:1/0")
    monkeypatch.setenv("RECIPE_MCP_SPOONACULAR_API_KEY", "test-key")
    monkeypatch.setenv("RECIPE_MCP_USDA_API_KEY", "test-key")
    from recipe_mcp_server.config import get_settings

    get_settings.cache_clear()

    # Force NullPool so aiosqlite background threads don't outlive the
    # event loop — the standard fix for the "Event loop is closed" race.
    _original = _engine_mod.create_async_engine

    def _with_null_pool(*args: object, **kwargs: object) -> object:
        kwargs.setdefault("poolclass", NullPool)
        return _original(*args, **kwargs)

    monkeypatch.setattr(_engine_mod, "create_async_engine", _with_null_pool)


@pytest.fixture
def mcp_server(_test_env: None) -> FastMCP:
    """Create a fresh FastMCP server instance with test configuration."""
    from recipe_mcp_server.server import create_server

    return create_server()


@pytest_asyncio.fixture
async def mcp_client(mcp_server: FastMCP) -> AsyncIterator[Client]:
    """MCP client with realistic API response mocking from fixture files."""
    mealdb_search = json.loads((FIXTURES_DIR / "themealdb" / "search.json").read_text())
    usda_search = json.loads((FIXTURES_DIR / "usda" / "search.json").read_text())

    async with respx.mock:
        respx.get(url__startswith="https://www.themealdb.com/").mock(
            return_value=httpx.Response(200, json=mealdb_search)
        )
        respx.get(url__startswith="https://api.nal.usda.gov/").mock(
            return_value=httpx.Response(200, json=usda_search)
        )
        # Catch-all for other API clients
        respx.route().mock(return_value=httpx.Response(200, json={}))

        client = Client(transport=mcp_server)
        async with client:
            yield client
