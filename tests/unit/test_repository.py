"""Unit tests for repository CRUD operations using in-memory SQLite."""

from __future__ import annotations

import pytest

from recipe_mcp_server.db.repository import (
    AuditRepo,
    FavoriteRepo,
    MealPlanRepo,
    RecipeRepo,
    UserRepo,
)
from recipe_mcp_server.models import (
    DayPlan,
    DietaryProfile,
    Ingredient,
    MealPlan,
    MealPlanItem,
    MealType,
    RecipeCreate,
    RecipeUpdate,
)

pytestmark = pytest.mark.unit


class TestRecipeRepo:
    async def test_create_and_get(self, recipe_repo: RecipeRepo) -> None:
        data = RecipeCreate(
            title="Pasta Carbonara",
            instructions=["Boil pasta", "Mix eggs"],
            category="Pasta",
            area="Italian",
            tags=["pasta", "quick"],
            ingredients=[
                Ingredient(name="Spaghetti", quantity=500, unit="g"),
                Ingredient(name="Eggs", quantity=3),
            ],
        )
        recipe = await recipe_repo.create(data)

        assert recipe.id is not None
        assert recipe.title == "Pasta Carbonara"
        assert recipe.instructions == ["Boil pasta", "Mix eggs"]
        assert recipe.tags == ["pasta", "quick"]
        assert len(recipe.ingredients) == 2
        assert recipe.ingredients[0].name == "Spaghetti"

        fetched = await recipe_repo.get(recipe.id)
        assert fetched is not None
        assert fetched.title == recipe.title
        assert len(fetched.ingredients) == 2

    async def test_get_nonexistent(self, recipe_repo: RecipeRepo) -> None:
        result = await recipe_repo.get("nonexistent")
        assert result is None

    async def test_update(self, recipe_repo: RecipeRepo) -> None:
        data = RecipeCreate(title="Old Title", servings=4)
        recipe = await recipe_repo.create(data)
        assert recipe.id is not None

        updated = await recipe_repo.update(
            recipe.id,
            RecipeUpdate(title="New Title", servings=6),
        )
        assert updated is not None
        assert updated.title == "New Title"
        assert updated.servings == 6

    async def test_update_nonexistent(self, recipe_repo: RecipeRepo) -> None:
        result = await recipe_repo.update("nonexistent", RecipeUpdate(title="X"))
        assert result is None

    async def test_soft_delete(self, recipe_repo: RecipeRepo) -> None:
        data = RecipeCreate(title="To Delete")
        recipe = await recipe_repo.create(data)
        assert recipe.id is not None

        deleted = await recipe_repo.delete(recipe.id)
        assert deleted is True

        # Should not be found via get
        fetched = await recipe_repo.get(recipe.id)
        assert fetched is None

    async def test_delete_nonexistent(self, recipe_repo: RecipeRepo) -> None:
        result = await recipe_repo.delete("nonexistent")
        assert result is False

    async def test_soft_deleted_not_in_list(self, recipe_repo: RecipeRepo) -> None:
        await recipe_repo.create(RecipeCreate(title="Keep"))
        r2 = await recipe_repo.create(RecipeCreate(title="Delete"))
        assert r2.id is not None
        await recipe_repo.delete(r2.id)

        page = await recipe_repo.list_recipes()
        titles = [item.title for item in page.items]
        assert "Keep" in titles
        assert "Delete" not in titles

    async def test_list_pagination(self, recipe_repo: RecipeRepo) -> None:
        for i in range(5):
            await recipe_repo.create(RecipeCreate(title=f"Recipe {i}"))

        page1 = await recipe_repo.list_recipes(limit=3)
        assert len(page1.items) == 3
        assert page1.total == 5
        assert page1.next_cursor is not None

    async def test_list_invalid_limit(self, recipe_repo: RecipeRepo) -> None:
        with pytest.raises(ValueError, match="limit must be >= 1"):
            await recipe_repo.list_recipes(limit=0)

    async def test_search(self, recipe_repo: RecipeRepo) -> None:
        await recipe_repo.create(RecipeCreate(title="Chicken Pasta", area="Italian"))
        await recipe_repo.create(RecipeCreate(title="Beef Stew", area="British"))
        await recipe_repo.create(RecipeCreate(title="Pasta Salad", area="Italian"))

        results = await recipe_repo.search("pasta")
        assert len(results) == 2

    async def test_search_with_cuisine(self, recipe_repo: RecipeRepo) -> None:
        await recipe_repo.create(RecipeCreate(title="Pasta", area="Italian"))
        await recipe_repo.create(RecipeCreate(title="Pasta", area="Japanese"))

        results = await recipe_repo.search("pasta", cuisine="Italian")
        assert len(results) == 1
        assert results[0].area == "Italian"

    async def test_json_roundtrip(self, recipe_repo: RecipeRepo) -> None:
        data = RecipeCreate(
            title="JSON Test",
            instructions=["Step 1", "Step 2"],
            tags=["tag1", "tag2"],
        )
        recipe = await recipe_repo.create(data)
        assert recipe.id is not None
        fetched = await recipe_repo.get(recipe.id)

        assert fetched is not None
        assert fetched.instructions == ["Step 1", "Step 2"]
        assert fetched.tags == ["tag1", "tag2"]


