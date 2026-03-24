"""Elicitation handlers that request structured user input via ctx.elicit()."""

from __future__ import annotations

from typing import Any, cast

import structlog
from fastmcp import Context
from fastmcp.server.elicitation import AcceptedElicitation

from recipe_mcp_server.elicitation.schemas import (
    AvailableIngredientsForm,
    DietaryPreferencesForm,
    ServingSizeConfirmation,
)
from recipe_mcp_server.models.user import DietaryProfile

logger = structlog.get_logger(__name__)


def _parse_comma_list(value: str) -> list[str]:
    """Parse a comma-separated string into a list of stripped, non-empty strings."""
    return [item.strip() for item in value.split(",") if item.strip()]


async def gather_dietary_preferences(ctx: Context) -> DietaryProfile | None:
    """Elicit dietary preferences from the user.

    Args:
        ctx: The MCP context for issuing elicitation requests.

    Returns:
        A DietaryProfile if the user accepted, or None if declined/cancelled.
    """
    logger.info("eliciting_dietary_preferences")

    result = await ctx.elicit(
        "Please provide your dietary preferences to personalize your results.",
        response_type=cast(Any, DietaryPreferencesForm),
    )

    if not isinstance(result, AcceptedElicitation):
        logger.info("dietary_preferences_declined", action=result.action)
        return None

    form = DietaryPreferencesForm(**result.data) if isinstance(result.data, dict) else result.data
    profile = DietaryProfile(
        dietary_restrictions=_parse_comma_list(form.restrictions),
        allergies=_parse_comma_list(form.allergies),
        preferred_cuisines=_parse_comma_list(form.preferred_cuisines),
        calorie_target=form.calorie_target if form.calorie_target > 0 else None,
    )

    await ctx.set_state("user_preferences", profile.model_dump())
    await ctx.disable_components(names={"gather_dietary_preferences"})

    return profile


async def confirm_serving_size(ctx: Context, target_servings: int) -> int | None:
    """Elicit confirmation for an unusually large serving size.

    Args:
        ctx: The MCP context for issuing elicitation requests.
        target_servings: The requested number of servings to confirm.

    Returns:
        The confirmed serving count if accepted, or None if declined/cancelled.
    """
    logger.info("eliciting_serving_confirmation", target_servings=target_servings)

    result = await ctx.elicit(
        f"You requested {target_servings} servings, which is unusually large. "
        "Please confirm the number of servings and provide a reason.",
        response_type=cast(Any, ServingSizeConfirmation),
    )

    if not isinstance(result, AcceptedElicitation):
        logger.info("serving_confirmation_declined", action=result.action)
        return None

    confirmation = (
        ServingSizeConfirmation(**result.data) if isinstance(result.data, dict) else result.data
    )
    logger.info(
        "serving_size_confirmed",
        confirmed_servings=confirmation.confirmed_servings,
        reason=confirmation.reason,
    )
    return confirmation.confirmed_servings


async def clarify_available_ingredients(
    ctx: Context,
) -> AvailableIngredientsForm | None:
    """Elicit available ingredients and kitchen context from the user.

    Args:
        ctx: The MCP context for issuing elicitation requests.

    Returns:
        The completed form if accepted, or None if declined/cancelled.
    """
    logger.info("eliciting_available_ingredients")

    result = await ctx.elicit(
        "Please clarify the ingredients you have available and your kitchen setup.",
        response_type=cast(Any, AvailableIngredientsForm),
    )

    if not isinstance(result, AcceptedElicitation):
        logger.info("ingredients_clarification_declined", action=result.action)
        return None

    if isinstance(result.data, dict):
        return AvailableIngredientsForm(**result.data)
    return result.data
