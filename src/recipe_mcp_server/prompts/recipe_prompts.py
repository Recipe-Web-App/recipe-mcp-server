"""Recipe generation prompts: generate_recipe, leftover_recipe, quick_meal."""

from __future__ import annotations

import structlog
from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message, PromptResult

logger = structlog.get_logger(__name__)


def register_recipe_prompts(mcp: FastMCP) -> None:
    """Register recipe-generation prompts on the given FastMCP server."""

    @mcp.prompt(tags={"recipe", "creative"})
    async def generate_recipe(
        cuisine: str,
        main_ingredient: str | None = None,
        difficulty: str | None = None,
        dietary_restrictions: list[str] | None = None,
    ) -> PromptResult:
        """Create a new recipe from cuisine and ingredient constraints.

        Args:
            cuisine: Cuisine style (e.g. "Italian", "Japanese", "Mexican").
            main_ingredient: Primary ingredient to feature.
            difficulty: Recipe difficulty — "easy", "medium", or "hard".
            dietary_restrictions: Dietary restrictions to honour (e.g. ["vegan", "gluten-free"]).
        """
        constraints: list[str] = [f"Cuisine: {cuisine}"]
        if main_ingredient:
            constraints.append(f"Main ingredient: {main_ingredient}")
        if difficulty:
            constraints.append(f"Difficulty: {difficulty}")
        if dietary_restrictions:
            constraints.append(f"Dietary restrictions: {', '.join(dietary_restrictions)}")

        system_msg = (
            "You are an expert chef and recipe developer. Create detailed, "
            "authentic recipes that respect the given constraints. Include a title, "
            "description, full ingredient list with quantities, and step-by-step "
            "instructions. Add prep time, cook time, and serving size."
        )
        user_msg = (
            "Please create a recipe with the following constraints:\n\n"
            + "\n".join(f"- {c}" for c in constraints)
            + "\n\nProvide the recipe in a clear, structured format."
        )

        return PromptResult(
            messages=[
                Message(system_msg, role="assistant"),
                Message(user_msg, role="user"),
            ],
            description=f"Generate a {cuisine} recipe",
        )

    @mcp.prompt(tags={"recipe", "creative"})
    async def leftover_recipe(
        ingredients: list[str],
    ) -> PromptResult:
        """Generate a creative recipe from available leftover ingredients.

        Args:
            ingredients: Leftover ingredients to use
                (e.g. ["chicken breast", "rice", "bell peppers"]).
        """
        ingredient_list = ", ".join(ingredients)

        system_msg = (
            "You are a resourceful home chef specialising in reducing food waste. "
            "Create delicious recipes using only the provided leftover ingredients "
            "plus common pantry staples (salt, pepper, oil, basic spices). "
            "Prioritise using all listed ingredients."
        )
        user_msg = (
            f"I have these leftover ingredients: {ingredient_list}\n\n"
            "Please suggest a recipe that uses as many of these ingredients as "
            "possible. Include the full ingredient list, step-by-step instructions, "
            "and estimated cooking time."
        )

        return PromptResult(
            messages=[
                Message(system_msg, role="assistant"),
                Message(user_msg, role="user"),
            ],
            description="Recipe from leftover ingredients",
        )

    @mcp.prompt(tags={"recipe"})
    async def quick_meal(
        max_minutes: int,
        available_ingredients: list[str] | None = None,
    ) -> PromptResult:
        """Suggest a quick meal achievable under a time limit.

        Args:
            max_minutes: Maximum total time in minutes (prep + cook).
            available_ingredients: Ingredients you already have on hand.
        """
        system_msg = (
            "You are a time-efficient cooking expert. Suggest meals that can "
            "realistically be prepared and cooked within the given time limit. "
            "Be honest about timing — include prep, cook, and any resting time."
        )

        user_parts = [f"I need a meal I can make in {max_minutes} minutes or less."]
        if available_ingredients:
            user_parts.append(
                f"I have these ingredients available: {', '.join(available_ingredients)}"
            )
        user_parts.append(
            "Please suggest a recipe with ingredients, step-by-step instructions, "
            "and a realistic time breakdown."
        )

        return PromptResult(
            messages=[
                Message(system_msg, role="assistant"),
                Message("\n\n".join(user_parts), role="user"),
            ],
            description=f"Quick meal in {max_minutes} minutes",
        )
