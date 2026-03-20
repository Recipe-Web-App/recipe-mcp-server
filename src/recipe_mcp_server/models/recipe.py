"""Recipe domain models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from recipe_mcp_server.models.common import APISource, Difficulty


class Ingredient(BaseModel):
    """A single ingredient in a recipe."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    quantity: float | None = None
    unit: str | None = None
    notes: str | None = None
    order_index: int = 0


class ScaledIngredient(Ingredient):
    """An ingredient with scaling information."""

    original_quantity: float | None = None
    scale_factor: float = 1.0


class Recipe(BaseModel):
    """Full recipe with all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    title: str
    description: str | None = None
    instructions: list[str] = []
    category: str | None = None
    area: str | None = None
    image_url: str | None = None
    source_url: str | None = None
    source_api: APISource | None = None
    source_id: str | None = None
    prep_time_min: int | None = None
    cook_time_min: int | None = None
    servings: int = 4
    difficulty: Difficulty | None = None
    tags: list[str] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    is_deleted: bool = False
    ingredients: list[Ingredient] = []


class RecipeCreate(BaseModel):
    """Fields for creating a new recipe."""

    title: str
    description: str | None = None
    instructions: list[str] = []
    category: str | None = None
    area: str | None = None
    image_url: str | None = None
    source_url: str | None = None
    source_api: APISource | None = None
    source_id: str | None = None
    prep_time_min: int | None = None
    cook_time_min: int | None = None
    servings: int = 4
    difficulty: Difficulty | None = None
    tags: list[str] = []
    ingredients: list[Ingredient] = []


class RecipeUpdate(BaseModel):
    """Fields for updating an existing recipe. All fields optional."""

    title: str | None = None
    description: str | None = None
    instructions: list[str] | None = None
    category: str | None = None
    area: str | None = None
    image_url: str | None = None
    source_url: str | None = None
    prep_time_min: int | None = None
    cook_time_min: int | None = None
    servings: int | None = None
    difficulty: Difficulty | None = None
    tags: list[str] | None = None
    ingredients: list[Ingredient] | None = None


class RecipeSummary(BaseModel):
    """Lightweight recipe summary for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    category: str | None = None
    area: str | None = None
    image_url: str | None = None
    source_api: APISource | None = None
    difficulty: Difficulty | None = None
