"""Tests for RecipeService."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.models.common import APISource
from recipe_mcp_server.models.recipe import (
    Ingredient,
    Recipe,
    RecipeCreate,
    RecipeSummary,
    RecipeUpdate,
)
from recipe_mcp_server.models.user import Favorite
from recipe_mcp_server.services.recipe_service import RecipeService


class TestCRUD:
    """CRUD operations delegate to RecipeRepo."""

    async def test_create_delegates(
        self,
        recipe_service: RecipeService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        data = RecipeCreate(title="Test")
        expected = Recipe(title="Test")
        mock_recipe_repo.create.return_value = expected

        result = await recipe_service.create(data)
        assert result.title == "Test"
        mock_recipe_repo.create.assert_called_once_with(data)

    async def test_get_returns_recipe(
        self,
        recipe_service: RecipeService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        mock_recipe_repo.get.return_value = Recipe(id="abc", title="Test")
        result = await recipe_service.get("abc")
        assert result.id == "abc"

    async def test_get_raises_not_found(
        self,
        recipe_service: RecipeService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        mock_recipe_repo.get.return_value = None
        with pytest.raises(NotFoundError, match="not found"):
            await recipe_service.get("missing")

    async def test_update_returns_recipe(
        self,
        recipe_service: RecipeService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        updated = Recipe(id="abc", title="Updated")
        mock_recipe_repo.update.return_value = updated

        result = await recipe_service.update("abc", RecipeUpdate(title="Updated"))
        assert result.title == "Updated"

    async def test_update_raises_not_found(
        self,
        recipe_service: RecipeService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        mock_recipe_repo.update.return_value = None
        with pytest.raises(NotFoundError):
            await recipe_service.update("missing", RecipeUpdate(title="X"))

    async def test_delete_delegates(
        self,
        recipe_service: RecipeService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        mock_recipe_repo.delete.return_value = True
        result = await recipe_service.delete("abc")
        assert result is True


class TestSearch:
    """Multi-API search with deduplication and fallback."""

    async def test_merges_results_from_all_apis(
        self,
        recipe_service: RecipeService,
        mock_mealdb_client: AsyncMock,
        mock_spoonacular_client: AsyncMock,
        mock_dummyjson_client: AsyncMock,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        mock_mealdb_client.search_by_name.return_value = [
            Recipe(title="MealDB Chicken", source_id="m1", source_api=APISource.THEMEALDB),
        ]
        mock_spoonacular_client.search_recipes.return_value = [
            RecipeSummary(id="s1", title="Spoon Chicken", source_api=APISource.SPOONACULAR),
        ]
        mock_dummyjson_client.search_recipes.return_value = [
            Recipe(title="Dummy Chicken", source_id="d1", source_api=APISource.DUMMYJSON),
        ]
        mock_recipe_repo.search.return_value = []

        results = await recipe_service.search("chicken")
        assert len(results) == 3
        titles = {r.title for r in results}
        assert "MealDB Chicken" in titles
        assert "Spoon Chicken" in titles
        assert "Dummy Chicken" in titles

    async def test_deduplicates_by_title(
        self,
        recipe_service: RecipeService,
        mock_mealdb_client: AsyncMock,
        mock_spoonacular_client: AsyncMock,
        mock_dummyjson_client: AsyncMock,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        mock_mealdb_client.search_by_name.return_value = [
            Recipe(title="Chicken Soup", source_id="m1"),
        ]
        mock_spoonacular_client.search_recipes.return_value = [
            RecipeSummary(id="s1", title="chicken soup"),
        ]
        mock_dummyjson_client.search_recipes.return_value = []
        mock_recipe_repo.search.return_value = []

        results = await recipe_service.search("chicken soup")
        assert len(results) == 1

    async def test_handles_api_failure_gracefully(
        self,
        recipe_service: RecipeService,
        mock_mealdb_client: AsyncMock,
        mock_spoonacular_client: AsyncMock,
        mock_dummyjson_client: AsyncMock,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        mock_mealdb_client.search_by_name.side_effect = ExternalAPIError(
            "timeout",
            api_name="TheMealDB",
        )
        mock_spoonacular_client.search_recipes.return_value = [
            RecipeSummary(id="s1", title="Pasta"),
        ]
        mock_dummyjson_client.search_recipes.return_value = []
        mock_recipe_repo.search.return_value = []

        results = await recipe_service.search("pasta")
        assert len(results) == 1
        assert results[0].title == "Pasta"

    async def test_all_apis_fail_returns_local(
        self,
        recipe_service: RecipeService,
        mock_mealdb_client: AsyncMock,
        mock_spoonacular_client: AsyncMock,
        mock_dummyjson_client: AsyncMock,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        mock_mealdb_client.search_by_name.side_effect = ExternalAPIError("fail")
        mock_spoonacular_client.search_recipes.side_effect = ExternalAPIError("fail")
        mock_dummyjson_client.search_recipes.side_effect = ExternalAPIError("fail")
        mock_recipe_repo.search.return_value = [
            RecipeSummary(id="local1", title="Local Recipe"),
        ]

        results = await recipe_service.search("anything")
        assert len(results) == 1
        assert results[0].id == "local1"

    async def test_respects_limit(
        self,
        recipe_service: RecipeService,
        mock_mealdb_client: AsyncMock,
        mock_spoonacular_client: AsyncMock,
        mock_dummyjson_client: AsyncMock,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        mock_mealdb_client.search_by_name.return_value = [
            Recipe(title=f"Recipe {i}", source_id=f"m{i}") for i in range(5)
        ]
        mock_spoonacular_client.search_recipes.return_value = []
        mock_dummyjson_client.search_recipes.return_value = []
        mock_recipe_repo.search.return_value = []

        results = await recipe_service.search("recipe", limit=3)
        assert len(results) == 3


class TestScaling:
    """Recipe ingredient scaling."""

    async def test_doubles_quantities(
        self,
        recipe_service: RecipeService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        recipe = Recipe(
            id="r1",
            title="Test",
            servings=4,
            ingredients=[
                Ingredient(name="flour", quantity=2.0, unit="cups"),
                Ingredient(name="sugar", quantity=1.0, unit="cup"),
            ],
        )
        mock_recipe_repo.get.return_value = recipe

        scaled = await recipe_service.scale_recipe("r1", 8)
        assert len(scaled) == 2
        assert scaled[0].quantity == pytest.approx(4.0)
        assert scaled[0].original_quantity == pytest.approx(2.0)
        assert scaled[0].scale_factor == pytest.approx(2.0)
        assert scaled[1].quantity == pytest.approx(2.0)

    async def test_handles_none_quantities(
        self,
        recipe_service: RecipeService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        recipe = Recipe(
            id="r1",
            title="Test",
            servings=2,
            ingredients=[
                Ingredient(name="salt", quantity=None, unit=None, notes="to taste"),
            ],
        )
        mock_recipe_repo.get.return_value = recipe

        scaled = await recipe_service.scale_recipe("r1", 4)
        assert scaled[0].quantity is None
        assert scaled[0].original_quantity is None

    async def test_halves_quantities(
        self,
        recipe_service: RecipeService,
        mock_recipe_repo: AsyncMock,
    ) -> None:
        recipe = Recipe(
            id="r1",
            title="Test",
            servings=4,
            ingredients=[
                Ingredient(name="butter", quantity=200.0, unit="g"),
            ],
        )
        mock_recipe_repo.get.return_value = recipe

        scaled = await recipe_service.scale_recipe("r1", 2)
        assert scaled[0].quantity == pytest.approx(100.0)


class TestSubstitutes:
    """Ingredient substitution with fallback."""

    async def test_from_spoonacular(
        self,
        recipe_service: RecipeService,
        mock_spoonacular_client: AsyncMock,
    ) -> None:
        mock_spoonacular_client.get_substitutes.return_value = ["margarine", "ghee"]
        result = await recipe_service.get_substitutes("butter")
        assert result == ["margarine", "ghee"]

    async def test_fallback_to_builtin(
        self,
        recipe_service: RecipeService,
        mock_spoonacular_client: AsyncMock,
    ) -> None:
        mock_spoonacular_client.get_substitutes.side_effect = ExternalAPIError("fail")
        result = await recipe_service.get_substitutes("butter")
        assert "margarine" in result

    async def test_no_substitutes_returns_empty(
        self,
        recipe_service: RecipeService,
        mock_spoonacular_client: AsyncMock,
    ) -> None:
        mock_spoonacular_client.get_substitutes.side_effect = ExternalAPIError("fail")
        result = await recipe_service.get_substitutes("unobtainium")
        assert result == []


class TestRandomRecipe:
    """Random recipe with Foodish image."""

    async def test_with_foodish_image(
        self,
        recipe_service: RecipeService,
        mock_mealdb_client: AsyncMock,
        mock_foodish_client: AsyncMock,
    ) -> None:
        mock_mealdb_client.random_meal.return_value = Recipe(title="Random", image_url="old.jpg")
        mock_foodish_client.random_image.return_value = "https://foodish.example/img.jpg"

        result = await recipe_service.random_recipe()
        assert result.image_url == "https://foodish.example/img.jpg"

    async def test_foodish_failure_uses_recipe_image(
        self,
        recipe_service: RecipeService,
        mock_mealdb_client: AsyncMock,
        mock_foodish_client: AsyncMock,
    ) -> None:
        mock_mealdb_client.random_meal.return_value = Recipe(
            title="Random",
            image_url="original.jpg",
        )
        mock_foodish_client.random_image.side_effect = ExternalAPIError("fail")

        result = await recipe_service.random_recipe()
        assert result.image_url == "original.jpg"

    async def test_no_random_meal_raises(
        self,
        recipe_service: RecipeService,
        mock_mealdb_client: AsyncMock,
    ) -> None:
        mock_mealdb_client.random_meal.return_value = None
        with pytest.raises(NotFoundError):
            await recipe_service.random_recipe()


class TestFavorites:
    """Favorite operations delegate to FavoriteRepo."""

    async def test_save_favorite(
        self,
        recipe_service: RecipeService,
        mock_favorite_repo: AsyncMock,
    ) -> None:
        expected = Favorite(user_id="u1", recipe_id="r1", rating=5)
        mock_favorite_repo.save.return_value = expected

        result = await recipe_service.save_favorite("u1", "r1", rating=5)
        assert result.rating == 5
        mock_favorite_repo.save.assert_called_once()

    async def test_list_favorites(
        self,
        recipe_service: RecipeService,
        mock_favorite_repo: AsyncMock,
    ) -> None:
        mock_favorite_repo.list_for_user.return_value = [
            Favorite(user_id="u1", recipe_id="r1"),
        ]
        result = await recipe_service.list_favorites("u1")
        assert len(result) == 1

    async def test_remove_favorite(
        self,
        recipe_service: RecipeService,
        mock_favorite_repo: AsyncMock,
    ) -> None:
        mock_favorite_repo.remove.return_value = True
        result = await recipe_service.remove_favorite("u1", "r1")
        assert result is True
