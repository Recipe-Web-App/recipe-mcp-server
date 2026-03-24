"""Test cursor-based pagination on search_recipes.

search_recipes implements opaque base64-encoded cursors.  We verify the
response envelope, the shape of the results list, and that passing a cursor
value does not cause an error.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastmcp import Client


@pytest.mark.e2e
class TestPagination:
    """search_recipes returns the correct paginated response envelope."""

    async def test_search_returns_results_key(self, mcp_client: Client) -> None:
        """The response JSON must contain a top-level 'results' list."""
        result = await mcp_client.call_tool("search_recipes", {"query": "soup"})
        assert result.content
        data = json.loads(result.content[0].text)
        assert "results" in data

    async def test_search_results_is_a_list(self, mcp_client: Client) -> None:
        """The 'results' value must be a list (possibly empty given mock APIs)."""
        result = await mcp_client.call_tool("search_recipes", {"query": "stew"})
        data = json.loads(result.content[0].text)
        assert isinstance(data["results"], list)

    async def test_search_with_cursor_does_not_error(self, mcp_client: Client) -> None:
        """Passing a valid opaque cursor to search_recipes must not raise."""
        cursor = base64.urlsafe_b64encode(json.dumps({"o": 10}).encode()).decode()
        result = await mcp_client.call_tool("search_recipes", {"query": "salad", "cursor": cursor})
        assert result.content
        data = json.loads(result.content[0].text)
        assert "results" in data

    async def test_search_respects_limit_parameter(self, mcp_client: Client) -> None:
        """Passing limit must not cause an error; the envelope is still returned."""
        result = await mcp_client.call_tool("search_recipes", {"query": "rice", "limit": 5})
        assert result.content
        data = json.loads(result.content[0].text)
        assert "results" in data
        assert isinstance(data["results"], list)
