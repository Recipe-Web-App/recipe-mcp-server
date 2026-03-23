"""Shared fixtures for MCP end-to-end tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import respx
from fastmcp import Client, FastMCP


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


@pytest.fixture
def mcp_server(_test_env: None) -> FastMCP:
    """Create a fresh FastMCP server instance with test configuration."""
    from recipe_mcp_server.server import create_server

    return create_server()


@pytest_asyncio.fixture
async def mcp_client(mcp_server: FastMCP) -> AsyncIterator[Client]:
    """MCP client connected to the test server via in-process transport."""
    async with respx.mock:
        respx.route().mock(return_value=httpx.Response(200, json={}))
        client = Client(transport=mcp_server)
        async with client:
            yield client
