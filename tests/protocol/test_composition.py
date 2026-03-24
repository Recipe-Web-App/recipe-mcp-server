"""Test that the mounted nutrition sub-server tools and resources are accessible.

The nutrition sub-server is mounted under the 'nutrition' namespace, which
prefixes its tool names (nutrition_lookup_food_nutrition,
nutrition_analyze_food_nutrition) and exposes the composed resource template
nutrition://nutrition/composed/{food_name}.
"""

from __future__ import annotations

import json

import pytest
from fastmcp import Client

NUTRITION_TOOLS = {
    "nutrition_lookup_food_nutrition",
    "nutrition_analyze_food_nutrition",
}

COMPOSED_RESOURCE_TEMPLATE = "nutrition://nutrition/composed/{food_name}"


@pytest.mark.e2e
class TestComposition:
    """Mounted sub-server tools and resources are accessible from the parent server."""

    async def test_nutrition_tools_in_tool_list(self, mcp_client: Client) -> None:
        """Both nutrition namespace tools appear in list_tools."""
        tools = await mcp_client.list_tools()
        names = {t.name for t in tools}
        assert NUTRITION_TOOLS.issubset(names)

    async def test_composed_resource_template_registered(self, mcp_client: Client) -> None:
        """The composed resource template is discoverable via list_resource_templates."""
        templates = await mcp_client.list_resource_templates()
        uris = {t.uriTemplate for t in templates}
        assert COMPOSED_RESOURCE_TEMPLATE in uris

    async def test_nutrition_lookup_food_nutrition_completes(self, mcp_client: Client) -> None:
        """nutrition_lookup_food_nutrition routes through the sub-server and completes."""
        result = await mcp_client.call_tool(
            "nutrition_lookup_food_nutrition", {"food_name": "broccoli"}
        )
        assert result.content
        assert result.content[0].text is not None

    async def test_nutrition_analyze_food_nutrition_with_recipe(self, mcp_client: Client) -> None:
        """nutrition_analyze_food_nutrition uses the parent lifespan context to
        analyze a recipe created in the same test session."""
        create_result = await mcp_client.call_tool(
            "create_recipe", {"title": "Composition Test Dish", "servings": 4}
        )
        recipe_id = json.loads(create_result.content[0].text)["id"]

        result = await mcp_client.call_tool(
            "nutrition_analyze_food_nutrition", {"recipe_id": recipe_id}
        )
        assert result.content
        assert result.content[0].text is not None
