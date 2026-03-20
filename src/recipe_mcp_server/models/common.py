"""Common types, enums, and generic models used across the domain."""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class APISource(StrEnum):
    """Source API for recipe data."""

    THEMEALDB = "themealdb"
    SPOONACULAR = "spoonacular"
    DUMMYJSON = "dummyjson"
    LOCAL = "local"
    OPENFOODFACTS = "openfoodfacts"


class Difficulty(StrEnum):
    """Recipe difficulty level."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class MealType(StrEnum):
    """Meal type classification."""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response with cursor-based pagination."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int
    next_cursor: str | None = None
