"""Tests for NutritionService."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.models.nutrition import FoodItem, NutrientInfo
from recipe_mcp_server.models.recipe import Ingredient, Recipe
from recipe_mcp_server.services.nutrition_service import NutritionService


class TestLookup:
    """Single food nutrition lookup."""

    async def test_returns_nutrients(
        self,
        nutrition_service: NutritionService,
        mock_usda_client: AsyncMock,
    ) -> None:
        nutrients = NutrientInfo(calories=165.0, protein_g=31.0, fat_g=3.6)
        mock_usda_client.search_foods.return_value = [
            FoodItem(food_name="chicken breast", nutrients=nutrients, source="usda"),
        ]

        result = await nutrition_service.lookup("chicken breast")
        assert result.calories == pytest.approx(165.0)
        assert result.protein_g == pytest.approx(31.0)

    async def test_raises_not_found_on_empty(
        self,
        nutrition_service: NutritionService,
        mock_usda_client: AsyncMock,
    ) -> None:
        mock_usda_client.search_foods.return_value = []
        with pytest.raises(NotFoundError, match="No nutrition data"):
            await nutrition_service.lookup("nonexistent food")


class TestAnalyzeRecipe:
    """Per-recipe nutrition analysis."""

    async def test_aggregates_ingredients(
        self,
        nutrition_service: NutritionService,
        mock_recipe_repo: AsyncMock,
        mock_usda_client: AsyncMock,
    ) -> None:
        recipe = Recipe(
            id="r1",
            title="Test",
            servings=2,
            ingredients=[
                Ingredient(name="chicken", quantity=200.0, unit="g"),
                Ingredient(name="rice", quantity=100.0, unit="g"),
            ],
        )
        mock_recipe_repo.get.return_value = recipe

        chicken_nutrients = NutrientInfo(calories=330.0, protein_g=62.0)
        rice_nutrients = NutrientInfo(calories=130.0, carbs_g=28.0)

        mock_usda_client.search_foods.side_effect = [
            [FoodItem(food_name="chicken", nutrients=chicken_nutrients, source="usda")],
            [FoodItem(food_name="rice", nutrients=rice_nutrients, source="usda")],
        ]

        report = await nutrition_service.analyze_recipe("r1")
        assert report.servings == 2
        assert report.total.calories == pytest.approx(460.0)
        assert report.total.protein_g == pytest.approx(62.0)
        assert report.total.carbs_g == pytest.approx(28.0)
        assert report.per_serving.calories == pytest.approx(230.0)
        assert len(report.ingredients) == 2

    async def test_recipe_not_found(
        self,
        nutrition_service: NutritionService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        mock_recipe_repo.get.return_value = None
        with pytest.raises(NotFoundError, match="not found"):
            await nutrition_service.analyze_recipe("missing")

    async def test_usda_failure_returns_zeroed(
        self,
        nutrition_service: NutritionService,
        mock_recipe_repo: AsyncMock,
        mock_usda_client: AsyncMock,
    ) -> None:
        recipe = Recipe(
            id="r1",
            title="Test",
            servings=1,
            ingredients=[Ingredient(name="unknown food", quantity=1.0, unit="cup")],
        )
        mock_recipe_repo.get.return_value = recipe
        mock_usda_client.search_foods.side_effect = ExternalAPIError("fail")

        report = await nutrition_service.analyze_recipe("r1")
        assert report.total.calories == pytest.approx(0.0)
        assert report.ingredients[0].nutrients.calories == pytest.approx(0.0)

    async def test_per_serving_division(
        self,
        nutrition_service: NutritionService,
        mock_recipe_repo: AsyncMock,
        mock_usda_client: AsyncMock,
    ) -> None:
        recipe = Recipe(
            id="r1",
            title="Test",
            servings=4,
            ingredients=[Ingredient(name="item", quantity=1.0, unit="unit")],
        )
        mock_recipe_repo.get.return_value = recipe
        mock_usda_client.search_foods.return_value = [
            FoodItem(
                food_name="item",
                nutrients=NutrientInfo(calories=400.0, protein_g=40.0),
                source="usda",
            ),
        ]

        report = await nutrition_service.analyze_recipe("r1")
        assert report.per_serving.calories == pytest.approx(100.0)
        assert report.per_serving.protein_g == pytest.approx(10.0)
