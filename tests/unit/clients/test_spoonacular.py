"""Tests for SpoonacularClient."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from recipe_mcp_server.clients.spoonacular import SpoonacularClient
from recipe_mcp_server.models.common import APISource, Difficulty
from recipe_mcp_server.models.nutrition import NutrientInfo

BASE_URL = "https://api.spoonacular.com"
API_KEY = "test-spoonacular-key"

RECIPE_INFO: dict[str, Any] = {
    "id": 716429,
    "title": "Pasta with Garlic",
    "image": "https://example.com/pasta.jpg",
    "sourceUrl": "https://example.com/recipe",
    "readyInMinutes": 45,
    "preparationMinutes": 15,
    "cookingMinutes": 30,
    "servings": 2,
    "instructions": "Boil the pasta.\nSaute garlic.",
    "extendedIngredients": [
        {"name": "garlic", "amount": 3.0, "unit": "cloves"},
        {"name": "pasta", "amount": 8.0, "unit": "ounces"},
    ],
    "dishTypes": ["lunch", "main course"],
}


@pytest.fixture
def client() -> SpoonacularClient:
    http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
    return SpoonacularClient(api_key=API_KEY, http_client=http)


@respx.mock
async def test_search_recipes(client: SpoonacularClient) -> None:
    respx.get(f"{BASE_URL}/recipes/complexSearch").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 716429,
                        "title": "Pasta with Garlic",
                        "image": "https://example.com/pasta.jpg",
                    },
                ],
                "totalResults": 1,
            },
        )
    )
    summaries = await client.search_recipes("pasta")
    assert len(summaries) == 1
    assert summaries[0].title == "Pasta with Garlic"
    assert summaries[0].source_api == APISource.SPOONACULAR


@respx.mock
async def test_search_recipes_empty(
    client: SpoonacularClient,
) -> None:
    respx.get(f"{BASE_URL}/recipes/complexSearch").mock(
        return_value=httpx.Response(200, json={"results": [], "totalResults": 0})
    )
    summaries = await client.search_recipes("nonexistent")
    assert summaries == []


@respx.mock
async def test_get_recipe_info(client: SpoonacularClient) -> None:
    respx.get(f"{BASE_URL}/recipes/716429/information").mock(
        return_value=httpx.Response(200, json=RECIPE_INFO)
    )
    recipe = await client.get_recipe_info(716429)
    assert recipe is not None
    assert recipe.title == "Pasta with Garlic"
    assert recipe.source_api == APISource.SPOONACULAR
    assert recipe.source_id == "716429"
    assert recipe.servings == 2
    assert len(recipe.ingredients) == 2
    assert recipe.ingredients[0].name == "garlic"


@respx.mock
async def test_get_recipe_info_not_found(
    client: SpoonacularClient,
) -> None:
    respx.get(f"{BASE_URL}/recipes/999999/information").mock(
        return_value=httpx.Response(200, json={})
    )
    recipe = await client.get_recipe_info(999999)
    assert recipe is None


@respx.mock
async def test_get_similar(client: SpoonacularClient) -> None:
    respx.get(f"{BASE_URL}/recipes/716429/similar").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 715538,
                    "title": "Similar Recipe",
                    "image": "https://example.com/s.jpg",
                },
            ],
        )
    )
    results = await client.get_similar(716429)
    assert len(results) == 1
    assert results[0].title == "Similar Recipe"


@respx.mock
async def test_generate_meal_plan(
    client: SpoonacularClient,
) -> None:
    plan = {
        "meals": [{"id": 1, "title": "Breakfast Bowl"}],
        "nutrients": {"calories": 2000},
    }
    respx.get(f"{BASE_URL}/mealplanner/generate").mock(return_value=httpx.Response(200, json=plan))
    result = await client.generate_meal_plan()
    assert "meals" in result
    assert result["nutrients"]["calories"] == 2000


@respx.mock
async def test_get_wine_pairing(client: SpoonacularClient) -> None:
    pairing = {
        "pairedWines": ["merlot"],
        "pairingText": "Merlot pairs well with steak.",
    }
    respx.get(f"{BASE_URL}/food/wine/pairing").mock(return_value=httpx.Response(200, json=pairing))
    result = await client.get_wine_pairing("steak")
    assert result["pairedWines"] == ["merlot"]


@respx.mock
async def test_get_substitutes(client: SpoonacularClient) -> None:
    respx.get(f"{BASE_URL}/food/ingredients/substitutes").mock(
        return_value=httpx.Response(
            200,
            json={
                "substitutes": ["1 cup yogurt = 1 cup sour cream"],
                "message": "Found 1 substitute",
            },
        )
    )
    subs = await client.get_substitutes("yogurt")
    assert len(subs) == 1
    assert "sour cream" in subs[0]


@respx.mock
async def test_convert_amounts(client: SpoonacularClient) -> None:
    respx.get(f"{BASE_URL}/recipes/convert").mock(
        return_value=httpx.Response(
            200,
            json={
                "sourceAmount": 2.0,
                "sourceUnit": "cups",
                "targetAmount": 473.176,
                "targetUnit": "ml",
            },
        )
    )
    result = await client.convert_amounts("flour", 2.0, "cups", "ml")
    assert result["targetAmount"] == 473.176


@respx.mock
async def test_get_recipe_nutrition(
    client: SpoonacularClient,
) -> None:
    respx.get(f"{BASE_URL}/recipes/716429/nutritionWidget.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "calories": "584",
                "carbs": "50g",
                "fat": "25g",
                "protein": "30g",
            },
        )
    )
    info = await client.get_recipe_nutrition(716429)
    assert isinstance(info, NutrientInfo)
    assert info.calories == 584
    assert info.carbs_g == 50
    assert info.fat_g == 25
    assert info.protein_g == 30


def test_difficulty_mapping_easy() -> None:
    data = {**RECIPE_INFO, "readyInMinutes": 20}
    recipe = SpoonacularClient._spoonacular_to_recipe(data)
    assert recipe.difficulty == Difficulty.EASY


def test_difficulty_mapping_medium() -> None:
    data = {**RECIPE_INFO, "readyInMinutes": 45}
    recipe = SpoonacularClient._spoonacular_to_recipe(data)
    assert recipe.difficulty == Difficulty.MEDIUM


def test_difficulty_mapping_hard() -> None:
    data = {**RECIPE_INFO, "readyInMinutes": 90}
    recipe = SpoonacularClient._spoonacular_to_recipe(data)
    assert recipe.difficulty == Difficulty.HARD
