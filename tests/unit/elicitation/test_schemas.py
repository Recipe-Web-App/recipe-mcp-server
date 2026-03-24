"""Tests for elicitation form schemas — validates MCP compatibility."""

from __future__ import annotations

import pytest
from fastmcp.server.elicitation import get_elicitation_schema, validate_elicitation_json_schema

from recipe_mcp_server.elicitation.schemas import (
    AvailableIngredientsForm,
    DietaryPreferencesForm,
    ServingSizeConfirmation,
)


@pytest.mark.parametrize(
    "schema_cls",
    [DietaryPreferencesForm, ServingSizeConfirmation, AvailableIngredientsForm],
    ids=["dietary_preferences", "serving_size", "available_ingredients"],
)
def test_schema_produces_valid_mcp_elicitation_schema(schema_cls: type) -> None:
    """All elicitation schemas must produce valid flat JSON schemas for MCP."""
    schema = get_elicitation_schema(schema_cls)

    # Should not raise
    validate_elicitation_json_schema(schema)


@pytest.mark.parametrize(
    "schema_cls",
    [DietaryPreferencesForm, ServingSizeConfirmation, AvailableIngredientsForm],
    ids=["dietary_preferences", "serving_size", "available_ingredients"],
)
def test_schema_is_object_type(schema_cls: type) -> None:
    """All elicitation schemas must be object type."""
    schema = get_elicitation_schema(schema_cls)
    assert schema["type"] == "object"


def test_dietary_preferences_has_expected_fields() -> None:
    """DietaryPreferencesForm schema should have all expected properties."""
    schema = get_elicitation_schema(DietaryPreferencesForm)
    props = schema["properties"]
    assert "restrictions" in props
    assert "allergies" in props
    assert "preferred_cuisines" in props
    assert "calorie_target" in props


def test_serving_size_has_expected_fields() -> None:
    """ServingSizeConfirmation schema should have all expected properties."""
    schema = get_elicitation_schema(ServingSizeConfirmation)
    props = schema["properties"]
    assert "confirmed_servings" in props
    assert "reason" in props


def test_available_ingredients_has_expected_fields() -> None:
    """AvailableIngredientsForm schema should have all expected properties."""
    schema = get_elicitation_schema(AvailableIngredientsForm)
    props = schema["properties"]
    assert "ingredients" in props
    assert "pantry_staples_available" in props
    assert "cooking_equipment" in props
