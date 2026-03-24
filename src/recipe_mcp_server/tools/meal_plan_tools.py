"""Meal plan generation and shopping list tools."""

from __future__ import annotations

import asyncio
import json
from typing import cast

import structlog
from fastmcp import Context, FastMCP

from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.services.meal_plan_service import MealPlanService
from recipe_mcp_server.services.shopping_service import ShoppingService

logger = structlog.get_logger(__name__)


def _get_meal_plan_service(ctx: Context) -> MealPlanService:
    """Extract MealPlanService from the lifespan context."""
    return cast(MealPlanService, ctx.lifespan_context["meal_plan_service"])


def _get_shopping_service(ctx: Context) -> ShoppingService:
    """Extract ShoppingService from the lifespan context."""
    return cast(ShoppingService, ctx.lifespan_context["shopping_service"])


def register_meal_plan_tools(mcp: FastMCP) -> None:
    """Register all meal plan tools on the given FastMCP server."""

    @mcp.tool(tags={"planning"})
    async def generate_meal_plan(
        ctx: Context,
        user_id: str,
        name: str,
        time_frame: str = "week",
        target_calories: int = 2000,
        diet: str = "",
    ) -> str:
        """Generate a meal plan for a user.

        Args:
            user_id: The user to generate the plan for.
            name: A name for the meal plan.
            time_frame: Duration of the plan ("day" or "week", default "week").
            target_calories: Daily calorie target (default 2000).
            diet: Optional dietary restriction (e.g. "vegetarian", "keto").
        """
        await ctx.info(
            f"Generating meal plan: user='{user_id}', name='{name}', "
            f"time_frame='{time_frame}', calories={target_calories}"
        )

        # Use stored dietary preferences if diet not explicitly provided
        if not diet:
            prefs = await ctx.get_state("user_preferences")
            if isinstance(prefs, dict) and prefs.get("dietary_restrictions"):
                diet = ", ".join(prefs["dietary_restrictions"])
                await ctx.debug(f"Using stored dietary preferences: {diet}")

        service = _get_meal_plan_service(ctx)
        try:
            plan = await service.generate(
                user_id=user_id,
                name=name,
                time_frame=time_frame,
                target_calories=target_calories,
                diet=diet,
                on_progress=lambda c, t, m: ctx.report_progress(c, t, m),
            )
            await ctx.debug(f"Generated meal plan '{plan.id}' with {len(plan.days)} days")
            return plan.model_dump_json()
        except asyncio.CancelledError:
            await ctx.warning("Meal plan generation cancelled")
            return json.dumps({"cancelled": True, "partial_plan": None})
        except ExternalAPIError as exc:
            await ctx.error(f"Meal plan API failed: {exc}")
            return f"Error generating meal plan: {exc}"

    @mcp.tool(tags={"planning"})
    async def generate_shopping_list(
        ctx: Context,
        recipe_ids_json: str | None = None,
        meal_plan_id: str | None = None,
    ) -> str:
        """Generate a shopping list from recipes or a meal plan.

        Provide either recipe_ids_json or meal_plan_id (at least one required).

        Args:
            recipe_ids_json: JSON array of recipe ID strings (e.g. '["id1", "id2"]').
            meal_plan_id: ID of an existing meal plan.
        """
        if recipe_ids_json is None and meal_plan_id is None:
            return "Error: Provide at least one of recipe_ids_json or meal_plan_id"

        await ctx.info(
            f"Generating shopping list: meal_plan_id={meal_plan_id}, "
            f"recipe_ids_json={'provided' if recipe_ids_json else 'none'}"
        )
        service = _get_shopping_service(ctx)

        if meal_plan_id is not None:
            try:
                items = await service.generate_from_meal_plan(meal_plan_id)
                await ctx.debug(f"Generated shopping list with {len(items)} items from meal plan")
                return json.dumps([item.model_dump() for item in items], default=str)
            except NotFoundError as exc:
                await ctx.warning(f"Meal plan not found: '{meal_plan_id}'")
                return f"Error: {exc}"

        assert recipe_ids_json is not None  # guaranteed by guard above
        try:
            recipe_ids: list[str] = json.loads(recipe_ids_json)
        except (json.JSONDecodeError, TypeError) as exc:
            await ctx.error(f"Invalid recipe_ids_json format: {exc}")
            return f"Error: Invalid recipe_ids_json format: {exc}"

        try:
            items = await service.generate_from_recipes(recipe_ids)
            await ctx.debug(
                f"Generated shopping list with {len(items)} items from {len(recipe_ids)} recipes"
            )
            return json.dumps([item.model_dump() for item in items], default=str)
        except NotFoundError as exc:
            await ctx.warning(f"One or more recipes not found: {exc}")
            return f"Error: {exc}"
