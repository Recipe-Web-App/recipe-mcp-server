"""Tests for elicitation handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)

from recipe_mcp_server.elicitation.handlers import (
    clarify_available_ingredients,
    confirm_serving_size,
    gather_dietary_preferences,
)
from recipe_mcp_server.elicitation.schemas import (
    AvailableIngredientsForm,
    DietaryPreferencesForm,
    ServingSizeConfirmation,
)


@pytest.fixture
def mock_ctx() -> AsyncMock:
    """Create a mock MCP Context with an elicit() method."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock()
    return ctx


# -- gather_dietary_preferences -----------------------------------------------


@pytest.mark.asyncio
async def test_gather_dietary_preferences_accepted(mock_ctx: AsyncMock) -> None:
    """Returns a DietaryProfile when the user accepts the form."""
    form = DietaryPreferencesForm(
        restrictions="vegetarian, pescatarian",
        allergies="peanuts, shellfish",
        preferred_cuisines="Italian, Thai",
        calorie_target=2000,
    )
    mock_ctx.elicit.return_value = AcceptedElicitation(data=form)

    result = await gather_dietary_preferences(mock_ctx)

    assert result is not None
    assert result.dietary_restrictions == ["vegetarian", "pescatarian"]
    assert result.allergies == ["peanuts", "shellfish"]
    assert result.preferred_cuisines == ["Italian", "Thai"]
    assert result.calorie_target == 2000


@pytest.mark.asyncio
async def test_gather_dietary_preferences_zero_calorie_target(
    mock_ctx: AsyncMock,
) -> None:
    """A calorie_target of 0 is treated as 'no target' (None)."""
    form = DietaryPreferencesForm(calorie_target=0)
    mock_ctx.elicit.return_value = AcceptedElicitation(data=form)

    result = await gather_dietary_preferences(mock_ctx)

    assert result is not None
    assert result.calorie_target is None


@pytest.mark.asyncio
async def test_gather_dietary_preferences_empty_fields(mock_ctx: AsyncMock) -> None:
    """Returns empty lists when all string fields are empty."""
    form = DietaryPreferencesForm()
    mock_ctx.elicit.return_value = AcceptedElicitation(data=form)

    result = await gather_dietary_preferences(mock_ctx)

    assert result is not None
    assert result.dietary_restrictions == []
    assert result.allergies == []
    assert result.preferred_cuisines == []
    assert result.calorie_target is None


@pytest.mark.asyncio
async def test_gather_dietary_preferences_declined(mock_ctx: AsyncMock) -> None:
    """Returns None when the user declines."""
    mock_ctx.elicit.return_value = DeclinedElicitation()

    result = await gather_dietary_preferences(mock_ctx)

    assert result is None


@pytest.mark.asyncio
async def test_gather_dietary_preferences_cancelled(mock_ctx: AsyncMock) -> None:
    """Returns None when the user cancels."""
    mock_ctx.elicit.return_value = CancelledElicitation()

    result = await gather_dietary_preferences(mock_ctx)

    assert result is None


# -- confirm_serving_size -----------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_serving_size_accepted(mock_ctx: AsyncMock) -> None:
    """Returns the confirmed serving count when accepted."""
    confirmation = ServingSizeConfirmation(confirmed_servings=50, reason="party")
    mock_ctx.elicit.return_value = AcceptedElicitation(data=confirmation)

    result = await confirm_serving_size(mock_ctx, target_servings=50)

    assert result == 50


@pytest.mark.asyncio
async def test_confirm_serving_size_declined(mock_ctx: AsyncMock) -> None:
    """Returns None when the user declines."""
    mock_ctx.elicit.return_value = DeclinedElicitation()

    result = await confirm_serving_size(mock_ctx, target_servings=30)

    assert result is None


@pytest.mark.asyncio
async def test_confirm_serving_size_cancelled(mock_ctx: AsyncMock) -> None:
    """Returns None when the user cancels."""
    mock_ctx.elicit.return_value = CancelledElicitation()

    result = await confirm_serving_size(mock_ctx, target_servings=25)

    assert result is None


# -- clarify_available_ingredients --------------------------------------------


@pytest.mark.asyncio
async def test_clarify_available_ingredients_accepted(mock_ctx: AsyncMock) -> None:
    """Returns the form data when accepted."""
    form = AvailableIngredientsForm(
        ingredients="chicken, rice, garlic, onion",
        pantry_staples_available=True,
        cooking_equipment="oven, stovetop",
    )
    mock_ctx.elicit.return_value = AcceptedElicitation(data=form)

    result = await clarify_available_ingredients(mock_ctx)

    assert result is not None
    assert result.ingredients == "chicken, rice, garlic, onion"
    assert result.pantry_staples_available is True
    assert result.cooking_equipment == "oven, stovetop"


@pytest.mark.asyncio
async def test_clarify_available_ingredients_declined(mock_ctx: AsyncMock) -> None:
    """Returns None when the user declines."""
    mock_ctx.elicit.return_value = DeclinedElicitation()

    result = await clarify_available_ingredients(mock_ctx)

    assert result is None
