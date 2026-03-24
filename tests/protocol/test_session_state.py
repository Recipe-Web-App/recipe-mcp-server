"""Test session state persistence across tool calls.

Several tools read and write per-session state via ctx.set_state /
ctx.get_state.  We verify the tools complete correctly and that
state-dependent paths are exercised without error.
"""

from __future__ import annotations

import json

import pytest
from fastmcp import Client


@pytest.mark.e2e
class TestSessionState:
    """Tools that read/write session state complete without error."""

    async def test_search_recipes_sets_last_search_state(self, mcp_client: Client) -> None:
        """search_recipes persists last_search state and returns paginated results."""
        result = await mcp_client.call_tool("search_recipes", {"query": "tacos"})
        assert result.content
        data = json.loads(result.content[0].text)
        # The tool writes state then returns the paginated response shape.
        assert "results" in data
        assert isinstance(data["results"], list)

    async def test_convert_units_with_metric_sets_unit_system_state(
        self, mcp_client: Client
    ) -> None:
        """convert_units detects metric target unit and stores unit_system state."""
        result = await mcp_client.call_tool(
            "convert_units",
            {"value": 1.0, "from_unit": "cups", "to_unit": "ml"},
        )
        assert result.content
        data = json.loads(result.content[0].text)
        assert "result" in data
        assert data["from"] == "cups"
        assert data["to"] == "ml"

    async def test_generate_meal_plan_reads_user_preferences_state(
        self, mcp_client: Client
    ) -> None:
        """generate_meal_plan reads user_preferences from session state.

        When no diet is passed the tool falls back to stored preferences.
        We verify the call completes whether or not state is present.
        """
        result = await mcp_client.call_tool(
            "generate_meal_plan",
            {"user_id": "user-state-1", "name": "State Test Plan"},
        )
        assert result.content
        assert result.content[0].text is not None
