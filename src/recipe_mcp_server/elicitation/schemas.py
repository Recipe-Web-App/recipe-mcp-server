"""Flat Pydantic models for MCP elicitation forms.

MCP elicitation only supports flat object schemas with primitive types
(string, number, integer, boolean). List fields use comma-separated strings
that are parsed after elicitation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DietaryPreferencesForm(BaseModel):
    """Elicitation form for collecting dietary preferences.

    Fields use comma-separated strings because MCP elicitation
    does not support array types.
    """

    restrictions: str = Field(
        default="",
        description="Dietary restrictions, comma-separated (e.g. vegetarian, vegan, keto)",
    )
    allergies: str = Field(
        default="",
        description="Food allergies, comma-separated (e.g. peanuts, shellfish, gluten)",
    )
    preferred_cuisines: str = Field(
        default="",
        description="Preferred cuisines, comma-separated (e.g. Italian, Thai, Mexican)",
    )
    calorie_target: int = Field(
        default=0,
        description="Daily calorie target (0 means no target)",
    )


class ServingSizeConfirmation(BaseModel):
    """Elicitation form for confirming unusually large serving sizes."""

    confirmed_servings: int = Field(
        description="Confirmed number of servings",
    )
    reason: str = Field(
        default="other",
        description="Reason for large serving size (party, meal_prep, restaurant, other)",
    )


class AvailableIngredientsForm(BaseModel):
    """Elicitation form for clarifying available ingredients and kitchen context."""

    ingredients: str = Field(
        default="",
        description="Available ingredients, comma-separated (e.g. chicken, rice, garlic, onion)",
    )
    pantry_staples_available: bool = Field(
        default=True,
        description="Whether common pantry staples (salt, pepper, oil, etc.) are available",
    )
    cooking_equipment: str = Field(
        default="",
        description="Available cooking equipment, comma-separated (e.g. oven, stovetop, grill)",
    )
