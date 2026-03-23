"""End-to-end tests for the MCP sampling flow (ctx.sample() round-trip)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from fastmcp import Client, FastMCP
from mcp.types import CreateMessageRequestParams, SamplingMessage


@pytest.mark.e2e
class TestSamplingFlow:
    """Verify that get_recipe(include_variations=True) triggers the sampling handler."""

    async def _create_recipe(self, client: Client, title: str) -> str:
        """Helper: create a recipe and return its ID."""
        result = await client.call_tool("create_recipe", {"title": title})
        return json.loads(result.content[0].text)["id"]

    async def test_sampling_handler_is_called(self, _test_env: None, mcp_server: FastMCP) -> None:
        """get_recipe with include_variations=True triggers the sampling callback."""
        sampling_called = False

        async def sampling_handler(
            messages: list[SamplingMessage],
            params: CreateMessageRequestParams,
            context: Any,
        ) -> str:
            nonlocal sampling_called
            sampling_called = True
            return "1. Fusion: Thai Pasta\n2. Seasonal: Spring\n3. Simple: Quick"

        async with respx.mock:
            respx.route().mock(return_value=httpx.Response(200, json={}))
            client = Client(transport=mcp_server, sampling_handler=sampling_handler)
            async with client:
                recipe_id = await self._create_recipe(client, "Spaghetti Bolognese")
                result = await client.call_tool(
                    "get_recipe",
                    {"recipe_id": recipe_id, "include_variations": True},
                )
                data = json.loads(result.content[0].text)

                assert sampling_called
                assert "variations" in data

    async def test_sampling_prompt_contains_recipe_title(
        self, _test_env: None, mcp_server: FastMCP
    ) -> None:
        """The sampling prompt sent to the handler includes the recipe title."""
        captured_prompt = ""

        async def sampling_handler(
            messages: list[SamplingMessage],
            params: CreateMessageRequestParams,
            context: Any,
        ) -> str:
            nonlocal captured_prompt
            for msg in messages:
                if hasattr(msg.content, "text"):
                    captured_prompt = msg.content.text
            return "Variations here"

        async with respx.mock:
            respx.route().mock(return_value=httpx.Response(200, json={}))
            client = Client(transport=mcp_server, sampling_handler=sampling_handler)
            async with client:
                recipe_id = await self._create_recipe(client, "Chicken Tikka Masala")
                await client.call_tool(
                    "get_recipe",
                    {"recipe_id": recipe_id, "include_variations": True},
                )
                assert "Chicken Tikka Masala" in captured_prompt

    async def test_sampling_max_tokens(self, _test_env: None, mcp_server: FastMCP) -> None:
        """The sampling request passes max_tokens=1024 (MAX_TOKENS_VARIATIONS)."""
        captured_max_tokens: int | None = None

        async def sampling_handler(
            messages: list[SamplingMessage],
            params: CreateMessageRequestParams,
            context: Any,
        ) -> str:
            nonlocal captured_max_tokens
            captured_max_tokens = params.maxTokens
            return "response"

        async with respx.mock:
            respx.route().mock(return_value=httpx.Response(200, json={}))
            client = Client(transport=mcp_server, sampling_handler=sampling_handler)
            async with client:
                recipe_id = await self._create_recipe(client, "Test Recipe")
                await client.call_tool(
                    "get_recipe",
                    {"recipe_id": recipe_id, "include_variations": True},
                )
                assert captured_max_tokens == 1024
