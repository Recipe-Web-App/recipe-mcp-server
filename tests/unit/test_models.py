"""Unit tests for Pydantic domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from recipe_mcp_server.models.common import APISource, Difficulty, MealType, PaginatedResponse
from recipe_mcp_server.models.meal_plan import DayPlan, MealPlan, MealPlanItem, ShoppingItem
from recipe_mcp_server.models.nutrition import FoodItem, NutrientInfo, NutritionReport
from recipe_mcp_server.models.recipe import (
    Ingredient,
    Recipe,
    RecipeCreate,
    RecipeSummary,
    RecipeUpdate,
    ScaledIngredient,
)
from recipe_mcp_server.models.user import DietaryProfile, Favorite, UserPreferences

pytestmark = pytest.mark.unit


class TestEnums:
    def test_api_source_values(self) -> None:
        assert APISource.THEMEALDB == "themealdb"
        assert APISource.SPOONACULAR == "spoonacular"
        assert APISource.DUMMYJSON == "dummyjson"
        assert APISource.LOCAL == "local"
        assert APISource.OPENFOODFACTS == "openfoodfacts"

    def test_difficulty_values(self) -> None:
        assert Difficulty.EASY == "easy"
        assert Difficulty.MEDIUM == "medium"
        assert Difficulty.HARD == "hard"

    def test_meal_type_values(self) -> None:
        assert MealType.BREAKFAST == "breakfast"
        assert MealType.LUNCH == "lunch"
        assert MealType.DINNER == "dinner"
        assert MealType.SNACK == "snack"


class TestIngredient:
    def test_minimal_ingredient(self) -> None:
        ing = Ingredient(name="Salt")
        assert ing.name == "Salt"
        assert ing.quantity is None
        assert ing.unit is None
        assert ing.notes is None
        assert ing.order_index == 0

    def test_full_ingredient(self) -> None:
        ing = Ingredient(name="Flour", quantity=2.5, unit="cup", notes="sifted", order_index=1)
        assert ing.quantity == 2.5
        assert ing.unit == "cup"
        assert ing.notes == "sifted"
        assert ing.order_index == 1


class TestScaledIngredient:
    def test_scaled_ingredient(self) -> None:
        ing = ScaledIngredient(name="Flour", quantity=5.0, original_quantity=2.5, scale_factor=2.0)
        assert ing.quantity == 5.0
        assert ing.original_quantity == 2.5
        assert ing.scale_factor == 2.0


class TestRecipe:
    def test_recipe_with_defaults(self) -> None:
        recipe = Recipe(title="Test Recipe")
        assert recipe.title == "Test Recipe"
        assert recipe.servings == 4
        assert recipe.is_deleted is False
        assert recipe.ingredients == []
        assert recipe.instructions == []
        assert recipe.tags == []

    def test_recipe_with_all_fields(self) -> None:
        recipe = Recipe(
            id="abc123",
            title="Pasta Carbonara",
            description="Classic Italian pasta",
            instructions=["Boil pasta", "Fry pancetta", "Mix eggs and cheese"],
            category="Pasta",
            area="Italian",
            source_api=APISource.THEMEALDB,
            servings=2,
            difficulty=Difficulty.MEDIUM,
            tags=["pasta", "italian", "quick"],
            ingredients=[Ingredient(name="Spaghetti", quantity=500, unit="g")],
        )
        assert recipe.source_api == APISource.THEMEALDB
        assert recipe.difficulty == Difficulty.MEDIUM
        assert len(recipe.ingredients) == 1
        assert len(recipe.instructions) == 3

    def test_recipe_invalid_difficulty(self) -> None:
        with pytest.raises(ValidationError):
            Recipe(title="Test", difficulty="impossible")  # type: ignore[arg-type]


class TestRecipeCreate:
    def test_minimal_create(self) -> None:
        data = RecipeCreate(title="New Recipe")
        assert data.title == "New Recipe"
        assert data.servings == 4
        assert data.ingredients == []

    def test_create_with_ingredients(self) -> None:
        data = RecipeCreate(
            title="Salad",
            ingredients=[
                Ingredient(name="Lettuce", quantity=1, unit="head"),
                Ingredient(name="Tomato", quantity=2),
            ],
        )
        assert len(data.ingredients) == 2


class TestRecipeUpdate:
    def test_all_none_is_valid(self) -> None:
        update = RecipeUpdate()
        dumped = update.model_dump(exclude_unset=True)
        assert dumped == {}

    def test_partial_update(self) -> None:
        update = RecipeUpdate(title="Updated Title", servings=6)
        dumped = update.model_dump(exclude_unset=True)
        assert dumped == {"title": "Updated Title", "servings": 6}


class TestRecipeSummary:
    def test_summary(self) -> None:
        summary = RecipeSummary(id="abc", title="Pasta")
        assert summary.id == "abc"
        assert summary.category is None


class TestNutrition:
    def test_nutrient_info_defaults(self) -> None:
        info = NutrientInfo()
        assert info.calories == 0.0
        assert info.protein_g == 0.0

    def test_food_item(self) -> None:
        item = FoodItem(
            food_name="Chicken Breast",
            nutrients=NutrientInfo(calories=165, protein_g=31),
            source="usda",
        )
        assert item.food_name == "Chicken Breast"
        assert item.nutrients.calories == 165

    def test_nutrition_report(self) -> None:
        report = NutritionReport(
            per_serving=NutrientInfo(calories=500),
            total=NutrientInfo(calories=2000),
            ingredients=[],
            servings=4,
        )
        assert report.servings == 4


class TestMealPlan:
    def test_meal_plan_item(self) -> None:
        item = MealPlanItem(day_date="2026-03-19", meal_type=MealType.LUNCH)
        assert item.servings == 1
        assert item.recipe_id is None

    def test_meal_plan_invalid_meal_type(self) -> None:
        with pytest.raises(ValidationError):
            MealPlanItem(day_date="2026-03-19", meal_type="brunch")  # type: ignore[arg-type]

    def test_day_plan(self) -> None:
        day = DayPlan(
            date="2026-03-19",
            meals=[MealPlanItem(day_date="2026-03-19", meal_type=MealType.BREAKFAST)],
        )
        assert len(day.meals) == 1

    def test_meal_plan(self) -> None:
        plan = MealPlan(name="Week 1", start_date="2026-03-19", end_date="2026-03-25")
        assert plan.days == []

    def test_shopping_item(self) -> None:
        item = ShoppingItem(ingredient="Milk", quantity=2, unit="L", recipes=["r1", "r2"])
        assert len(item.recipes) == 2


class TestUser:
    def test_dietary_profile_defaults(self) -> None:
        profile = DietaryProfile()
        assert profile.dietary_restrictions == []
        assert profile.allergies == []
        assert profile.preferred_cuisines == []
        assert profile.calorie_target is None

    def test_user_preferences(self) -> None:
        prefs = UserPreferences(user_id="user1")
        assert prefs.default_servings == 4
        assert prefs.unit_system == "metric"

    def test_favorite_valid_rating(self) -> None:
        fav = Favorite(user_id="u1", recipe_id="r1", rating=5)
        assert fav.rating == 5

    def test_favorite_rating_too_low(self) -> None:
        with pytest.raises(ValidationError):
            Favorite(user_id="u1", recipe_id="r1", rating=0)

    def test_favorite_rating_too_high(self) -> None:
        with pytest.raises(ValidationError):
            Favorite(user_id="u1", recipe_id="r1", rating=6)

    def test_favorite_no_rating(self) -> None:
        fav = Favorite(user_id="u1", recipe_id="r1")
        assert fav.rating is None


class TestPaginatedResponse:
    def test_generic_response(self) -> None:
        resp = PaginatedResponse[str](items=["a", "b"], total=2)
        assert resp.items == ["a", "b"]
        assert resp.next_cursor is None

    def test_with_cursor(self) -> None:
        resp = PaginatedResponse[int](items=[1, 2, 3], total=10, next_cursor="abc")
        assert resp.next_cursor == "abc"
