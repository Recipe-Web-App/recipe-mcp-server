"""User and preference domain models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DietaryProfile(BaseModel):
    """User's dietary restrictions and preferences."""

    dietary_restrictions: list[str] = []
    allergies: list[str] = []
    preferred_cuisines: list[str] = []
    calorie_target: int | None = None


class UserPreferences(BaseModel):
    """User profile with preferences."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    display_name: str | None = None
    dietary_profile: DietaryProfile = DietaryProfile()
    default_servings: int = 4
    unit_system: Literal["metric", "imperial"] = "metric"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Favorite(BaseModel):
    """A user's favorite/saved recipe."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    recipe_id: str
    notes: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    saved_at: datetime | None = None
