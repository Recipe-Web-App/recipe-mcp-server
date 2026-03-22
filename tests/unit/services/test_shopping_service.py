"""Tests for ShoppingService."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from recipe_mcp_server.exceptions import NotFoundError
from recipe_mcp_server.models.common import MealType
from recipe_mcp_server.models.meal_plan import DayPlan, MealPlan, MealPlanItem
from recipe_mcp_server.models.recipe import Ingredient, Recipe
from recipe_mcp_server.services.shopping_service import ShoppingService


class TestGenerateFromRecipes:
    """Shopping list generation from recipe IDs."""

    async def test_aggregates_ingredients(
        self,
        shopping_service: ShoppingService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        recipe1 = Recipe(
            id="r1",
            title="Recipe A",
            ingredients=[
                Ingredient(name="flour", quantity=2.0, unit="cups"),
                Ingredient(name="sugar", quantity=1.0, unit="cups"),
            ],
        )
        recipe2 = Recipe(
            id="r2",
            title="Recipe B",
            ingredients=[
                Ingredient(name="flour", quantity=1.0, unit="cups"),
            ],
        )
        mock_recipe_repo.get.side_effect = lambda rid: {
            "r1": recipe1,
            "r2": recipe2,
        }.get(rid)

        items = await shopping_service.generate_from_recipes(["r1", "r2"])
        flour_items = [i for i in items if i.ingredient.lower() == "flour"]
        assert len(flour_items) == 1
        assert flour_items[0].quantity == pytest.approx(3.0)

    async def test_deduplicates_by_name(
        self,
        shopping_service: ShoppingService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        recipe = Recipe(
            id="r1",
            title="Test",
            ingredients=[
                Ingredient(name="Salt", quantity=1.0, unit="tsp"),
                Ingredient(name="salt", quantity=0.5, unit="tsp"),
            ],
        )
        mock_recipe_repo.get.return_value = recipe

        items = await shopping_service.generate_from_recipes(["r1"])
        salt_items = [i for i in items if i.ingredient.lower() == "salt"]
        assert len(salt_items) == 1
        assert salt_items[0].quantity == pytest.approx(1.5)

    async def test_keeps_different_units_separate(
        self,
        shopping_service: ShoppingService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        recipe = Recipe(
            id="r1",
            title="Test",
            ingredients=[
                Ingredient(name="flour", quantity=2.0, unit="cups"),
                Ingredient(name="flour", quantity=100.0, unit="g"),
            ],
        )
        mock_recipe_repo.get.return_value = recipe

        items = await shopping_service.generate_from_recipes(["r1"])
        flour_items = [i for i in items if i.ingredient.lower() == "flour"]
        assert len(flour_items) == 2

    async def test_skips_missing_recipes(
        self,
        shopping_service: ShoppingService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        recipe = Recipe(
            id="r1",
            title="Test",
            ingredients=[Ingredient(name="salt", quantity=1.0, unit="tsp")],
        )
        mock_recipe_repo.get.side_effect = lambda rid: recipe if rid == "r1" else None

        items = await shopping_service.generate_from_recipes(["r1", "missing"])
        assert len(items) == 1

    async def test_empty_recipes_returns_empty(
        self,
        shopping_service: ShoppingService,
    ) -> None:
        items = await shopping_service.generate_from_recipes([])
        assert items == []


class TestGenerateFromMealPlan:
    """Shopping list generation from a meal plan."""

    async def test_extracts_recipe_ids(
        self,
        shopping_service: ShoppingService,
        mock_meal_plan_repo: AsyncMock,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        plan = MealPlan(
            id="p1",
            name="Test Plan",
            start_date="2026-01-01",
            end_date="2026-01-01",
            days=[
                DayPlan(
                    date="2026-01-01",
                    meals=[
                        MealPlanItem(
                            day_date="2026-01-01",
                            meal_type=MealType.BREAKFAST,
                            recipe_id="r1",
                        ),
                        MealPlanItem(
                            day_date="2026-01-01",
                            meal_type=MealType.LUNCH,
                            custom_meal="Leftovers",
                        ),
                    ],
                ),
            ],
        )
        mock_meal_plan_repo.get.return_value = plan

        recipe = Recipe(
            id="r1",
            title="Breakfast",
            ingredients=[Ingredient(name="eggs", quantity=2.0, unit="pieces")],
        )
        mock_recipe_repo.get.return_value = recipe

        items = await shopping_service.generate_from_meal_plan("p1")
        assert len(items) == 1
        assert items[0].ingredient == "eggs"

    async def test_plan_not_found_raises(
        self,
        shopping_service: ShoppingService,
        mock_meal_plan_repo: AsyncMock,
    ) -> None:
        mock_meal_plan_repo.get.return_value = None
        with pytest.raises(NotFoundError, match="not found"):
            await shopping_service.generate_from_meal_plan("missing")
