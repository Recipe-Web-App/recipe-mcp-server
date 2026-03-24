"""Sampling handlers that request LLM completions via ctx.sample()."""

from __future__ import annotations

import structlog
from fastmcp import Context

from recipe_mcp_server.models.recipe import Recipe

logger = structlog.get_logger(__name__)

VARIATION_PROMPT = (
    "Given this recipe for {title}, suggest 3 creative variations: "
    "one fusion twist, one seasonal adaptation, and one simplified version"
)

PAIRING_PROMPT = (
    "For a main dish featuring {main_ingredient} with {cuisine} flavors, "
    "suggest 3 complementary side ingredients with brief reasoning"
)

MAX_TOKENS_VARIATIONS = 1024
MAX_TOKENS_PAIRING = 512


async def suggest_recipe_variations(ctx: Context, recipe: Recipe) -> str:
    """Request LLM-generated creative variations of a recipe.

    Args:
        ctx: The MCP context for issuing sampling requests.
        recipe: The recipe to generate variations for.

    Returns:
        The LLM's suggested variations as text.
    """
    prompt = VARIATION_PROMPT.format(title=recipe.title)
    logger.info("sampling_recipe_variations", recipe_id=recipe.id, title=recipe.title)

    result = await ctx.sample(prompt, max_tokens=MAX_TOKENS_VARIATIONS)
    return result.text or ""


async def pair_ingredients(ctx: Context, main_ingredient: str, cuisine: str) -> str:
    """Request LLM-suggested complementary side ingredients.

    Args:
        ctx: The MCP context for issuing sampling requests.
        main_ingredient: The primary ingredient of the main dish.
        cuisine: The cuisine style to match.

    Returns:
        The LLM's ingredient pairing suggestions as text.
    """
    prompt = PAIRING_PROMPT.format(main_ingredient=main_ingredient, cuisine=cuisine)
    logger.info(
        "sampling_ingredient_pairing",
        main_ingredient=main_ingredient,
        cuisine=cuisine,
    )

    result = await ctx.sample(prompt, max_tokens=MAX_TOKENS_PAIRING)
    return result.text or ""
