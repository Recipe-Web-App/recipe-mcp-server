"""Shopping list service for ingredient aggregation and deduplication."""

from __future__ import annotations

from collections import defaultdict

import structlog

from recipe_mcp_server.db.repository import MealPlanRepo, RecipeRepo
from recipe_mcp_server.exceptions import NotFoundError
from recipe_mcp_server.models.meal_plan import ShoppingItem
from recipe_mcp_server.models.recipe import Ingredient
from recipe_mcp_server.services.conversion_service import ConversionService

logger = structlog.get_logger(__name__)


def _normalize_name(name: str) -> str:
    """Normalize an ingredient name for grouping."""
    return name.strip().lower()


def _aggregate_ingredients(
    items: list[tuple[str, Ingredient]],
    conversion_service: ConversionService,
) -> list[ShoppingItem]:
    """Group ingredients by normalized name and sum compatible quantities.

    Args:
        items: List of (recipe_title, ingredient) tuples.
        conversion_service: Used to attempt unit normalization.

    Returns:
        Deduplicated shopping items sorted by ingredient name.
    """
    # Group by normalized ingredient name
    groups: dict[str, list[tuple[str, Ingredient]]] = defaultdict(list)
    for recipe_title, ing in items:
        key = _normalize_name(ing.name)
        groups[key].append((recipe_title, ing))

    result: list[ShoppingItem] = []
    for _key, group in sorted(groups.items()):
        # Collect all recipe titles contributing to this ingredient
        recipe_titles = list({title for title, _ing in group})

        # Try to sum quantities when units match
        subgroups: dict[str | None, list[tuple[str, Ingredient]]] = defaultdict(list)
        for title, ing in group:
            unit = ing.unit.strip().lower() if ing.unit else None
            subgroups[unit].append((title, ing))

        for normalized_unit, unit_group in subgroups.items():
            total_qty: float | None = None
            all_have_qty = all(ing.quantity is not None for _, ing in unit_group)

            if all_have_qty:
                total_qty = sum(ing.quantity for _, ing in unit_group if ing.quantity is not None)

            # Use the original ingredient name from the first entry
            display_name = unit_group[0][1].name
            # Prefer the original casing from the ingredient, fall back to normalized
            display_unit = unit_group[0][1].unit or normalized_unit

            result.append(
                ShoppingItem(
                    ingredient=display_name,
                    quantity=total_qty,
                    unit=display_unit,
                    recipes=recipe_titles,
                ),
            )

    return result


class ShoppingService:
    """Generates shopping lists by aggregating ingredients across recipes."""

    def __init__(
        self,
        *,
        recipe_repo: RecipeRepo,
        meal_plan_repo: MealPlanRepo,
        conversion_service: ConversionService,
    ) -> None:
        self._recipe_repo = recipe_repo
        self._meal_plan_repo = meal_plan_repo
        self._conversion_service = conversion_service

    async def generate_from_recipes(
        self,
        recipe_ids: list[str],
    ) -> list[ShoppingItem]:
        """Generate a shopping list from a set of recipe IDs.

        Missing recipes are skipped with a warning.
        """
        items: list[tuple[str, Ingredient]] = []

        for recipe_id in recipe_ids:
            recipe = await self._recipe_repo.get(recipe_id)
            if recipe is None:
                logger.warning("shopping_recipe_not_found", recipe_id=recipe_id)
                continue

            for ing in recipe.ingredients:
                items.append((recipe.title, ing))

        return _aggregate_ingredients(items, self._conversion_service)

    async def generate_from_meal_plan(
        self,
        plan_id: str,
    ) -> list[ShoppingItem]:
        """Generate a shopping list from all recipes in a meal plan."""
        plan = await self._meal_plan_repo.get(plan_id)
        if plan is None:
            raise NotFoundError(f"Meal plan '{plan_id}' not found")

        recipe_ids: list[str] = []
        for day in plan.days:
            for meal in day.meals:
                if meal.recipe_id:
                    recipe_ids.append(meal.recipe_id)

        return await self.generate_from_recipes(recipe_ids)
