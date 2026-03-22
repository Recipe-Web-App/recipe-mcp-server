"""Tests for FoodishClient."""

from __future__ import annotations

import httpx
import pytest
import respx

from recipe_mcp_server.clients.foodish import FoodishClient
from recipe_mcp_server.exceptions import ServiceUnavailableError

BASE_URL = "https://foodish-api.com/api"


@pytest.fixture
def client() -> FoodishClient:
    http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
    return FoodishClient(http_client=http)


@respx.mock
async def test_random_image(client: FoodishClient) -> None:
    url = "https://foodish-api.com/images/pizza/pizza42.jpg"
    respx.get(f"{BASE_URL}/").mock(return_value=httpx.Response(200, json={"image": url}))
    result = await client.random_image()
    assert result == url


@respx.mock
async def test_random_image_empty(client: FoodishClient) -> None:
    respx.get(f"{BASE_URL}/").mock(return_value=httpx.Response(200, json={}))
    result = await client.random_image()
    assert result == ""


@respx.mock
async def test_random_image_by_category(
    client: FoodishClient,
) -> None:
    url = "https://foodish-api.com/images/burger/burger15.jpg"
    respx.get(f"{BASE_URL}/images/burger/").mock(
        return_value=httpx.Response(200, json={"image": url})
    )
    result = await client.random_image_by_category("burger")
    assert result == url


@respx.mock
async def test_error_handling_500(client: FoodishClient) -> None:
    respx.get(f"{BASE_URL}/").mock(return_value=httpx.Response(500))
    with pytest.raises(ServiceUnavailableError):
        await client.random_image()
