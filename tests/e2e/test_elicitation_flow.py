"""End-to-end tests for the MCP elicitation flow (ctx.elicit() round-trip)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from fastmcp import Client, Context, FastMCP
from fastmcp.client.elicitation import ElicitResult


def _register_elicitation_test_tools(server: FastMCP) -> None:
    """Register transient tools that trigger each elicitation handler."""

    @server.tool()
    async def test_dietary_elicitation(ctx: Context) -> str:
        """Test tool that triggers gather_dietary_preferences."""
        from recipe_mcp_server.elicitation.handlers import gather_dietary_preferences

        profile = await gather_dietary_preferences(ctx)
        if profile is None:
            return "declined"
        return profile.model_dump_json()

    @server.tool()
    async def test_serving_elicitation(ctx: Context, servings: int) -> str:
        """Test tool that triggers confirm_serving_size."""
        from recipe_mcp_server.elicitation.handlers import confirm_serving_size

        result = await confirm_serving_size(ctx, servings)
        if result is None:
            return "declined"
        return str(result)

    @server.tool()
    async def test_ingredients_elicitation(ctx: Context) -> str:
        """Test tool that triggers clarify_available_ingredients."""
        from recipe_mcp_server.elicitation.handlers import clarify_available_ingredients

        form = await clarify_available_ingredients(ctx)
        if form is None:
            return "declined"
        return form.model_dump_json()


@pytest.mark.e2e
class TestElicitationFlow:
    """Verify elicitation handlers work end-to-end through the MCP protocol."""

    async def test_dietary_preferences_accepted(self, _test_env: None, mcp_server: FastMCP) -> None:
        """Accepting dietary preference elicitation returns a DietaryProfile."""
        _register_elicitation_test_tools(mcp_server)

        async def elicitation_handler(
            message: str,
            schema: type[Any] | None,
            params: Any,
            context: Any,
        ) -> ElicitResult:
            return ElicitResult(
                action="accept",
                content={
                    "restrictions": "vegan, gluten-free",
                    "allergies": "peanuts",
                    "preferred_cuisines": "Italian, Thai",
                    "calorie_target": 2000,
                },
            )

        async with respx.mock:
            respx.route().mock(return_value=httpx.Response(200, json={}))
            client = Client(
                transport=mcp_server,
                elicitation_handler=elicitation_handler,
            )
            async with client:
                result = await client.call_tool("test_dietary_elicitation", {})
                data = json.loads(result.content[0].text)
                assert "vegan" in data["dietary_restrictions"]
                assert "gluten-free" in data["dietary_restrictions"]
                assert "peanuts" in data["allergies"]
                assert data["calorie_target"] == 2000

    async def test_serving_size_declined(self, _test_env: None, mcp_server: FastMCP) -> None:
        """Declining serving size elicitation returns None (our tool returns 'declined')."""
        _register_elicitation_test_tools(mcp_server)

        async def elicitation_handler(
            message: str,
            schema: type[Any] | None,
            params: Any,
            context: Any,
        ) -> ElicitResult:
            return ElicitResult(action="decline")

        async with respx.mock:
            respx.route().mock(return_value=httpx.Response(200, json={}))
            client = Client(
                transport=mcp_server,
                elicitation_handler=elicitation_handler,
            )
            async with client:
                result = await client.call_tool("test_serving_elicitation", {"servings": 100})
                assert result.content[0].text == "declined"

    async def test_serving_size_accepted(self, _test_env: None, mcp_server: FastMCP) -> None:
        """Accepting serving size returns the confirmed number."""
        _register_elicitation_test_tools(mcp_server)

        async def elicitation_handler(
            message: str,
            schema: type[Any] | None,
            params: Any,
            context: Any,
        ) -> ElicitResult:
            return ElicitResult(
                action="accept",
                content={
                    "confirmed_servings": 50,
                    "reason": "party",
                },
            )

        async with respx.mock:
            respx.route().mock(return_value=httpx.Response(200, json={}))
            client = Client(
                transport=mcp_server,
                elicitation_handler=elicitation_handler,
            )
            async with client:
                result = await client.call_tool("test_serving_elicitation", {"servings": 50})
                assert result.content[0].text == "50"

    async def test_ingredients_elicitation_accepted(
        self, _test_env: None, mcp_server: FastMCP
    ) -> None:
        """Accepting ingredients elicitation returns the form data."""
        _register_elicitation_test_tools(mcp_server)

        async def elicitation_handler(
            message: str,
            schema: type[Any] | None,
            params: Any,
            context: Any,
        ) -> ElicitResult:
            return ElicitResult(
                action="accept",
                content={
                    "ingredients": "chicken, rice, garlic",
                    "pantry_staples_available": True,
                    "cooking_equipment": "oven, stovetop",
                },
            )

        async with respx.mock:
            respx.route().mock(return_value=httpx.Response(200, json={}))
            client = Client(
                transport=mcp_server,
                elicitation_handler=elicitation_handler,
            )
            async with client:
                result = await client.call_tool("test_ingredients_elicitation", {})
                data = json.loads(result.content[0].text)
                assert data["ingredients"] == "chicken, rice, garlic"
                assert data["pantry_staples_available"] is True
