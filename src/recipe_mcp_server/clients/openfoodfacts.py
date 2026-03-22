"""Open Food Facts API client.

Wraps https://world.openfoodfacts.org/api/v2 with caching, retry,
and circuit-breaker behaviour inherited from :class:`BaseAPIClient`.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from recipe_mcp_server.cache.keys import (
    TTL_PRODUCT,
    TTL_SEARCH,
    product_key,
    search_key,
)
from recipe_mcp_server.clients.base import BaseAPIClient

logger = structlog.get_logger(__name__)


class OpenFoodFactsClient(BaseAPIClient):
    """Client for the Open Food Facts product database."""

    api_name = "OpenFoodFacts"
    base_url = "https://world.openfoodfacts.org/api/v2"

    def _default_headers(self) -> dict[str, str]:
        """User-Agent header is required by Open Food Facts."""
        return {
            "Accept": "application/json",
            "User-Agent": "RecipeMCPServer/1.0 (contact@example.com)",
        }

    # -- Abstract method required by BaseAPIClient ----------------------------

    def _build_cache_key(self, endpoint: str, params: dict[str, Any] | None) -> str:
        """Build a cache key based on the endpoint and query parameters."""
        params = params or {}

        if endpoint.startswith("/product/"):
            barcode = endpoint.rsplit("/", maxsplit=1)[-1]
            return product_key(barcode)
        if endpoint == "/search":
            return search_key(params.get("search_terms", ""))
        return search_key(f"{endpoint}:{json.dumps(params, sort_keys=True)}")

    # -- Public API methods ---------------------------------------------------

    async def get_product(self, barcode: str) -> dict[str, Any] | None:
        """Get a product by its barcode. Returns None if not found."""
        endpoint = f"/product/{barcode}"
        cache_key = self._build_cache_key(endpoint, None)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            return json.loads(cached)

        data = await self._get(endpoint)
        if not isinstance(data, dict) or "product" not in data:
            return None

        product: dict[str, Any] = data["product"]
        await self._cache_set(cache_key, json.dumps(product), TTL_PRODUCT)
        return product

    async def search_products(
        self,
        query: str,
        *,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """Search products by name. Returns an empty list when nothing matches."""
        params = {"search_terms": query, "page_size": page_size}
        cache_key = self._build_cache_key("/search", {"search_terms": query})

        cached = await self._cache_get(cache_key)
        if cached is not None:
            return json.loads(cached)

        data = await self._get("/search", params=params)
        products: list[dict[str, Any]] = []
        if isinstance(data, dict):
            products = data.get("products", [])

        if products:
            await self._cache_set(cache_key, json.dumps(products), TTL_SEARCH)
        return products

    @staticmethod
    def extract_allergens(product: dict[str, Any]) -> list[str]:
        """Extract human-readable allergen names from a product dict.

        Allergen tags are in the format ``"en:milk"``, ``"en:nuts"``, etc.
        This strips the language prefix and returns clean names.
        """
        tags: list[str] = product.get("allergens_tags", [])
        allergens: list[str] = []
        for tag in tags:
            # Strip language prefix (e.g. "en:milk" → "milk")
            if ":" in tag:
                allergens.append(tag.split(":", maxsplit=1)[1])
            else:
                allergens.append(tag)
        return allergens
