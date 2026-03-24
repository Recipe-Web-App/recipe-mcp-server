"""Test that tool calls produce logging output via ctx.info/debug/warning/error.

The MCP logging protocol routes ctx.info/debug/etc. calls as notifications to
the connected client.  In the test environment all external HTTP calls are
mocked, so we exercise the logging code paths by verifying the tools complete
without raising and return a text response.
"""

from __future__ import annotations

import pytest
from fastmcp import Client


@pytest.mark.e2e
class TestServerLogging:
    """Tools that emit structured log messages via ctx complete successfully."""

    async def test_search_recipes_logs_and_completes(self, mcp_client: Client) -> None:
        """search_recipes emits ctx.info and ctx.debug; verify the call succeeds."""
        result = await mcp_client.call_tool("search_recipes", {"query": "pasta"})
        assert result.content
        assert result.content[0].text is not None

    async def test_lookup_nutrition_logs_and_completes(self, mcp_client: Client) -> None:
        """lookup_nutrition emits ctx.info and ctx.debug; verify the call succeeds."""
        result = await mcp_client.call_tool("lookup_nutrition", {"food_name": "apple"})
        assert result.content
        assert result.content[0].text is not None

    async def test_get_wine_pairing_logs_and_completes(self, mcp_client: Client) -> None:
        """get_wine_pairing emits ctx.info and ctx.debug; verify the call succeeds."""
        result = await mcp_client.call_tool("get_wine_pairing", {"food": "salmon"})
        assert result.content
        assert result.content[0].text is not None