class TestUserRepo:
    async def test_get_or_create_new(self, user_repo: UserRepo) -> None:
        prefs = await user_repo.get_or_create("user1")
        assert prefs.user_id == "user1"
        assert prefs.default_servings == 4
        assert prefs.unit_system == "metric"

    async def test_get_or_create_existing(self, user_repo: UserRepo) -> None:
        await user_repo.get_or_create("user1")
        prefs = await user_repo.get_or_create("user1")
        assert prefs.user_id == "user1"

    async def test_update(self, user_repo: UserRepo) -> None:
        await user_repo.get_or_create("user1")
        updated = await user_repo.update("user1", {"display_name": "Test User"})
        assert updated is not None
        assert updated.display_name == "Test User"

    async def test_update_dietary_profile(self, user_repo: UserRepo) -> None:
        await user_repo.get_or_create("user1")
        profile = DietaryProfile(
            dietary_restrictions=["vegetarian"],
            allergies=["peanuts"],
            preferred_cuisines=["Italian"],
        )
        updated = await user_repo.update("user1", {"dietary_profile": profile})
        assert updated is not None
        assert updated.dietary_profile.dietary_restrictions == ["vegetarian"]
        assert updated.dietary_profile.allergies == ["peanuts"]

    async def test_update_nonexistent(self, user_repo: UserRepo) -> None:
        result = await user_repo.update("nonexistent", {"display_name": "X"})
        assert result is None

    async def test_update_unknown_field_raises(self, user_repo: UserRepo) -> None:
        await user_repo.get_or_create("user1")
        with pytest.raises(ValueError, match="Unknown user profile field"):
            await user_repo.update("user1", {"nonexistent_field": "value"})

    async def test_update_calorie_target(self, user_repo: UserRepo) -> None:
        await user_repo.get_or_create("user1")
        profile = DietaryProfile(calorie_target=2000)
        updated = await user_repo.update("user1", {"dietary_profile": profile})
        assert updated is not None
        assert updated.dietary_profile.calorie_target == 2000

        fetched = await user_repo.get_or_create("user1")
        assert fetched.dietary_profile.calorie_target == 2000


class TestFavoriteRepo:
    async def test_save_and_list(
        self, favorite_repo: FavoriteRepo, recipe_repo: RecipeRepo
    ) -> None:
        recipe = await recipe_repo.create(RecipeCreate(title="Fav Recipe"))
        assert recipe.id is not None

        fav = await favorite_repo.save("user1", recipe.id, rating=5, notes="Great!")
        assert fav.user_id == "user1"
        assert fav.rating == 5

        favs = await favorite_repo.list_for_user("user1")
        assert len(favs) == 1
        assert favs[0].notes == "Great!"

    async def test_upsert(self, favorite_repo: FavoriteRepo, recipe_repo: RecipeRepo) -> None:
        recipe = await recipe_repo.create(RecipeCreate(title="Fav"))
        assert recipe.id is not None

        await favorite_repo.save("user1", recipe.id, rating=3)
        updated = await favorite_repo.save("user1", recipe.id, rating=5)
        assert updated.rating == 5

        favs = await favorite_repo.list_for_user("user1")
        assert len(favs) == 1

    async def test_remove(self, favorite_repo: FavoriteRepo, recipe_repo: RecipeRepo) -> None:
        recipe = await recipe_repo.create(RecipeCreate(title="Fav"))
        assert recipe.id is not None
        await favorite_repo.save("user1", recipe.id)

        removed = await favorite_repo.remove("user1", recipe.id)
        assert removed is True

        favs = await favorite_repo.list_for_user("user1")
        assert len(favs) == 0

    async def test_remove_nonexistent(self, favorite_repo: FavoriteRepo) -> None:
        result = await favorite_repo.remove("user1", "nonexistent")
        assert result is False


