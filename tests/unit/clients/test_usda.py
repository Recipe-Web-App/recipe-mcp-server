"""Tests for USDAClient."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from recipe_mcp_server.clients.usda import USDA_NUTRIENT_MAP, USDAClient
from recipe_mcp_server.models.nutrition import NutrientInfo

BASE_URL = "https://api.nal.usda.gov/fdc/v1"
API_KEY = "test-usda-key"

FOOD_NUTRIENTS: list[dict[str, Any]] = [
    {"nutrientId": 1008, "nutrientName": "Energy", "value": 120},
    {"nutrientId": 1003, "nutrientName": "Protein", "value": 22.5},
    {"nutrientId": 1004, "nutrientName": "Total lipid (fat)", "value": 2.62},
    {"nutrientId": 1005, "nutrientName": "Carbohydrate", "value": 0},
    {"nutrientId": 1079, "nutrientName": "Fiber", "value": 0},
    {"nutrientId": 2000, "nutrientName": "Sugars", "value": 0},
    {"nutrientId": 1093, "nutrientName": "Sodium", "value": 74},
]

FOOD_FIXTURE: dict[str, Any] = {
    "fdcId": 534358,
    "description": "Chicken breast, raw",
    "dataType": "SR Legacy",
    "foodNutrients": FOOD_NUTRIENTS,
}


@pytest.fixture
def client() -> USDAClient:
    http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
    return USDAClient(api_key=API_KEY, http_client=http)


@respx.mock
async def test_search_foods_returns_items(client: USDAClient) -> None:
    respx.get(f"{BASE_URL}/foods/search").mock(
        return_value=httpx.Response(200, json={"totalHits": 1, "foods": [FOOD_FIXTURE]})
    )
    items = await client.search_foods("chicken")
    assert len(items) == 1
    assert items[0].food_name == "Chicken breast, raw"
    assert items[0].fdc_id == "534358"
    assert items[0].source == "usda"
    assert items[0].nutrients.calories == 120
    assert items[0].nutrients.protein_g == 22.5


@respx.mock
async def test_search_foods_empty(client: USDAClient) -> None:
    respx.get(f"{BASE_URL}/foods/search").mock(
        return_value=httpx.Response(200, json={"totalHits": 0, "foods": []})
    )
    items = await client.search_foods("nonexistent")
    assert items == []


@respx.mock
async def test_get_food_returns_item(client: USDAClient) -> None:
    respx.get(f"{BASE_URL}/food/534358").mock(return_value=httpx.Response(200, json=FOOD_FIXTURE))
    item = await client.get_food("534358")
    assert item is not None
    assert item.food_name == "Chicken breast, raw"
    assert item.nutrients.calories == 120
    assert item.nutrients.protein_g == 22.5
    assert item.nutrients.fat_g == 2.62
    assert item.nutrients.sodium_mg == 74


@respx.mock
async def test_get_food_not_found(client: USDAClient) -> None:
    respx.get(f"{BASE_URL}/food/999999").mock(return_value=httpx.Response(200, json={}))
    item = await client.get_food("999999")
    assert item is None


@respx.mock
async def test_get_nutrients(client: USDAClient) -> None:
    respx.get(f"{BASE_URL}/food/534358").mock(return_value=httpx.Response(200, json=FOOD_FIXTURE))
    nutrients = await client.get_nutrients("534358")
    assert isinstance(nutrients, NutrientInfo)
    assert nutrients.calories == 120
    assert nutrients.protein_g == 22.5


@respx.mock
async def test_get_nutrients_not_found(client: USDAClient) -> None:
    respx.get(f"{BASE_URL}/food/999999").mock(return_value=httpx.Response(200, json={}))
    nutrients = await client.get_nutrients("999999")
    assert nutrients.calories == 0.0


def test_extract_nutrients() -> None:
    nutrients = USDAClient._extract_nutrients(FOOD_NUTRIENTS)
    assert nutrients.calories == 120
    assert nutrients.protein_g == 22.5
    assert nutrients.fat_g == 2.62
    assert nutrients.carbs_g == 0
    assert nutrients.sodium_mg == 74
    assert nutrients.full_nutrients is not None
    assert "Energy" in nutrients.full_nutrients


def test_nutrient_map_coverage() -> None:
    expected_fields = {
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
        "fiber_g",
        "sugar_g",
        "sodium_mg",
    }
    assert set(USDA_NUTRIENT_MAP.values()) == expected_fields


@respx.mock
async def test_search_foods_cache_hit() -> None:
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=json.dumps([FOOD_FIXTURE]))
    http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
    client = USDAClient(api_key=API_KEY, http_client=http, redis_client=redis_mock)

    items = await client.search_foods("chicken")
    assert len(items) == 1
    assert items[0].food_name == "Chicken breast, raw"
    redis_mock.get.assert_called_once()


@respx.mock
async def test_api_key_sent_in_params(client: USDAClient) -> None:
    route = respx.get(f"{BASE_URL}/foods/search").mock(
        return_value=httpx.Response(200, json={"totalHits": 0, "foods": []})
    )
    await client.search_foods("test")
    assert route.call_count == 1
    request = route.calls[0].request
    assert f"api_key={API_KEY}" in str(request.url)
