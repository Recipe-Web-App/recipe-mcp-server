"""Tests for MealPlanService."""

from __future__ import annotations

from unittest.mock import AsyncMock

from recipe_mcp_server.models.common import MealType
from recipe_mcp_server.models.meal_plan import MealPlan
from recipe_mcp_server.services.meal_plan_service import MealPlanService


class TestGenerate:
    """Meal plan generation from Spoonacular."""

    async def test_generates_day_plan(
        self,
        meal_plan_service: MealPlanService,
        mock_spoonacular_client: AsyncMock,
        mock_meal_plan_repo: AsyncMock,
    ) -> None:
        spoonacular_response = {
            "meals": [
                {"id": 1, "title": "Breakfast Bowl", "readyInMinutes": 10},
                {"id": 2, "title": "Lunch Salad", "readyInMinutes": 15},
                {"id": 3, "title": "Dinner Pasta", "readyInMinutes": 30},
            ],
            "nutrients": {"calories": 2000, "protein": 80},
        }
        mock_spoonacular_client.generate_meal_plan.return_value = spoonacular_response
        mock_meal_plan_repo.create.side_effect = lambda plan: plan

        result = await meal_plan_service.generate(
            user_id="u1",
            name="My Plan",
            time_frame="day",
        )

        assert result.user_id == "u1"
        assert result.name == "My Plan"
        assert len(result.days) == 1
        assert len(result.days[0].meals) == 3
        assert result.days[0].meals[0].meal_type == MealType.BREAKFAST
        assert result.days[0].meals[1].meal_type == MealType.LUNCH
        assert result.days[0].meals[2].meal_type == MealType.DINNER
        # recipe_id set when Spoonacular provides an id
        assert result.days[0].meals[0].recipe_id == "1"
        assert result.days[0].meals[0].custom_meal is None

    async def test_meal_without_id_uses_custom_meal(
        self,
        meal_plan_service: MealPlanService,
        mock_spoonacular_client: AsyncMock,
        mock_meal_plan_repo: AsyncMock,
    ) -> None:
        spoonacular_response = {
            "meals": [
                {"title": "Leftovers"},
            ],
            "nutrients": {},
        }
        mock_spoonacular_client.generate_meal_plan.return_value = spoonacular_response
        mock_meal_plan_repo.create.side_effect = lambda plan: plan

        result = await meal_plan_service.generate(
            user_id="u1",
            name="Custom Plan",
            time_frame="day",
        )

        meal = result.days[0].meals[0]
        assert meal.recipe_id is None
        assert meal.custom_meal == "Leftovers"

    async def test_generates_week_plan(
        self,
        meal_plan_service: MealPlanService,
        mock_spoonacular_client: AsyncMock,
        mock_meal_plan_repo: AsyncMock,
    ) -> None:
        week_data = {}
        for day_name in [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]:
            week_data[day_name] = {
                "meals": [
                    {"id": 1, "title": f"{day_name} Breakfast"},
                    {"id": 2, "title": f"{day_name} Lunch"},
                    {"id": 3, "title": f"{day_name} Dinner"},
                ],
            }

        mock_spoonacular_client.generate_meal_plan.return_value = {"week": week_data}
        mock_meal_plan_repo.create.side_effect = lambda plan: plan

        result = await meal_plan_service.generate(
            user_id="u1",
            name="Weekly Plan",
            time_frame="week",
        )

        assert len(result.days) == 7
        for day in result.days:
            assert len(day.meals) == 3

    async def test_passes_params_to_spoonacular(
        self,
        meal_plan_service: MealPlanService,
        mock_spoonacular_client: AsyncMock,
        mock_meal_plan_repo: AsyncMock,
    ) -> None:
        mock_spoonacular_client.generate_meal_plan.return_value = {"meals": []}
        mock_meal_plan_repo.create.side_effect = lambda plan: plan

        await meal_plan_service.generate(
            user_id="u1",
            name="Diet Plan",
            time_frame="day",
            target_calories=1500,
            diet="vegetarian",
        )

        mock_spoonacular_client.generate_meal_plan.assert_called_once_with(
            time_frame="day",
            target_calories=1500,
            diet="vegetarian",
        )


class TestGetAndList:
    """Get and list delegate to MealPlanRepo."""

    async def test_get_delegates(
        self,
        meal_plan_service: MealPlanService,
        mock_meal_plan_repo: AsyncMock,
    ) -> None:
        expected = MealPlan(name="Test", start_date="2026-01-01", end_date="2026-01-07")
        mock_meal_plan_repo.get.return_value = expected

        result = await meal_plan_service.get("plan1")
        assert result is expected
        mock_meal_plan_repo.get.assert_called_once_with("plan1")

    async def test_list_for_user_delegates(
        self,
        meal_plan_service: MealPlanService,
        mock_meal_plan_repo: AsyncMock,
    ) -> None:
        plans = [MealPlan(name="P1", start_date="2026-01-01", end_date="2026-01-07")]
        mock_meal_plan_repo.list_for_user.return_value = plans

        result = await meal_plan_service.list_for_user("u1")
        assert len(result) == 1
        mock_meal_plan_repo.list_for_user.assert_called_once_with("u1")
