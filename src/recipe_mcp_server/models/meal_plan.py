"""Meal plan domain models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from recipe_mcp_server.models.common import MealType


class MealPlanItem(BaseModel):
    """A single meal slot within a meal plan."""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    day_date: str
    meal_type: MealType
    recipe_id: str | None = None
    custom_meal: str | None = None
    servings: int = 1


class DayPlan(BaseModel):
    """All meals for a single day."""

    date: str
    meals: list[MealPlanItem] = []


class MealPlan(BaseModel):
    """A complete meal plan spanning multiple days."""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    user_id: str | None = None
    name: str
    start_date: str
    end_date: str
    preferences: dict[str, Any] | None = None
    days: list[DayPlan] = []
    created_at: datetime | None = None


class WeekPlan(MealPlan):
    """A 7-day meal plan."""


class ShoppingItem(BaseModel):
    """A single item on a shopping list."""

    ingredient: str
    quantity: float | None = None
    unit: str | None = None
    recipes: list[str] = []
    category: str | None = None
