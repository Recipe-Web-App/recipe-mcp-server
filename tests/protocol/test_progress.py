"""Test that tools with progress reporting complete successfully.

search_recipes, analyze_recipe_nutrition, and generate_meal_plan all call
ctx.report_progress internally.  The in-process FastMCP transport forwards
progress notifications to the client transparently, so we verify each tool
returns a well-formed response.
"""

from __future__ import annotations

import json

import pytest
from fastmcp import Client


@pytest.mark.e2e
class TestProgressReporting:
    """Tools that emit progress notifications still complete successfully."""

    async def test_search_recipes_returns_results(self, mcp_client: Client) -> None:
        """search_recipes reports progress and returns a paginated results object."""
        result = await mcp_client.call_tool("search_recipes", {"query": "chicken"})
        assert result.content
        data = json.loads(result.content[0].text)
        assert "results" in data
        assert isinstance(data["results"], list)

    async def test_analyze_recipe_nutrition_with_existing_recipe(self, mcp_client: Client) -> None:
        """analyze_recipe_nutrition reports progress; create a recipe first so the
        service has a record to analyze against the mocked API."""
        create_result = await mcp_client.call_tool(
            "create_recipe", {"title": "Progress Test Recipe", "servings": 2}
        )
        recipe_id = json.loads(create_result.content[0].text)["id"]

        result = await mcp_client.call_tool("analyze_recipe_nutrition", {"recipe_id": recipe_id})
        assert result.content
        assert result.content[0].text is not None

    async def test_generate_meal_plan_returns_plan(self, mcp_client: Client) -> None:
        """generate_meal_plan reports progress and returns a meal plan payload."""
        result = await mcp_client.call_tool(
            "generate_meal_plan",
            {"user_id": "user-progress-1", "name": "Progress Week"},
        )
        assert result.content
        assert result.content[0].text is not None
