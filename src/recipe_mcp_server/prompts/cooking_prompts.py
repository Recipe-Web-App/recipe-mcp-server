"""Cooking instruction prompts: cooking_instructions."""

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


def register_cooking_prompts(mcp: FastMCP) -> None:
    """Register cooking instruction prompts on the given FastMCP server."""

    @mcp.prompt(tags={"recipe"})
    async def cooking_instructions(
        ctx: Context,
        recipe_id: str,
        skill_level: str | None = None,
    ) -> PromptResult:
        """Detailed step-by-step cooking guidance for a recipe.

        Fetches the recipe to include its instructions and ingredients for
        contextual, skill-appropriate guidance.

        Args:
            recipe_id: ID of the recipe to explain.
            skill_level: Cook's skill level — "beginner", "intermediate", or "advanced".
        """
        service = _get_recipe_service(ctx)
        try:
            recipe = await service.get(recipe_id)
        except NotFoundError:
            return PromptResult(
                messages=[
                    Message(
                        f"Recipe '{recipe_id}' was not found. Please provide a valid "
                        "recipe ID to get cooking instructions.",
                        role="user",
                    ),
                ],
                description="Recipe not found",
            )

        level = skill_level or "intermediate"

        ingredient_lines = []
        for ing in recipe.ingredients:
            parts = []
            if ing.quantity is not None:
                parts.append(str(ing.quantity))
            if ing.unit:
                parts.append(ing.unit)
            parts.append(ing.name)
            ingredient_lines.append(" ".join(parts))

        ingredient_block = "\n".join(f"- {line}" for line in ingredient_lines)

        steps_block = ""
        if recipe.instructions:
            steps_block = "\n".join(f"{i}. {step}" for i, step in enumerate(recipe.instructions, 1))
        else:
            steps_block = "(No instructions stored — please generate from scratch.)"

        timing_parts: list[str] = []
        if recipe.prep_time_min is not None:
            timing_parts.append(f"Prep: {recipe.prep_time_min} min")
        if recipe.cook_time_min is not None:
            timing_parts.append(f"Cook: {recipe.cook_time_min} min")
        timing_line = ", ".join(timing_parts) if timing_parts else "Timing not specified"

        system_msg = (
            f"You are a patient cooking instructor tailoring guidance for a "
            f"{level}-level cook. Explain techniques clearly, anticipate common "
            f"mistakes, and offer tips appropriate to the skill level. "
            f"{'Include basic definitions for culinary terms.' if level == 'beginner' else ''}"
            f"{'Focus on advanced techniques and plating.' if level == 'advanced' else ''}"
        )
        user_msg = (
            f'Please provide detailed cooking instructions for "{recipe.title}" '
            f"(serves {recipe.servings}).\n\n"
            f"**Timing:** {timing_line}\n\n"
            f"**Ingredients:**\n{ingredient_block}\n\n"
            f"**Original steps:**\n{steps_block}\n\n"
            "Please expand each step with detailed technique explanations, "
            "timing cues, and visual indicators of doneness."
        )

        return PromptResult(
            messages=[
                Message(system_msg, role="assistant"),
                Message(user_msg, role="user"),
            ],
            description=f"Cooking instructions for '{recipe.title}' ({level})",
        )
