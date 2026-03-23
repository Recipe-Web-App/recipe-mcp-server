"""Templated MCP resources for recipe details, nutrition, meal plans, and favorites."""

from __future__ import annotations

import json
from typing import cast

import structlog
from fastmcp import Context, FastMCP

from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.services.meal_plan_service import MealPlanService
from recipe_mcp_server.services.nutrition_service import NutritionService
from recipe_mcp_server.services.recipe_service import RecipeService

logger = structlog.get_logger(__name__)


def _get_recipe_service(ctx: Context) -> RecipeService:
    """Extract RecipeService from the lifespan context."""
    return cast(RecipeService, ctx.lifespan_context["recipe_service"])


def _get_nutrition_service(ctx: Context) -> NutritionService:
    """Extract NutritionService from the lifespan context."""
    return cast(NutritionService, ctx.lifespan_context["nutrition_service"])


def _get_meal_plan_service(ctx: Context) -> MealPlanService:
    """Extract MealPlanService from the lifespan context."""
    return cast(MealPlanService, ctx.lifespan_context["meal_plan_service"])


def register_dynamic_resources(mcp: FastMCP) -> None:
    """Register all templated (dynamic) resources on the FastMCP server."""

    @mcp.resource(
        "recipe://recipe/{recipe_id}",
        name="recipe_detail",
        description=("Full recipe details including ingredients, instructions, and source info"),
        mime_type="application/json",
        tags={"recipe"},
    )
    async def recipe_detail(recipe_id: str, ctx: Context) -> str:
        """Return full recipe details by ID."""
        service = _get_recipe_service(ctx)
        try:
            recipe = await service.get(recipe_id)
            return recipe.model_dump_json()
        except NotFoundError as exc:
            return json.dumps({"error": str(exc)})

    @mcp.resource(
        "nutrition://{food_name}",
        name="nutrition_facts",
        description="USDA nutrition facts for a specific food (cached 7 days)",
        mime_type="application/json",
        tags={"nutrition"},
    )
    async def nutrition_facts(food_name: str, ctx: Context) -> str:
        """Return nutrition information for a food item."""
        service = _get_nutrition_service(ctx)
        try:
            info = await service.lookup(food_name)
            return info.model_dump_json()
        except (NotFoundError, ExternalAPIError) as exc:
            return json.dumps({"error": str(exc)})

    @mcp.resource(
        "mealplan://{plan_id}",
        name="meal_plan_detail",
        description=("Complete meal plan with all days, meals, and linked recipes"),
        mime_type="application/json",
        tags={"planning"},
    )
    async def meal_plan_detail(plan_id: str, ctx: Context) -> str:
        """Return a meal plan by ID."""
        service = _get_meal_plan_service(ctx)
        plan = await service.get(plan_id)
        if plan is None:
            return json.dumps({"error": f"Meal plan '{plan_id}' not found"})
        return plan.model_dump_json()

    @mcp.resource(
        "recipe://favorites/{user_id}",
        name="user_favorites",
        description=("User's saved favorite recipes with ratings and notes"),
        mime_type="application/json",
        tags={"recipe"},
    )
    async def user_favorites(user_id: str, ctx: Context) -> str:
        """Return a user's favorite recipes."""
        service = _get_recipe_service(ctx)
        favorites = await service.list_favorites(user_id)
        return json.dumps([f.model_dump() for f in favorites], default=str)
