"""Fixtures for service unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from recipe_mcp_server.services.conversion_service import ConversionService
from recipe_mcp_server.services.meal_plan_service import MealPlanService
from recipe_mcp_server.services.nutrition_service import NutritionService
from recipe_mcp_server.services.recipe_service import RecipeService
from recipe_mcp_server.services.shopping_service import ShoppingService


@pytest.fixture
def mock_mealdb_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_spoonacular_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_dummyjson_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_foodish_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_usda_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_recipe_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_favorite_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_meal_plan_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def conversion_service(mock_spoonacular_client: AsyncMock) -> ConversionService:
    return ConversionService(spoonacular_client=mock_spoonacular_client)


@pytest.fixture
def recipe_service(
    mock_recipe_repo: AsyncMock,
    mock_favorite_repo: AsyncMock,
    mock_mealdb_client: AsyncMock,
    mock_spoonacular_client: AsyncMock,
    mock_dummyjson_client: AsyncMock,
    mock_foodish_client: AsyncMock,
) -> RecipeService:
    return RecipeService(
        recipe_repo=mock_recipe_repo,
        favorite_repo=mock_favorite_repo,
        mealdb_client=mock_mealdb_client,
        spoonacular_client=mock_spoonacular_client,
        dummyjson_client=mock_dummyjson_client,
        foodish_client=mock_foodish_client,
    )


@pytest.fixture
def nutrition_service(
    mock_usda_client: AsyncMock,
    mock_spoonacular_client: AsyncMock,
    mock_recipe_repo: AsyncMock,
) -> NutritionService:
    return NutritionService(
        usda_client=mock_usda_client,
        spoonacular_client=mock_spoonacular_client,
        recipe_repo=mock_recipe_repo,
    )


@pytest.fixture
def meal_plan_service(
    mock_spoonacular_client: AsyncMock,
    mock_meal_plan_repo: AsyncMock,
) -> MealPlanService:
    return MealPlanService(
        spoonacular_client=mock_spoonacular_client,
        meal_plan_repo=mock_meal_plan_repo,
    )


@pytest.fixture
def shopping_service(
    mock_recipe_repo: AsyncMock,
    mock_meal_plan_repo: AsyncMock,
    conversion_service: ConversionService,
) -> ShoppingService:
    return ShoppingService(
        recipe_repo=mock_recipe_repo,
        meal_plan_repo=mock_meal_plan_repo,
        conversion_service=conversion_service,
    )
