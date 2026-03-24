"""Dietary prompts: adapt_for_diet, ingredient_spotlight."""

from __future__ import annotations

from typing import cast

import structlog
from fastmcp import Context, FastMCP
from fastmcp.prompts.prompt import Message, PromptResult

from recipe_mcp_server.exceptions import NotFoundError
from recipe_mcp_server.services.recipe_service import RecipeService

logger = structlog.get_logger(__name__)


def _get_recipe_service(ctx: Context) -> RecipeService:
    """Extract RecipeService from the lifespan context."""
    return cast(RecipeService, ctx.lifespan_context["recipe_service"])


def register_dietary_prompts(mcp: FastMCP) -> None:
    """Register dietary-adaptation prompts on the given FastMCP server."""

    @mcp.prompt(tags={"recipe", "nutrition"})
    async def adapt_for_diet(
        ctx: Context,
        recipe_id: str,
        restrictions: list[str],
    ) -> PromptResult:
        """Modify an existing recipe for specific dietary needs.

        Fetches the original recipe to provide full ingredient context for
        accurate adaptation suggestions.

        Args:
            recipe_id: ID of the recipe to adapt.
            restrictions: Dietary restrictions to apply (e.g. ["vegan", "gluten-free"]).
        """
        service = _get_recipe_service(ctx)
        try:
            recipe = await service.get(recipe_id)
        except NotFoundError:
            return PromptResult(
                messages=[
                    Message(
                        f"Recipe '{recipe_id}' was not found. Please provide a valid "
                        "recipe ID so I can suggest dietary adaptations.",
                        role="user",
                    ),
                ],
                description="Recipe not found",
            )

        ingredient_lines = []
        for ing in recipe.ingredients:
            parts = []
            if ing.quantity is not None:
                parts.append(str(ing.quantity))
            if ing.unit:
                parts.append(ing.unit)
            parts.append(ing.name)
            if ing.notes:
                parts.append(f"({ing.notes})")
            ingredient_lines.append(" ".join(parts))

        restriction_str = ", ".join(restrictions)
        ingredient_block = "\n".join(f"- {line}" for line in ingredient_lines)

        system_msg = (
            "You are a dietitian and recipe adaptation specialist. Modify recipes "
            "to meet dietary requirements while preserving flavour and texture as "
            "much as possible. For each ingredient that needs changing, explain the "
            "substitution and why it works."
        )
        user_msg = (
            f'Please adapt the recipe "{recipe.title}" for these dietary '
            f"restrictions: {restriction_str}\n\n"
            f"Current ingredients:\n{ingredient_block}\n\n"
            "For each ingredient that conflicts with the restrictions, suggest "
            "a substitute and explain how it affects the dish."
        )

        return PromptResult(
            messages=[
                Message(system_msg, role="assistant"),
                Message(user_msg, role="user"),
            ],
            description=f"Adapt '{recipe.title}' for {restriction_str}",
        )

    @mcp.prompt(tags={"nutrition"})
    async def ingredient_spotlight(
        ingredient: str,
    ) -> PromptResult:
        """Deep dive into an ingredient's history, uses, nutrition, and storage.

        Args:
            ingredient: The ingredient to explore (e.g. "saffron", "chickpeas", "miso").
        """
        system_msg = (
            "You are a food historian, nutritionist, and culinary educator. "
            "Provide comprehensive, engaging information about ingredients "
            "covering their origin, culinary uses, nutritional profile, "
            "selection tips, and storage guidelines."
        )
        user_msg = (
            f'Tell me everything about "{ingredient}":\n\n'
            "1. **Origin & History** — Where does it come from? How has it been "
            "used historically?\n"
            "2. **Culinary Uses** — What cuisines feature it? What are classic "
            "and creative ways to use it?\n"
            "3. **Nutrition** — Key nutrients, health benefits, and any cautions.\n"
            "4. **Selection & Storage** — How to pick the best quality and store "
            "it properly.\n"
            "5. **Fun Facts** — Anything surprising or interesting."
        )

        return PromptResult(
            messages=[
                Message(system_msg, role="assistant"),
                Message(user_msg, role="user"),
            ],
            description=f"Spotlight on {ingredient}",
        )
