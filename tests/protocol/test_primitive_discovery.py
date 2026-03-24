"""Verify all registered primitives appear in MCP list responses."""

from __future__ import annotations

import pytest
from fastmcp import Client

EXPECTED_TOOLS = {
    "search_recipes",
    "get_recipe",
    "create_recipe",
    "update_recipe",
    "delete_recipe",
    "scale_recipe",
    "get_substitutes",
    "save_favorite",
    "get_random_recipe",
    "list_favorites",
    "lookup_nutrition",
    "analyze_recipe_nutrition",
    "generate_meal_plan",
    "generate_shopping_list",
    "convert_units",
    "get_wine_pairing",
    "get_holiday_recipes",
    "nutrition_lookup_food_nutrition",
    "nutrition_analyze_food_nutrition",
}

EXPECTED_STATIC_RESOURCE_URIS = {
    "recipe://catalog",
    "recipe://categories",
    "recipe://cuisines",
    "recipe://ingredients",
}

EXPECTED_RESOURCE_TEMPLATES = {
    "recipe://recipe/{recipe_id}",
    "nutrition://{food_name}",
    "mealplan://{plan_id}",
    "recipe://favorites/{user_id}",
    "recipe://card/{recipe_id}",
    "nutrition://label/{food_name}",
    "recipe://photo/{recipe_id}",
    "nutrition://chart/{food_name}",
    "nutrition://nutrition/composed/{food_name}",
}

EXPECTED_PROMPTS = {
    "generate_recipe",
    "leftover_recipe",
    "quick_meal",
    "adapt_for_diet",
    "ingredient_spotlight",
    "weekly_meal_plan",
    "holiday_menu",
    "cooking_instructions",
}


@pytest.mark.e2e
class TestToolDiscovery:
    """All 16 tools are discoverable via list_tools."""

    async def test_all_tools_registered(self, mcp_client: Client) -> None:
        tools = await mcp_client.list_tools()
        names = {t.name for t in tools}
        assert names == EXPECTED_TOOLS

    async def test_tool_count(self, mcp_client: Client) -> None:
        tools = await mcp_client.list_tools()
        assert len(tools) == len(EXPECTED_TOOLS)

    @pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS))
    async def test_tool_has_input_schema(self, mcp_client: Client, tool_name: str) -> None:
        tools = await mcp_client.list_tools()
        tool = next(t for t in tools if t.name == tool_name)
        assert tool.inputSchema is not None
        assert "properties" in tool.inputSchema


@pytest.mark.e2e
class TestResourceDiscovery:
    """All static resources and resource templates are discoverable."""

    async def test_all_static_resources_registered(self, mcp_client: Client) -> None:
        resources = await mcp_client.list_resources()
        uris = {str(r.uri) for r in resources}
        assert EXPECTED_STATIC_RESOURCE_URIS.issubset(uris)

    async def test_all_resource_templates_registered(self, mcp_client: Client) -> None:
        templates = await mcp_client.list_resource_templates()
        template_uris = {t.uriTemplate for t in templates}
        assert template_uris == EXPECTED_RESOURCE_TEMPLATES


@pytest.mark.e2e
class TestPromptDiscovery:
    """All 8 prompts are discoverable via list_prompts."""

    async def test_all_prompts_registered(self, mcp_client: Client) -> None:
        prompts = await mcp_client.list_prompts()
        names = {p.name for p in prompts}
        assert names == EXPECTED_PROMPTS

    async def test_prompt_count(self, mcp_client: Client) -> None:
        prompts = await mcp_client.list_prompts()
        assert len(prompts) == len(EXPECTED_PROMPTS)

    @pytest.mark.parametrize("prompt_name", sorted(EXPECTED_PROMPTS))
    async def test_prompt_has_arguments(self, mcp_client: Client, prompt_name: str) -> None:
        prompts = await mcp_client.list_prompts()
        prompt = next(p for p in prompts if p.name == prompt_name)
        assert prompt.arguments is not None
        assert len(prompt.arguments) > 0
