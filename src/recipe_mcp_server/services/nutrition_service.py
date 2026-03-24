"""Nutrition service for food lookups and recipe analysis."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog

from recipe_mcp_server.clients.spoonacular import SpoonacularClient
from recipe_mcp_server.clients.usda import USDAClient
from recipe_mcp_server.db.repository import RecipeRepo
from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.models.nutrition import (
    IngredientNutrition,
    NutrientInfo,
    NutritionReport,
)
from recipe_mcp_server.models.recipe import Ingredient

logger = structlog.get_logger(__name__)

ProgressCallback = Callable[[int, int, str], Awaitable[None]]


def _aggregate_nutrients(items: list[IngredientNutrition]) -> NutrientInfo:
    """Sum nutrient values across all ingredients."""
    total = NutrientInfo()
    for item in items:
        n = item.nutrients
        total = NutrientInfo(
            calories=total.calories + n.calories,
            protein_g=total.protein_g + n.protein_g,
            fat_g=total.fat_g + n.fat_g,
            carbs_g=total.carbs_g + n.carbs_g,
            fiber_g=total.fiber_g + n.fiber_g,
            sugar_g=total.sugar_g + n.sugar_g,
            sodium_mg=total.sodium_mg + n.sodium_mg,
        )
    return total


def _divide_nutrients(total: NutrientInfo, divisor: int) -> NutrientInfo:
    """Divide all nutrient values by *divisor* for per-serving calculation."""
    return NutrientInfo(
        calories=total.calories / divisor,
        protein_g=total.protein_g / divisor,
        fat_g=total.fat_g / divisor,
        carbs_g=total.carbs_g / divisor,
        fiber_g=total.fiber_g / divisor,
        sugar_g=total.sugar_g / divisor,
        sodium_mg=total.sodium_mg / divisor,
    )


class NutritionService:
    """USDA-based nutrition lookup and per-recipe analysis."""

    def __init__(
        self,
        *,
        usda_client: USDAClient,
        spoonacular_client: SpoonacularClient,
        recipe_repo: RecipeRepo,
    ) -> None:
        self._usda_client = usda_client
        self._spoonacular_client = spoonacular_client
        self._recipe_repo = recipe_repo

    async def lookup(self, food_name: str) -> NutrientInfo:
        """Look up nutrition for a single food item via USDA.

        Raises ``NotFoundError`` when no matching food is found.
        """
        results = await self._usda_client.search_foods(food_name, page_size=1)
        if not results:
            raise NotFoundError(f"No nutrition data found for '{food_name}'")
        return results[0].nutrients

    async def analyze_recipe(
        self,
        recipe_id: str,
        on_progress: ProgressCallback | None = None,
    ) -> NutritionReport:
        """Compute per-serving and total nutrition for a recipe."""
        recipe = await self._recipe_repo.get(recipe_id)
        if recipe is None:
            raise NotFoundError(f"Recipe '{recipe_id}' not found")

        servings = recipe.servings
        if servings <= 0:
            msg = f"Recipe '{recipe_id}' has invalid servings value: {servings}"
            raise ValueError(msg)

        total_ingredients = len(recipe.ingredients)
        ingredient_results: list[IngredientNutrition] = []
        for i, ing in enumerate(recipe.ingredients):
            if on_progress:
                await on_progress(
                    i,
                    total_ingredients,
                    f"Looking up {ing.name}...",
                )
            nutrition = await self._get_ingredient_nutrition(ing)
            ingredient_results.append(nutrition)
        if on_progress:
            await on_progress(
                total_ingredients,
                total_ingredients,
                "Calculating totals...",
            )

        total = _aggregate_nutrients(ingredient_results)
        per_serving = _divide_nutrients(total, servings)

        return NutritionReport(
            per_serving=per_serving,
            total=total,
            ingredients=ingredient_results,
            servings=recipe.servings,
        )

    async def _get_ingredient_nutrition(
        self,
        ingredient: Ingredient,
    ) -> IngredientNutrition:
        """Look up nutrition for a single ingredient with USDA fallback to zeroed data."""
        try:
            results = await self._usda_client.search_foods(ingredient.name, page_size=1)
            if results:
                return IngredientNutrition(
                    ingredient_name=ingredient.name,
                    quantity=ingredient.quantity,
                    unit=ingredient.unit,
                    nutrients=results[0].nutrients,
                )
        except ExternalAPIError:
            logger.warning(
                "usda_lookup_failed",
                ingredient=ingredient.name,
                exc_info=True,
            )

        logger.warning("ingredient_nutrition_unavailable", ingredient=ingredient.name)
        return IngredientNutrition(
            ingredient_name=ingredient.name,
            quantity=ingredient.quantity,
            unit=ingredient.unit,
            nutrients=NutrientInfo(),
        )
