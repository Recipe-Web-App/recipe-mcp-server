"""Tests for DummyJSONClient."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from recipe_mcp_server.clients.dummyjson import DummyJSONClient
from recipe_mcp_server.models.common import APISource, Difficulty

BASE_URL = "https://dummyjson.com"

RECIPE_FIXTURE: dict[str, Any] = {
    "id": 1,
    "name": "Classic Margherita Pizza",
    "ingredients": ["Pizza dough", "Tomato sauce", "Fresh mozzarella"],
    "instructions": [
        "Preheat oven to 475F",
        "Roll out pizza dough",
        "Add toppings and bake",
    ],
    "prepTimeMinutes": 20,
    "cookTimeMinutes": 15,
    "servings": 4,
    "difficulty": "Easy",
    "cuisine": "Italian",
    "caloriesPerServing": 300,
    "tags": ["Pizza", "Italian"],
    "image": "https://cdn.dummyjson.com/recipe-images/1.webp",
    "rating": 4.6,
    "reviewCount": 98,
    "mealType": ["Dinner"],
}


@pytest.fixture
def client() -> DummyJSONClient:
    http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
    return DummyJSONClient(http_client=http)


@respx.mock
async def test_list_recipes(client: DummyJSONClient) -> None:
    respx.get(f"{BASE_URL}/recipes").mock(
        return_value=httpx.Response(
            200,
            json={"recipes": [RECIPE_FIXTURE], "total": 1},
        )
    )
    recipes = await client.list_recipes()
    assert len(recipes) == 1
    assert recipes[0].title == "Classic Margherita Pizza"
    assert recipes[0].source_api == APISource.DUMMYJSON
    assert recipes[0].source_id == "1"


@respx.mock
async def test_list_recipes_empty(client: DummyJSONClient) -> None:
    respx.get(f"{BASE_URL}/recipes").mock(
        return_value=httpx.Response(200, json={"recipes": [], "total": 0})
    )
    recipes = await client.list_recipes()
    assert recipes == []


@respx.mock
async def test_get_recipe(client: DummyJSONClient) -> None:
    respx.get(f"{BASE_URL}/recipes/1").mock(return_value=httpx.Response(200, json=RECIPE_FIXTURE))
    recipe = await client.get_recipe(1)
    assert recipe is not None
    assert recipe.title == "Classic Margherita Pizza"
    assert recipe.area == "Italian"


@respx.mock
async def test_get_recipe_not_found(
    client: DummyJSONClient,
) -> None:
    respx.get(f"{BASE_URL}/recipes/999").mock(return_value=httpx.Response(200, json={}))
    recipe = await client.get_recipe(999)
    assert recipe is None


@respx.mock
async def test_search_recipes(client: DummyJSONClient) -> None:
    respx.get(f"{BASE_URL}/recipes/search").mock(
        return_value=httpx.Response(
            200,
            json={"recipes": [RECIPE_FIXTURE], "total": 1},
        )
    )
    recipes = await client.search_recipes("pizza")
    assert len(recipes) == 1
    assert recipes[0].title == "Classic Margherita Pizza"


@respx.mock
async def test_list_tags(client: DummyJSONClient) -> None:
    tags = ["Pizza", "Italian", "Vegetarian"]
    respx.get(f"{BASE_URL}/recipes/tags").mock(return_value=httpx.Response(200, json=tags))
    result = await client.list_tags()
    assert result == tags


@respx.mock
async def test_get_by_tag(client: DummyJSONClient) -> None:
    respx.get(f"{BASE_URL}/recipes/tag/Pizza").mock(
        return_value=httpx.Response(
            200,
            json={"recipes": [RECIPE_FIXTURE], "total": 1},
        )
    )
    recipes = await client.get_by_tag("Pizza")
    assert len(recipes) == 1


@respx.mock
async def test_get_by_meal_type(client: DummyJSONClient) -> None:
    respx.get(f"{BASE_URL}/recipes/meal-type/Dinner").mock(
        return_value=httpx.Response(
            200,
            json={"recipes": [RECIPE_FIXTURE], "total": 1},
        )
    )
    recipes = await client.get_by_meal_type("Dinner")
    assert len(recipes) == 1


def test_recipe_mapping_difficulty() -> None:
    recipe = DummyJSONClient._dummyjson_to_recipe(RECIPE_FIXTURE)
    assert recipe.difficulty == Difficulty.EASY


def test_recipe_mapping_tags_merged() -> None:
    recipe = DummyJSONClient._dummyjson_to_recipe(RECIPE_FIXTURE)
    assert "Pizza" in recipe.tags
    assert "Italian" in recipe.tags
    assert "Dinner" in recipe.tags


def test_recipe_mapping_ingredients() -> None:
    recipe = DummyJSONClient._dummyjson_to_recipe(RECIPE_FIXTURE)
    assert len(recipe.ingredients) == 3
    assert recipe.ingredients[0].name == "Pizza dough"
    assert recipe.ingredients[0].order_index == 0


@respx.mock
async def test_cache_integration() -> None:
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=json.dumps([RECIPE_FIXTURE]))
    http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
    client = DummyJSONClient(http_client=http, redis_client=redis_mock)

    recipes = await client.list_recipes()
    assert len(recipes) == 1
    assert recipes[0].title == "Classic Margherita Pizza"
    redis_mock.get.assert_called_once()
