"""Spoonacular API client.

Wraps https://api.spoonacular.com with caching, retry,
and circuit-breaker behaviour inherited from :class:`BaseAPIClient`.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from recipe_mcp_server.cache.keys import (
    TTL_CONVERSION,
    TTL_FILTER,
    TTL_NUTRITION,
    TTL_RECIPE,
    TTL_SEARCH,
    TTL_SUBSTITUTES,
    TTL_WINE_PAIRING,
    conversion_key,
    recipe_key,
    search_key,
    substitutes_key,
    wine_pairing_key,
)
from recipe_mcp_server.clients.base import BaseAPIClient
from recipe_mcp_server.models.common import APISource, Difficulty
from recipe_mcp_server.models.nutrition import NutrientInfo
from recipe_mcp_server.models.recipe import Ingredient, Recipe, RecipeSummary

logger = structlog.get_logger(__name__)


class SpoonacularClient(BaseAPIClient):
    """Client for the Spoonacular recipe API."""

    api_name = "Spoonacular"
    base_url = "https://api.spoonacular.com"

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

        if endpoint == "/recipes/complexSearch":
            return search_key(
                params.get("query", ""),
                cuisine=params.get("cuisine", ""),
                diet=params.get("diet", ""),
            )
        if "/information" in endpoint:
            recipe_id = endpoint.split("/")[2]
            return recipe_key("spoonacular", recipe_id)
        if "/similar" in endpoint:
            recipe_id = endpoint.split("/")[2]
            return search_key(f"similar:{recipe_id}")
        if endpoint == "/mealplanner/generate":
            return search_key(json.dumps(params, sort_keys=True))
        if endpoint == "/food/wine/pairing":
            return wine_pairing_key(params.get("food", ""))
        if endpoint == "/food/ingredients/substitutes":
            return substitutes_key(params.get("ingredientName", ""))
        if endpoint == "/recipes/convert":
            return conversion_key(
                params.get("ingredientName", ""),
                params.get("sourceUnit", ""),
                params.get("targetUnit", ""),
            )
        if "/nutritionWidget.json" in endpoint:
            recipe_id = endpoint.split("/")[2]
            return search_key(f"nutrition:{recipe_id}")
        return search_key(f"{endpoint}:{json.dumps(params, sort_keys=True)}")

    # -- Data mapping helpers -------------------------------------------------

    @staticmethod
    def _spoonacular_to_recipe(data: dict[str, Any]) -> Recipe:
        """Map a Spoonacular recipe dict to a domain :class:`Recipe`."""
        raw_instructions = data.get("instructions") or ""
        instructions: list[str] = []
        if raw_instructions:
            instructions = [
                line.strip()
                for line in raw_instructions.replace("\r\n", "\n").split("\n")
                if line.strip()
            ]

        # Parse extended ingredients if available
        ingredients: list[Ingredient] = []
        for idx, ing in enumerate(data.get("extendedIngredients", [])):
            ingredients.append(
                Ingredient(
                    name=ing.get("name", ""),
                    quantity=ing.get("amount"),
                    unit=ing.get("unit") or None,
                    order_index=idx,
                ),
            )

        # Map difficulty from readyInMinutes
        ready_minutes = data.get("readyInMinutes")
        difficulty = None
        if ready_minutes is not None:
            if ready_minutes <= 30:
                difficulty = Difficulty.EASY
            elif ready_minutes <= 60:
                difficulty = Difficulty.MEDIUM
            else:
                difficulty = Difficulty.HARD

        return Recipe(
            title=data.get("title", ""),
            description=data.get("summary"),
            instructions=instructions,
            category=None,
            area=None,
            image_url=data.get("image"),
            source_url=data.get("sourceUrl") or data.get("spoonacularSourceUrl"),
            source_api=APISource.SPOONACULAR,
            source_id=str(data.get("id", "")),
            prep_time_min=data.get("preparationMinutes"),
            cook_time_min=data.get("cookingMinutes"),
            servings=data.get("servings", 4),
            difficulty=difficulty,
            tags=[dt.get("name", "") for dt in data.get("dishTypes", []) if dt.get("name")]
            if isinstance(data.get("dishTypes"), list)
            and data["dishTypes"]
            and isinstance(data["dishTypes"][0], dict)
            else data.get("dishTypes", []),
            ingredients=ingredients,
        )

    @staticmethod
    def _spoonacular_to_summary(data: dict[str, Any]) -> RecipeSummary:
        """Map a Spoonacular search result to a :class:`RecipeSummary`."""
        return RecipeSummary(
            id=str(data.get("id", "")),
            title=data.get("title", ""),
            image_url=data.get("image"),
            source_api=APISource.SPOONACULAR,
        )

    # -- Public API methods ---------------------------------------------------

    async def search_recipes(
        self,
        query: str,
        *,
        cuisine: str = "",
        diet: str = "",
        number: int = 10,
    ) -> list[RecipeSummary]:
        """Advanced recipe search. Returns summary-level data."""
        params: dict[str, Any] = {
            "query": query,
            "number": number,
            "apiKey": self._api_key,
        }
        if cuisine:
            params["cuisine"] = cuisine
        if diet:
            params["diet"] = diet

        cache_key = self._build_cache_key(
            "/recipes/complexSearch",
            {"query": query, "cuisine": cuisine, "diet": diet},
        )

        cached = await self._cache_get(cache_key)
        if cached is not None:
            results: list[dict[str, Any]] = json.loads(cached)
            return [self._spoonacular_to_summary(r) for r in results]

        data = await self._get("/recipes/complexSearch", params=params)
        results = data.get("results", []) if isinstance(data, dict) else []

        if results:
            await self._cache_set(cache_key, json.dumps(results), TTL_SEARCH)
        return [self._spoonacular_to_summary(r) for r in results]

    async def get_recipe_info(self, recipe_id: int) -> Recipe | None:
        """Get full recipe details by Spoonacular ID."""
        endpoint = f"/recipes/{recipe_id}/information"
        cache_key = self._build_cache_key(endpoint, None)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            data: dict[str, Any] = json.loads(cached)
            return self._spoonacular_to_recipe(data)

        data = await self._get(endpoint, params={"apiKey": self._api_key})
        if not isinstance(data, dict) or "id" not in data:
            return None

        await self._cache_set(cache_key, json.dumps(data), TTL_RECIPE)
        return self._spoonacular_to_recipe(data)

    async def get_similar(self, recipe_id: int) -> list[RecipeSummary]:
        """Get similar recipes by Spoonacular ID."""
        endpoint = f"/recipes/{recipe_id}/similar"
        cache_key = self._build_cache_key(endpoint, None)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            results: list[dict[str, Any]] = json.loads(cached)
            return [self._spoonacular_to_summary(r) for r in results]

        data = await self._get(endpoint, params={"apiKey": self._api_key})
        results = data if isinstance(data, list) else []

        if results:
            await self._cache_set(cache_key, json.dumps(results), TTL_FILTER)
        return [self._spoonacular_to_summary(r) for r in results]

    async def generate_meal_plan(
        self,
        *,
        time_frame: str = "week",
        target_calories: int = 2000,
        diet: str = "",
    ) -> dict[str, Any]:
        """Generate a meal plan via Spoonacular."""
        params: dict[str, Any] = {
            "timeFrame": time_frame,
            "targetCalories": target_calories,
            "apiKey": self._api_key,
        }
        if diet:
            params["diet"] = diet

        cache_params = {
            "timeFrame": time_frame,
            "targetCalories": str(target_calories),
            "diet": diet,
        }
        cache_key = self._build_cache_key("/mealplanner/generate", cache_params)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            return json.loads(cached)

        data = await self._get("/mealplanner/generate", params=params)
        if isinstance(data, dict):
            await self._cache_set(cache_key, json.dumps(data), TTL_SEARCH)
        return data if isinstance(data, dict) else {}

    async def get_wine_pairing(self, food: str) -> dict[str, Any]:
        """Get wine pairing suggestions for a food."""
        params = {"food": food, "apiKey": self._api_key}
        cache_key = self._build_cache_key("/food/wine/pairing", {"food": food})

        cached = await self._cache_get(cache_key)
        if cached is not None:
            return json.loads(cached)

        data = await self._get("/food/wine/pairing", params=params)
        if isinstance(data, dict):
            await self._cache_set(cache_key, json.dumps(data), TTL_WINE_PAIRING)
        return data if isinstance(data, dict) else {}

    async def get_substitutes(self, ingredient: str) -> list[str]:
        """Get ingredient substitution suggestions."""
        params = {"ingredientName": ingredient, "apiKey": self._api_key}
        cache_key = self._build_cache_key(
            "/food/ingredients/substitutes", {"ingredientName": ingredient}
        )

        cached = await self._cache_get(cache_key)
        if cached is not None:
            return json.loads(cached)

        data = await self._get("/food/ingredients/substitutes", params=params)
        substitutes: list[str] = []
        if isinstance(data, dict):
            substitutes = data.get("substitutes", [])

        if substitutes:
            await self._cache_set(cache_key, json.dumps(substitutes), TTL_SUBSTITUTES)
        return substitutes

    async def convert_amounts(
        self,
        ingredient: str,
        source_amount: float,
        source_unit: str,
        target_unit: str,
    ) -> dict[str, Any]:
        """Convert ingredient amounts between units."""
        params = {
            "ingredientName": ingredient,
            "sourceAmount": source_amount,
            "sourceUnit": source_unit,
            "targetUnit": target_unit,
            "apiKey": self._api_key,
        }
        cache_key = self._build_cache_key(
            "/recipes/convert",
            {"ingredientName": ingredient, "sourceUnit": source_unit, "targetUnit": target_unit},
        )

        cached = await self._cache_get(cache_key)
        if cached is not None:
            return json.loads(cached)

        data = await self._get("/recipes/convert", params=params)
        if isinstance(data, dict):
            await self._cache_set(cache_key, json.dumps(data), TTL_CONVERSION)
        return data if isinstance(data, dict) else {}

    async def get_recipe_nutrition(self, recipe_id: int) -> NutrientInfo:
        """Get nutrition information for a recipe."""
        endpoint = f"/recipes/{recipe_id}/nutritionWidget.json"
        cache_key = self._build_cache_key(endpoint, None)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            data: dict[str, Any] = json.loads(cached)
            return self._parse_nutrition(data)

        data = await self._get(endpoint, params={"apiKey": self._api_key})
        if not isinstance(data, dict):
            return NutrientInfo()

        await self._cache_set(cache_key, json.dumps(data), TTL_NUTRITION)
        return self._parse_nutrition(data)

    @staticmethod
    def _parse_nutrition(data: dict[str, Any]) -> NutrientInfo:
        """Parse Spoonacular nutrition widget response into NutrientInfo."""
        return NutrientInfo(
            calories=float(data.get("calories", "0").replace("k", "")),
            protein_g=float(data.get("protein", "0g").replace("g", "")),
            fat_g=float(data.get("fat", "0g").replace("g", "")),
            carbs_g=float(data.get("carbs", "0g").replace("g", "")),
        )
