"""Meal plan service using Spoonacular integration."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import structlog

from recipe_mcp_server.clients.spoonacular import SpoonacularClient
from recipe_mcp_server.db.repository import MealPlanRepo
from recipe_mcp_server.models.common import MealType
from recipe_mcp_server.models.meal_plan import DayPlan, MealPlan, MealPlanItem

logger = structlog.get_logger(__name__)

# Spoonacular meal slot indices mapped to MealType
_SLOT_TO_MEAL_TYPE: dict[int, MealType] = {
    0: MealType.BREAKFAST,
    1: MealType.LUNCH,
    2: MealType.DINNER,
}

# Day names returned in Spoonacular week response
_WEEKDAY_ORDER: list[str] = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def _parse_day_meals(
    meals_data: list[dict[str, Any]],
    day_date: str,
) -> DayPlan:
    """Parse a list of Spoonacular meal dicts into a DayPlan."""
    items: list[MealPlanItem] = []
    for idx, meal in enumerate(meals_data):
        meal_type = _SLOT_TO_MEAL_TYPE.get(idx, MealType.SNACK)
        items.append(
            MealPlanItem(
                id=str(uuid.uuid4()),
                day_date=day_date,
                meal_type=meal_type,
                recipe_id=str(meal.get("id", "")),
                custom_meal=meal.get("title"),
                servings=1,
            ),
        )
    return DayPlan(date=day_date, meals=items)


def _parse_spoonacular_plan(
    data: dict[str, Any],
    user_id: str,
    name: str,
) -> MealPlan:
    """Convert a Spoonacular meal plan response to domain models.

    Handles both the "day" format (flat ``meals`` list) and the "week" format
    (``week`` dict with day-named keys, each containing a ``meals`` list).
    """
    today = date.today()
    days: list[DayPlan] = []

    week_data = data.get("week")
    if isinstance(week_data, dict):
        # Week format: {"week": {"monday": {"meals": [...]}, ...}}
        for offset, day_name in enumerate(_WEEKDAY_ORDER):
            day_info = week_data.get(day_name, {})
            day_meals = day_info.get("meals", [])
            day_date = (today + timedelta(days=offset)).isoformat()
            days.append(_parse_day_meals(day_meals, day_date))
    else:
        # Day format: {"meals": [...]}
        day_meals = data.get("meals", [])
        day_date = today.isoformat()
        days.append(_parse_day_meals(day_meals, day_date))

    end_date = today + timedelta(days=max(len(days) - 1, 0))

    return MealPlan(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        start_date=today.isoformat(),
        end_date=end_date.isoformat(),
        preferences=data.get("nutrients"),
        days=days,
    )


class MealPlanService:
    """Generates and manages meal plans via Spoonacular."""

    def __init__(
        self,
        *,
        spoonacular_client: SpoonacularClient,
        meal_plan_repo: MealPlanRepo,
    ) -> None:
        self._spoonacular_client = spoonacular_client
        self._meal_plan_repo = meal_plan_repo

    async def generate(
        self,
        *,
        user_id: str,
        name: str,
        time_frame: str = "week",
        target_calories: int = 2000,
        diet: str = "",
    ) -> MealPlan:
        """Generate a meal plan and persist it."""
        data = await self._spoonacular_client.generate_meal_plan(
            time_frame=time_frame,
            target_calories=target_calories,
            diet=diet,
        )

        plan = _parse_spoonacular_plan(data, user_id, name)
        return await self._meal_plan_repo.create(plan)

    async def get(self, plan_id: str) -> MealPlan | None:
        """Retrieve a meal plan by ID."""
        return await self._meal_plan_repo.get(plan_id)

    async def list_for_user(self, user_id: str) -> list[MealPlan]:
        """List all meal plans for a user."""
        return await self._meal_plan_repo.list_for_user(user_id)
