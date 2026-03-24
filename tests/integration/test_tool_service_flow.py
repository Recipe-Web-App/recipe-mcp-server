"""Integration tests: tool -> service -> mocked API client flow."""

from __future__ import annotations

import json

import pytest
from fastmcp import Client


@pytest.mark.integration
class TestRecipeToolServiceFlow:
    """Recipe tools call services which call mocked external APIs."""

    async def test_search_recipes_returns_mealdb_results(self, mcp_client: Client) -> None:
        """search_recipes returns results from the mocked TheMealDB API."""
        result = await mcp_client.call_tool("search_recipes", {"query": "teriyaki", "limit": 5})
        text = result.content[0].text
        data = json.loads(text)
        assert isinstance(data, dict)
        recipes = data["results"]
        assert len(recipes) > 0
        assert any("Teriyaki" in r["title"] for r in recipes)


@pytest.mark.integration
class TestNutritionToolServiceFlow:
    """Nutrition tools call services which call mocked USDA API."""

    async def test_lookup_nutrition_returns_usda_data(self, mcp_client: Client) -> None:
        """lookup_nutrition returns parsed nutrition data from the mocked USDA API."""
        result = await mcp_client.call_tool("lookup_nutrition", {"food_name": "chicken breast"})
        text = result.content[0].text
        data = json.loads(text)
        assert "calories" in data
        assert data["calories"] > 0


@pytest.mark.integration
class TestFavoritesFlow:
    """Create a recipe, save as favorite, list favorites — full roundtrip."""

    async def test_create_save_and_list_favorites(self, mcp_client: Client) -> None:
        """Create a recipe, favorite it, then verify it appears in favorites list."""
        create_result = await mcp_client.call_tool(
            "create_recipe", {"title": "Integration Test Stew"}
        )
        recipe_id = json.loads(create_result.content[0].text)["id"]

        await mcp_client.call_tool(
            "save_favorite",
            {"user_id": "test-user-1", "recipe_id": recipe_id, "rating": 5},
        )

        list_result = await mcp_client.call_tool("list_favorites", {"user_id": "test-user-1"})
        favorites = json.loads(list_result.content[0].text)
        assert isinstance(favorites, list)
        assert len(favorites) == 1
        assert favorites[0]["recipe_id"] == recipe_id
