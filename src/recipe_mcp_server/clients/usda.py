"""USDA FoodData Central API client.

Wraps https://api.nal.usda.gov/fdc/v1 with caching, retry,
and circuit-breaker behaviour inherited from :class:`BaseAPIClient`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from recipe_mcp_server.cache.keys import (
    TTL_NUTRITION,
    nutrition_key,
    search_key,
)
from recipe_mcp_server.clients.base import BaseAPIClient
from recipe_mcp_server.models.nutrition import FoodItem, NutrientInfo

logger = structlog.get_logger(__name__)

# USDA nutrient IDs → NutrientInfo field names (REQUIREMENTS 4.2)
USDA_NUTRIENT_MAP: dict[int, str] = {
    1008: "calories",
    1003: "protein_g",
    1004: "fat_g",
    1005: "carbs_g",
    1079: "fiber_g",
    2000: "sugar_g",
    1093: "sodium_mg",
}


class USDAClient(BaseAPIClient):
    """Client for the USDA FoodData Central API."""

    api_name = "USDA"
    base_url = "https://api.nal.usda.gov/fdc/v1"

    def __init__(
        self,
        *,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
        redis_client: Any | None = None,
    ) -> None:
        super().__init__(http_client=http_client, redis_client=redis_client)
        self._api_key = api_key

    # -- Abstract method required by BaseAPIClient ----------------------------

    def _build_cache_key(self, endpoint: str, params: dict[str, Any] | None) -> str:
        """Build a cache key based on the endpoint and query parameters."""
        params = params or {}

        if endpoint == "/foods/search":
            return search_key(params.get("query", ""))
        if endpoint.startswith("/food/"):
            fdc_id = endpoint.rsplit("/", maxsplit=1)[-1]
            return nutrition_key(fdc_id)
        return nutrition_key(f"{endpoint}:{json.dumps(params, sort_keys=True)}")

    # -- Private helpers ------------------------------------------------------

    @staticmethod
    def _extract_nutrients(food_nutrients: list[dict[str, Any]]) -> NutrientInfo:
        """Map USDA nutrient IDs to a :class:`NutrientInfo` instance."""
        values: dict[str, float] = {}
        full: dict[str, float] = {}

        for nutrient in food_nutrients:
            nutrient_id = nutrient.get("nutrientId") or nutrient.get("number")
            value = nutrient.get("value") or nutrient.get("amount", 0.0)
            name = nutrient.get("nutrientName", "")

            if nutrient_id is not None:
                nutrient_id = int(nutrient_id)
                field = USDA_NUTRIENT_MAP.get(nutrient_id)
                if field is not None:
                    values[field] = float(value)

            if name:
                full[name] = float(value)

        return NutrientInfo(
            calories=values.get("calories", 0.0),
            protein_g=values.get("protein_g", 0.0),
            fat_g=values.get("fat_g", 0.0),
            carbs_g=values.get("carbs_g", 0.0),
            fiber_g=values.get("fiber_g", 0.0),
            sugar_g=values.get("sugar_g", 0.0),
            sodium_mg=values.get("sodium_mg", 0.0),
            full_nutrients=full or None,
        )

    @classmethod
    def _food_to_item(cls, food: dict[str, Any]) -> FoodItem:
        """Map a raw USDA food dict to a domain :class:`FoodItem`."""
        nutrients = cls._extract_nutrients(food.get("foodNutrients", []))
        return FoodItem(
            food_name=food.get("description", ""),
            fdc_id=str(food.get("fdcId", "")),
            nutrients=nutrients,
            source="usda",
            fetched_at=datetime.now(tz=UTC),
        )

    # -- Public API methods ---------------------------------------------------

    async def search_foods(self, query: str, *, page_size: int = 25) -> list[FoodItem]:
        """Search foods by name. Returns an empty list when nothing matches."""
        params = {"query": query, "pageSize": page_size, "api_key": self._api_key}
        cache_key = self._build_cache_key("/foods/search", {"query": query})

        cached = await self._cache_get(cache_key)
        if cached is not None:
            foods: list[dict[str, Any]] = json.loads(cached)
            return [self._food_to_item(f) for f in foods]

        data = await self._get("/foods/search", params=params)
        foods = data.get("foods", []) if isinstance(data, dict) else []

        if foods:
            await self._cache_set(cache_key, json.dumps(foods), TTL_NUTRITION)
        return [self._food_to_item(f) for f in foods]

    async def get_food(self, fdc_id: str) -> FoodItem | None:
        """Get a single food item by its FDC ID."""
        endpoint = f"/food/{fdc_id}"
        cache_key = self._build_cache_key(endpoint, None)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            food: dict[str, Any] = json.loads(cached)
            return self._food_to_item(food)

        data = await self._get(endpoint, params={"api_key": self._api_key})
        if not isinstance(data, dict) or "fdcId" not in data:
            return None

        await self._cache_set(cache_key, json.dumps(data), TTL_NUTRITION)
        return self._food_to_item(data)

    async def get_nutrients(self, fdc_id: str) -> NutrientInfo:
        """Convenience method: get just the nutrient profile for a food."""
        food = await self.get_food(fdc_id)
        if food is None:
            return NutrientInfo()
        return food.nutrients
