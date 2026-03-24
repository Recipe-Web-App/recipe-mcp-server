"""Test the seasonal tool registration.

get_holiday_recipes is always registered in the tool list.  Outside of
November and December the tool returns an informational error payload rather
than results.  Inside those months it searches for keyword-matched recipes.

The test date (2026-03-23) is outside the holiday season, so we expect the
"only available Nov-Dec" payload when the tool is called.
"""

from __future__ import annotations

import json

import pytest
from fastmcp import Client

HOLIDAY_TOOL = "get_holiday_recipes"


@pytest.mark.e2e
class TestSeasonalVisibility:
    """get_holiday_recipes is registered and callable year-round."""

    async def test_get_holiday_recipes_in_tool_list(self, mcp_client: Client) -> None:
        """The seasonal tool must appear in list_tools regardless of current month."""
        tools = await mcp_client.list_tools()
        names = {t.name for t in tools}
        assert HOLIDAY_TOOL in names

    async def test_get_holiday_recipes_returns_response(self, mcp_client: Client) -> None:
        """Calling get_holiday_recipes must not raise; outside Nov-Dec it returns
        the availability error payload."""
        result = await mcp_client.call_tool(HOLIDAY_TOOL, {"holiday": "christmas"})
        assert result.content
        text = result.content[0].text
        assert text is not None
        # Outside the holiday season the tool returns a JSON error object.
        data = json.loads(text)
        assert "error" in data or "recipes" in data

    async def test_get_holiday_recipes_off_season_message(self, mcp_client: Client) -> None:
        """Outside Nov-Dec the tool returns the off-season error message."""
        result = await mcp_client.call_tool(HOLIDAY_TOOL, {})
        data = json.loads(result.content[0].text)
        # Current test date is March 2026 — outside holiday season.
        assert "error" in data
        assert "November" in data["error"] or "november" in data["error"].lower()

    async def test_get_holiday_recipes_alternate_holiday(self, mcp_client: Client) -> None:
        """Passing a different holiday keyword (thanksgiving) also returns a response."""
        result = await mcp_client.call_tool(HOLIDAY_TOOL, {"holiday": "thanksgiving"})
        assert result.content
        data = json.loads(result.content[0].text)
        assert "error" in data or "recipes" in data