class TestMealPlanRepo:
    async def test_create_and_get(self, meal_plan_repo: MealPlanRepo) -> None:
        plan = MealPlan(
            name="Week 1",
            user_id="user1",
            start_date="2026-03-19",
            end_date="2026-03-25",
            days=[
                DayPlan(
                    date="2026-03-19",
                    meals=[
                        MealPlanItem(
                            day_date="2026-03-19",
                            meal_type=MealType.BREAKFAST,
                            custom_meal="Oatmeal",
                        ),
                        MealPlanItem(
                            day_date="2026-03-19",
                            meal_type=MealType.LUNCH,
                            custom_meal="Salad",
                        ),
                    ],
                )
            ],
        )
        created = await meal_plan_repo.create(plan)
        assert created.id is not None
        assert created.name == "Week 1"
        assert len(created.days) == 1
        assert len(created.days[0].meals) == 2

        assert created.id is not None
        fetched = await meal_plan_repo.get(created.id)
        assert fetched is not None
        assert fetched.name == "Week 1"
        assert len(fetched.days) == 1

    async def test_get_nonexistent(self, meal_plan_repo: MealPlanRepo) -> None:
        result = await meal_plan_repo.get("nonexistent")
        assert result is None

    async def test_list_for_user(self, meal_plan_repo: MealPlanRepo) -> None:
        for i in range(3):
            plan = MealPlan(
                name=f"Plan {i}",
                user_id="user1",
                start_date="2026-03-19",
                end_date="2026-03-25",
            )
            await meal_plan_repo.create(plan)

        plans = await meal_plan_repo.list_for_user("user1")
        assert len(plans) == 3

    async def test_list_for_user_empty(self, meal_plan_repo: MealPlanRepo) -> None:
        plans = await meal_plan_repo.list_for_user("nobody")
        assert plans == []

    async def test_empty_day_preserved(self, meal_plan_repo: MealPlanRepo) -> None:
        plan = MealPlan(
            name="Empty Day Test",
            user_id="user1",
            start_date="2026-03-19",
            end_date="2026-03-20",
            days=[
                DayPlan(date="2026-03-19", meals=[]),
                DayPlan(
                    date="2026-03-20",
                    meals=[
                        MealPlanItem(
                            day_date="2026-03-20",
                            meal_type=MealType.LUNCH,
                            custom_meal="Sandwich",
                        )
                    ],
                ),
            ],
        )
        created = await meal_plan_repo.create(plan)
        assert created.id is not None
        fetched = await meal_plan_repo.get(created.id)
        assert fetched is not None
        assert len(fetched.days) == 2
        dates = [d.date for d in fetched.days]
        assert "2026-03-19" in dates
        empty_day = next(d for d in fetched.days if d.date == "2026-03-19")
        assert empty_day.meals == []


class TestAuditRepo:
    async def test_log_entry(self, audit_repo: AuditRepo) -> None:
        await audit_repo.log(
            action="create_recipe",
            entity_type="recipe",
            entity_id="abc123",
            after_state={"title": "New Recipe"},
            tool_name="create_recipe",
            request_id="req-001",
            user_id="user1",
        )
        # Audit repo is append-only, so we just verify no exception was raised

    async def test_log_with_before_after(self, audit_repo: AuditRepo) -> None:
        await audit_repo.log(
            action="update_recipe",
            entity_type="recipe",
            entity_id="abc123",
            before_state={"title": "Old"},
            after_state={"title": "New"},
        )

    async def test_log_minimal(self, audit_repo: AuditRepo) -> None:
        await audit_repo.log(
            action="search_recipes",
            entity_type="recipe",
        )
