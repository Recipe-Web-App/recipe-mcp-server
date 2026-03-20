"""Nutrition domain models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NutrientInfo(BaseModel):
    """Nutritional information for a food item."""

    model_config = ConfigDict(from_attributes=True)

    calories: float = 0.0
    protein_g: float = 0.0
    fat_g: float = 0.0
    carbs_g: float = 0.0
    fiber_g: float = 0.0
    sugar_g: float = 0.0
    sodium_mg: float = 0.0
    full_nutrients: dict[str, float] | None = None


class FoodItem(BaseModel):
    """A food item with nutrition data from an external source."""

    model_config = ConfigDict(from_attributes=True)

    food_name: str
    fdc_id: str | None = None
    nutrients: NutrientInfo
    source: str
    fetched_at: datetime | None = None


class IngredientNutrition(BaseModel):
    """Nutrition breakdown for a single ingredient in a recipe."""

    ingredient_name: str
    quantity: float | None = None
    unit: str | None = None
    nutrients: NutrientInfo


class NutritionReport(BaseModel):
    """Complete nutrition analysis for a recipe."""

    per_serving: NutrientInfo
    total: NutrientInfo
    ingredients: list[IngredientNutrition]
    servings: int
