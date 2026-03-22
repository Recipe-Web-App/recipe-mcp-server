"""Tests for OpenFoodFactsClient."""

from __future__ import annotations

import httpx
import pytest
import respx

from recipe_mcp_server.clients.openfoodfacts import OpenFoodFactsClient

BASE_URL = "https://world.openfoodfacts.org/api/v2"

PRODUCT_RESPONSE = {
    "product": {
        "product_name": "Nutella",
        "brands": "Ferrero",
        "nutriscore_grade": "e",
        "allergens_tags": ["en:milk", "en:nuts", "en:soybeans"],
        "nutriments": {
            "energy-kcal_100g": 539,
            "fat_100g": 30.9,
        },
        "image_url": "https://example.com/nutella.jpg",
    }
}


@pytest.fixture
def client() -> OpenFoodFactsClient:
    http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
    return OpenFoodFactsClient(http_client=http)


@respx.mock
async def test_get_product(client: OpenFoodFactsClient) -> None:
    respx.get(f"{BASE_URL}/product/3017620422003").mock(
        return_value=httpx.Response(200, json=PRODUCT_RESPONSE)
    )
    product = await client.get_product("3017620422003")
    assert product is not None
    assert product["product_name"] == "Nutella"
    assert product["brands"] == "Ferrero"


@respx.mock
async def test_get_product_not_found(
    client: OpenFoodFactsClient,
) -> None:
    respx.get(f"{BASE_URL}/product/0000000000000").mock(
        return_value=httpx.Response(200, json={"status": 0})
    )
    product = await client.get_product("0000000000000")
    assert product is None


@respx.mock
async def test_search_products(
    client: OpenFoodFactsClient,
) -> None:
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "products": [
                    {"product_name": "Nutella", "code": "3017620422003"},
                    {"product_name": "Peanut Butter", "code": "0048001252325"},
                ],
                "count": 2,
            },
        )
    )
    products = await client.search_products("chocolate spread")
    assert len(products) == 2
    assert products[0]["product_name"] == "Nutella"


@respx.mock
async def test_search_products_empty(
    client: OpenFoodFactsClient,
) -> None:
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(200, json={"products": [], "count": 0})
    )
    products = await client.search_products("nonexistent")
    assert products == []


def test_extract_allergens() -> None:
    product = {
        "allergens_tags": ["en:milk", "en:nuts", "en:soybeans"],
    }
    allergens = OpenFoodFactsClient.extract_allergens(product)
    assert allergens == ["milk", "nuts", "soybeans"]


def test_extract_allergens_no_prefix() -> None:
    product = {"allergens_tags": ["milk", "gluten"]}
    allergens = OpenFoodFactsClient.extract_allergens(product)
    assert allergens == ["milk", "gluten"]


def test_extract_allergens_empty() -> None:
    product: dict[str, list[str]] = {"allergens_tags": []}
    allergens = OpenFoodFactsClient.extract_allergens(product)
    assert allergens == []


def test_user_agent_header() -> None:
    client = OpenFoodFactsClient()
    headers = client._default_headers()
    assert "User-Agent" in headers
    assert "RecipeMCPServer" in headers["User-Agent"]
