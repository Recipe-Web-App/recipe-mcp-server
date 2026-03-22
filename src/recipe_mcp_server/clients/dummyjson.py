"""DummyJSON API client.

Wraps https://dummyjson.com for mock recipe data.
No authentication required. Used as a fallback source.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from recipe_mcp_server.cache.keys import (
    TTL_FILTER,
    TTL_INGREDIENTS,
    TTL_RECIPE,
    TTL_SEARCH,
    recipe_key,
    search_key,
)
from recipe_mcp_server.clients.base import BaseAPIClient
from recipe_mcp_server.models.common import APISource, Difficulty
from recipe_mcp_server.models.recipe import Ingredient, Recipe

logger = structlog.get_logger(__name__)

_DIFFICULTY_MAP: dict[str, Difficulty] = {
    "easy": Difficulty.EASY,
    "medium": Difficulty.MEDIUM,
    "hard": Difficulty.HARD,
}


class DummyJSONClient(BaseAPIClient):
    """Client for the DummyJSON mock recipe API."""

    api_name = "DummyJSON"
    base_url = "https://dummyjson.com"

    # -- Abstract method required by BaseAPIClient ----------------------------

    def _build_cache_key(self, endpoint: str, params: dict[str, Any] | None) -> str:
        """Build a cache key based on the endpoint and query parameters."""
        params = params or {}

        if endpoint == "/recipes" and "limit" in params:
            return search_key(f"dummyjson:list:{params.get('skip', 0)}")
        if endpoint == "/recipes/search":
            return search_key(f"dummyjson:{params.get('q', '')}")
        if endpoint == "/recipes/tags":
            return search_key("dummyjson:tags")
        if endpoint.startswith("/recipes/tag/"):
            tag = endpoint.rsplit("/", maxsplit=1)[-1]
            return search_key(f"dummyjson:tag:{tag}")
        if endpoint.startswith("/recipes/meal-type/"):
            meal_type = endpoint.rsplit("/", maxsplit=1)[-1]
            return search_key(f"dummyjson:meal-type:{meal_type}")
        if endpoint.startswith("/recipes/"):
            recipe_id = endpoint.rsplit("/", maxsplit=1)[-1]
            return recipe_key("dummyjson", recipe_id)
        return search_key(f"{endpoint}:{json.dumps(params, sort_keys=True)}")

    # -- Data mapping helpers -------------------------------------------------

    @staticmethod
    def _dummyjson_to_recipe(data: dict[str, Any]) -> Recipe:
        """Map a DummyJSON recipe dict to a domain :class:`Recipe`."""
        raw_ingredients: list[str] = data.get("ingredients", [])
        ingredients = [
            Ingredient(name=name, order_index=idx) for idx, name in enumerate(raw_ingredients)
        ]

        raw_difficulty = (data.get("difficulty") or "").lower()

        tags: list[str] = data.get("tags", [])
        meal_types: list[str] = data.get("mealType", [])
        all_tags = tags + [mt for mt in meal_types if mt not in tags]

        return Recipe(
            title=data.get("name", ""),
            instructions=data.get("instructions", []),
            category=None,
            area=data.get("cuisine"),
            image_url=data.get("image"),
            source_api=APISource.DUMMYJSON,
            source_id=str(data.get("id", "")),
            prep_time_min=data.get("prepTimeMinutes"),
            cook_time_min=data.get("cookTimeMinutes"),
            servings=data.get("servings", 4),
            difficulty=_DIFFICULTY_MAP.get(raw_difficulty),
            tags=all_tags,
            ingredients=ingredients,
        )

    @staticmethod
    def _extract_recipes(data: Any) -> list[dict[str, Any]]:
        """Return the recipes list from an API response, or empty list."""
        if isinstance(data, dict):
            recipes = data.get("recipes")
            if isinstance(recipes, list):
                return recipes
        return []

    # -- Public API methods ---------------------------------------------------

    async def list_recipes(self, *, limit: int = 30, skip: int = 0) -> list[Recipe]:
        """Get a paginated list of recipes."""
        params = {"limit": limit, "skip": skip}
        cache_key = self._build_cache_key("/recipes", params)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            recipes: list[dict[str, Any]] = json.loads(cached)
            return [self._dummyjson_to_recipe(r) for r in recipes]

        data = await self._get("/recipes", params=params)
        recipes = self._extract_recipes(data)

        if recipes:
            await self._cache_set(cache_key, json.dumps(recipes), TTL_RECIPE)
        return [self._dummyjson_to_recipe(r) for r in recipes]

    async def get_recipe(self, recipe_id: int) -> Recipe | None:
        """Get a single recipe by ID."""
        endpoint = f"/recipes/{recipe_id}"
        cache_key = self._build_cache_key(endpoint, None)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            data: dict[str, Any] = json.loads(cached)
            return self._dummyjson_to_recipe(data)

        data = await self._get(endpoint)
        if not isinstance(data, dict) or "id" not in data:
            return None

        await self._cache_set(cache_key, json.dumps(data), TTL_RECIPE)
        return self._dummyjson_to_recipe(data)

    async def search_recipes(self, query: str) -> list[Recipe]:
        """Search recipes by name. Returns an empty list when nothing matches."""
        params = {"q": query}
        cache_key = self._build_cache_key("/recipes/search", params)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            recipes: list[dict[str, Any]] = json.loads(cached)
            return [self._dummyjson_to_recipe(r) for r in recipes]

        data = await self._get("/recipes/search", params=params)
        recipes = self._extract_recipes(data)

        if recipes:
            await self._cache_set(cache_key, json.dumps(recipes), TTL_SEARCH)
        return [self._dummyjson_to_recipe(r) for r in recipes]

    async def list_tags(self) -> list[str]:
        """Get all available recipe tags."""
        cache_key = self._build_cache_key("/recipes/tags", None)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            return json.loads(cached)

        data = await self._get("/recipes/tags")
        tags: list[str] = data if isinstance(data, list) else []

        if tags:
            await self._cache_set(cache_key, json.dumps(tags), TTL_INGREDIENTS)
        return tags

    async def get_by_tag(self, tag: str) -> list[Recipe]:
        """Get recipes filtered by tag."""
        endpoint = f"/recipes/tag/{tag}"
        cache_key = self._build_cache_key(endpoint, None)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            recipes: list[dict[str, Any]] = json.loads(cached)
            return [self._dummyjson_to_recipe(r) for r in recipes]

        data = await self._get(endpoint)
        recipes = self._extract_recipes(data)

        if recipes:
            await self._cache_set(cache_key, json.dumps(recipes), TTL_FILTER)
        return [self._dummyjson_to_recipe(r) for r in recipes]

    async def get_by_meal_type(self, meal_type: str) -> list[Recipe]:
        """Get recipes filtered by meal type."""
        endpoint = f"/recipes/meal-type/{meal_type}"
        cache_key = self._build_cache_key(endpoint, None)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            recipes: list[dict[str, Any]] = json.loads(cached)
            return [self._dummyjson_to_recipe(r) for r in recipes]

        data = await self._get(endpoint)
        recipes = self._extract_recipes(data)

        if recipes:
            await self._cache_set(cache_key, json.dumps(recipes), TTL_FILTER)
        return [self._dummyjson_to_recipe(r) for r in recipes]
