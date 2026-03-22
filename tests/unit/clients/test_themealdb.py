"""Tests for TheMealDBClient."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from recipe_mcp_server.clients.themealdb import TheMealDBClient
from recipe_mcp_server.exceptions import ServiceUnavailableError
from recipe_mcp_server.models.common import APISource

BASE_URL = "https://www.themealdb.com/api/json/v1/1"

MEAL_FIXTURE: dict[str, Any] = {
    "idMeal": "52772",
    "strMeal": "Teriyaki Chicken Casserole",
    "strCategory": "Chicken",
    "strArea": "Japanese",
    "strInstructions": "Preheat oven to 350.\nCombine soy sauce.",
    "strMealThumb": "https://example.com/img.jpg",
    "strTags": "Meat,Casserole",
    "strSource": "https://example.com/recipe",
    "strIngredient1": "soy sauce",
    "strIngredient2": "water",
    "strIngredient3": "",
    "strMeasure1": "3/4 cup",
    "strMeasure2": "1/2 cup",
    "strMeasure3": "",
}


@pytest.fixture
def client() -> TheMealDBClient:
    http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
    return TheMealDBClient(http_client=http)


@respx.mock
async def test_search_by_name_returns_recipes(
    client: TheMealDBClient,
) -> None:
    respx.get(f"{BASE_URL}/search.php").mock(
        return_value=httpx.Response(200, json={"meals": [MEAL_FIXTURE]})
    )
    recipes = await client.search_by_name("chicken")
    assert len(recipes) == 1
    assert recipes[0].title == "Teriyaki Chicken Casserole"
    assert recipes[0].source_api == APISource.THEMEALDB
    assert recipes[0].source_id == "52772"
    assert recipes[0].category == "Chicken"
    assert recipes[0].area == "Japanese"


@respx.mock
async def test_search_by_name_empty(client: TheMealDBClient) -> None:
    respx.get(f"{BASE_URL}/search.php").mock(return_value=httpx.Response(200, json={"meals": None}))
    recipes = await client.search_by_name("nonexistent")
    assert recipes == []


@respx.mock
async def test_lookup_by_id_returns_recipe(
    client: TheMealDBClient,
) -> None:
    respx.get(f"{BASE_URL}/lookup.php").mock(
        return_value=httpx.Response(200, json={"meals": [MEAL_FIXTURE]})
    )
    recipe = await client.lookup_by_id("52772")
    assert recipe is not None
    assert recipe.title == "Teriyaki Chicken Casserole"
    assert recipe.source_id == "52772"


@respx.mock
async def test_lookup_by_id_not_found(client: TheMealDBClient) -> None:
    respx.get(f"{BASE_URL}/lookup.php").mock(return_value=httpx.Response(200, json={"meals": None}))
    recipe = await client.lookup_by_id("99999")
    assert recipe is None


@respx.mock
async def test_random_meal(client: TheMealDBClient) -> None:
    respx.get(f"{BASE_URL}/random.php").mock(
        return_value=httpx.Response(200, json={"meals": [MEAL_FIXTURE]})
    )
    recipe = await client.random_meal()
    assert recipe is not None
    assert recipe.title == "Teriyaki Chicken Casserole"


@respx.mock
async def test_list_categories(client: TheMealDBClient) -> None:
    categories = [
        {"idCategory": "1", "strCategory": "Beef"},
        {"idCategory": "2", "strCategory": "Chicken"},
    ]
    respx.get(f"{BASE_URL}/categories.php").mock(
        return_value=httpx.Response(200, json={"categories": categories})
    )
    result = await client.list_categories()
    assert len(result) == 2
    assert result[0]["strCategory"] == "Beef"


@respx.mock
async def test_list_areas(client: TheMealDBClient) -> None:
    respx.get(f"{BASE_URL}/list.php").mock(
        return_value=httpx.Response(
            200,
            json={
                "meals": [
                    {"strArea": "American"},
                    {"strArea": "Japanese"},
                ]
            },
        )
    )
    areas = await client.list_areas()
    assert areas == ["American", "Japanese"]


@respx.mock
async def test_filter_by_category(client: TheMealDBClient) -> None:
    respx.get(f"{BASE_URL}/filter.php").mock(
        return_value=httpx.Response(
            200,
            json={
                "meals": [
                    {
                        "idMeal": "52772",
                        "strMeal": "Teriyaki Chicken",
                        "strMealThumb": "https://example.com/t.jpg",
                    },
                ]
            },
        )
    )
    summaries = await client.filter_by_category("Chicken")
    assert len(summaries) == 1
    assert summaries[0].title == "Teriyaki Chicken"
    assert summaries[0].source_api == APISource.THEMEALDB


def test_parse_ingredients() -> None:
    meal: dict[str, Any] = {
        "strIngredient1": "soy sauce",
        "strIngredient2": "water",
        "strIngredient3": "  ",
        "strIngredient4": "",
        "strMeasure1": "3/4 cup",
        "strMeasure2": "",
        "strMeasure3": "",
        "strMeasure4": "",
    }
    ingredients = TheMealDBClient._parse_ingredients(meal)
    assert len(ingredients) == 2
    assert ingredients[0].name == "soy sauce"
    assert ingredients[0].unit == "3/4 cup"
    assert ingredients[1].name == "water"
    assert ingredients[1].unit is None


@respx.mock
async def test_search_by_name_cache_hit() -> None:
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=json.dumps([MEAL_FIXTURE]))
    http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
    client = TheMealDBClient(http_client=http, redis_client=redis_mock)

    recipes = await client.search_by_name("chicken")
    assert len(recipes) == 1
    assert recipes[0].title == "Teriyaki Chicken Casserole"
    redis_mock.get.assert_called_once()


@respx.mock
async def test_error_handling_500(client: TheMealDBClient) -> None:
    respx.get(f"{BASE_URL}/search.php").mock(return_value=httpx.Response(500))
    with pytest.raises(ServiceUnavailableError):
        await client.search_by_name("chicken")
