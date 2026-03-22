"""TheMealDB API client.

Wraps https://www.themealdb.com/api/json/v1/1 with caching, retry,
and circuit-breaker behaviour inherited from :class:`BaseAPIClient`.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from recipe_mcp_server.cache.keys import (
    TTL_CATEGORIES,
    TTL_CUISINES,
    TTL_FILTER,
    TTL_INGREDIENTS,
    TTL_RECIPE,
    TTL_SEARCH,
    categories_key,
    cuisines_key,
    ingredients_key,
    recipe_key,
    search_key,
)
from recipe_mcp_server.clients.base import BaseAPIClient
from recipe_mcp_server.models.common import APISource
from recipe_mcp_server.models.recipe import Ingredient, Recipe, RecipeSummary

logger = structlog.get_logger(__name__)

_MAX_INGREDIENT_SLOTS = 20


class TheMealDBClient(BaseAPIClient):
    """Client for TheMealDB free recipe API."""

    api_name = "TheMealDB"
    base_url = "https://www.themealdb.com/api/json/v1/1"

    # -- Abstract method required by BaseAPIClient ----------------------------

    def _build_cache_key(self, endpoint: str, params: dict[str, Any] | None) -> str:
        """Build a cache key based on the endpoint and query parameters."""
        params = params or {}

        if endpoint == "/search.php":
            return search_key(params.get("s", ""))
        if endpoint == "/lookup.php":
            return recipe_key("themealdb", params.get("i", ""))
        if endpoint == "/categories.php":
            return categories_key()
        if endpoint == "/list.php":
            if "a" in params:
                return cuisines_key()
            if "i" in params:
                return ingredients_key()
            return categories_key()
        if endpoint == "/filter.php":
            return search_key(json.dumps(params, sort_keys=True))
        return search_key(f"{endpoint}:{json.dumps(params, sort_keys=True)}")

    # -- Data mapping helpers -------------------------------------------------

    @staticmethod
    def _parse_ingredients(meal: dict[str, Any]) -> list[Ingredient]:
        """Extract ingredients from TheMealDB's flat strIngredient/strMeasure fields."""
        ingredients: list[Ingredient] = []
        for i in range(1, _MAX_INGREDIENT_SLOTS + 1):
            name = (meal.get(f"strIngredient{i}") or "").strip()
            if not name:
                continue
            measure = (meal.get(f"strMeasure{i}") or "").strip()
            ingredients.append(
                Ingredient(
                    name=name,
                    unit=measure or None,
                    order_index=len(ingredients),
                ),
            )
        return ingredients

    @classmethod
    def _meal_to_recipe(cls, meal: dict[str, Any]) -> Recipe:
        """Map a TheMealDB meal dict to a domain :class:`Recipe`."""
        raw_instructions = meal.get("strInstructions") or ""
        instructions = [
            line.strip()
            for line in raw_instructions.replace("\r\n", "\n").split("\n")
            if line.strip()
        ]

        raw_tags = meal.get("strTags") or ""
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else []

        return Recipe(
            title=meal.get("strMeal", ""),
            instructions=instructions,
            category=meal.get("strCategory"),
            area=meal.get("strArea"),
            image_url=meal.get("strMealThumb"),
            source_url=meal.get("strSource") or None,
            source_api=APISource.THEMEALDB,
            source_id=meal.get("idMeal"),
            tags=tags,
            ingredients=cls._parse_ingredients(meal),
        )

    @staticmethod
    def _meal_to_summary(meal: dict[str, Any]) -> RecipeSummary:
        """Map a partial TheMealDB meal dict to a :class:`RecipeSummary`."""
        return RecipeSummary(
            id=meal.get("idMeal", ""),
            title=meal.get("strMeal", ""),
            image_url=meal.get("strMealThumb"),
            source_api=APISource.THEMEALDB,
        )

    # -- Convenience for safe meals extraction --------------------------------

    @staticmethod
    def _extract_meals(data: Any) -> list[dict[str, Any]]:
        """Return the ``meals`` list from an API response, or empty list if null."""
        if isinstance(data, dict):
            meals = data.get("meals")
            if isinstance(meals, list):
                return meals
        return []

    # -- Public API methods ---------------------------------------------------

    async def search_by_name(self, name: str) -> list[Recipe]:
        """Search meals by name.  Returns an empty list when nothing matches."""
        cache_key = self._build_cache_key("/search.php", {"s": name})

        cached = await self._cache_get(cache_key)
        if cached is not None:
            meals: list[dict[str, Any]] = json.loads(cached)
            return [self._meal_to_recipe(m) for m in meals]

        data = await self._get("/search.php", params={"s": name})
        meals = self._extract_meals(data)

        if meals:
            await self._cache_set(cache_key, json.dumps(meals), TTL_SEARCH)
        return [self._meal_to_recipe(m) for m in meals]

    async def lookup_by_id(self, meal_id: str) -> Recipe | None:
        """Look up a single meal by its TheMealDB ID."""
        cache_key = self._build_cache_key("/lookup.php", {"i": meal_id})

        cached = await self._cache_get(cache_key)
        if cached is not None:
            meals: list[dict[str, Any]] = json.loads(cached)
            return self._meal_to_recipe(meals[0]) if meals else None

        data = await self._get("/lookup.php", params={"i": meal_id})
        meals = self._extract_meals(data)

        if meals:
            await self._cache_set(cache_key, json.dumps(meals), TTL_RECIPE)
            return self._meal_to_recipe(meals[0])
        return None

    async def random_meal(self) -> Recipe | None:
        """Fetch a single random meal.  Not cached per requirements."""
        data = await self._get("/random.php")
        meals = self._extract_meals(data)
        return self._meal_to_recipe(meals[0]) if meals else None

    async def list_categories(self) -> list[dict[str, Any]]:
        """Return all meal categories with metadata."""
        cache_key = self._build_cache_key("/categories.php", None)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            result: list[dict[str, Any]] = json.loads(cached)
            return result

        data = await self._get("/categories.php")
        categories: list[dict[str, Any]] = []
        if isinstance(data, dict):
            categories = data.get("categories", [])

        if categories:
            await self._cache_set(cache_key, json.dumps(categories), TTL_CATEGORIES)
        return categories

    async def list_areas(self) -> list[str]:
        """Return all available area/cuisine names."""
        cache_key = self._build_cache_key("/list.php", {"a": "list"})

        cached = await self._cache_get(cache_key)
        if cached is not None:
            areas: list[str] = json.loads(cached)
            return areas

        data = await self._get("/list.php", params={"a": "list"})
        meals = self._extract_meals(data)
        areas = [m["strArea"] for m in meals if m.get("strArea")]

        if areas:
            await self._cache_set(cache_key, json.dumps(areas), TTL_CUISINES)
        return areas

    async def list_ingredients(self) -> list[dict[str, Any]]:
        """Return all available ingredients with descriptions."""
        cache_key = self._build_cache_key("/list.php", {"i": "list"})

        cached = await self._cache_get(cache_key)
        if cached is not None:
            result: list[dict[str, Any]] = json.loads(cached)
            return result

        data = await self._get("/list.php", params={"i": "list"})
        meals = self._extract_meals(data)

        if meals:
            await self._cache_set(cache_key, json.dumps(meals), TTL_INGREDIENTS)
        return meals

    async def filter_by_category(self, category: str) -> list[RecipeSummary]:
        """Filter meals by category.  Returns summary-level data."""
        cache_key = self._build_cache_key("/filter.php", {"c": category})

        cached = await self._cache_get(cache_key)
        if cached is not None:
            meals: list[dict[str, Any]] = json.loads(cached)
            return [self._meal_to_summary(m) for m in meals]

        data = await self._get("/filter.php", params={"c": category})
        meals = self._extract_meals(data)

        if meals:
            await self._cache_set(cache_key, json.dumps(meals), TTL_FILTER)
        return [self._meal_to_summary(m) for m in meals]

    async def filter_by_area(self, area: str) -> list[RecipeSummary]:
        """Filter meals by area/cuisine.  Returns summary-level data."""
        cache_key = self._build_cache_key("/filter.php", {"a": area})

        cached = await self._cache_get(cache_key)
        if cached is not None:
            meals: list[dict[str, Any]] = json.loads(cached)
            return [self._meal_to_summary(m) for m in meals]

        data = await self._get("/filter.php", params={"a": area})
        meals = self._extract_meals(data)

        if meals:
            await self._cache_set(cache_key, json.dumps(meals), TTL_FILTER)
        return [self._meal_to_summary(m) for m in meals]

    async def filter_by_ingredient(self, ingredient: str) -> list[RecipeSummary]:
        """Filter meals by main ingredient.  Returns summary-level data."""
        cache_key = self._build_cache_key("/filter.php", {"i": ingredient})

        cached = await self._cache_get(cache_key)
        if cached is not None:
            meals: list[dict[str, Any]] = json.loads(cached)
            return [self._meal_to_summary(m) for m in meals]

        data = await self._get("/filter.php", params={"i": ingredient})
        meals = self._extract_meals(data)

        if meals:
            await self._cache_set(cache_key, json.dumps(meals), TTL_SEARCH)
        return [self._meal_to_summary(m) for m in meals]
