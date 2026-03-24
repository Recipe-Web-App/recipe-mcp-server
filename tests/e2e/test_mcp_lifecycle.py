"""End-to-end MCP lifecycle tests: initialize -> discover -> call -> close."""

from __future__ import annotations

import json

import pytest
from fastmcp import Client


@pytest.mark.e2e
class TestToolLifecycle:
    """Full lifecycle through tool discovery and invocation."""

    async def test_create_and_get_recipe(self, mcp_client: Client) -> None:
        """Create a recipe via call_tool, then retrieve it and verify fields."""
        tools = await mcp_client.list_tools()
        tool_names = {t.name for t in tools}
        assert "create_recipe" in tool_names
        assert "get_recipe" in tool_names

        create_result = await mcp_client.call_tool(
            "create_recipe", {"title": "Test Pasta", "servings": 2}
        )
        recipe_data = json.loads(create_result.content[0].text)
        recipe_id = recipe_data["id"]
        assert recipe_id is not None

        get_result = await mcp_client.call_tool("get_recipe", {"recipe_id": recipe_id})
        retrieved = json.loads(get_result.content[0].text)
        assert retrieved["title"] == "Test Pasta"
        assert retrieved["servings"] == 2

    async def test_get_nonexistent_recipe_returns_error(self, mcp_client: Client) -> None:
        """Calling get_recipe with a missing ID returns an error message, not an exception."""
        result = await mcp_client.call_tool("get_recipe", {"recipe_id": "nonexistent-id-12345"})
        text = result.content[0].text
        assert "error" in text.lower()

    async def test_create_and_delete_recipe(self, mcp_client: Client) -> None:
        """Create then soft-delete a recipe."""
        create_result = await mcp_client.call_tool("create_recipe", {"title": "Ephemeral Dish"})
        recipe_id = json.loads(create_result.content[0].text)["id"]

        delete_result = await mcp_client.call_tool("delete_recipe", {"recipe_id": recipe_id})
        delete_data = json.loads(delete_result.content[0].text)
        assert delete_data["deleted"] is True
        assert delete_data["recipe_id"] == recipe_id


@pytest.mark.e2e
class TestResourceLifecycle:
    """List and read resources through the MCP protocol."""

    async def test_read_catalog_resource(self, mcp_client: Client) -> None:
        """Read the recipe://catalog static resource without error."""
        resources = await mcp_client.list_resources()
        catalog_uris = [str(r.uri) for r in resources if "catalog" in str(r.uri)]
        assert len(catalog_uris) > 0

        content = await mcp_client.read_resource("recipe://catalog")
        assert content is not None


@pytest.mark.e2e
class TestPromptLifecycle:
    """Get prompt messages through the MCP protocol."""

    async def test_get_generate_recipe_prompt(self, mcp_client: Client) -> None:
        """Retrieve the generate_recipe prompt with arguments."""
        prompts = await mcp_client.list_prompts()
        assert any(p.name == "generate_recipe" for p in prompts)

        result = await mcp_client.get_prompt("generate_recipe", {"cuisine": "Italian"})
        assert result is not None
        assert len(result.messages) >= 2
