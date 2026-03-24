"""Nutrition lookup and recipe analysis tools."""

from __future__ import annotations

from typing import cast

import structlog
from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.services.nutrition_service import NutritionService

logger = structlog.get_logger(__name__)


def _get_nutrition_service(ctx: Context) -> NutritionService:
    """Extract NutritionService from the lifespan context."""
    return cast(NutritionService, ctx.lifespan_context["nutrition_service"])


def register_nutrition_tools(mcp: FastMCP) -> None:
    """Register all nutrition tools on the given FastMCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True),
        tags={"nutrition"},
    )
    async def lookup_nutrition(ctx: Context, food_name: str) -> str:
        """Look up nutrition information for a food item.

        Args:
            food_name: The food to look up (e.g. "chicken breast", "apple").
        """
        await ctx.info(f"Looking up nutrition for: '{food_name}'")
        service = _get_nutrition_service(ctx)
        try:
            info = await service.lookup(food_name)
            await ctx.debug(f"Nutrition lookup complete for '{food_name}'")
            return info.model_dump_json()
        except NotFoundError as exc:
            await ctx.warning(f"Nutrition data not found for '{food_name}'")
            return f"Error: {exc}"
        except ExternalAPIError as exc:
            await ctx.error(f"Nutrition API failed for '{food_name}': {exc}")
            return f"Error looking up nutrition: {exc}"

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True),
        tags={"nutrition", "recipe"},
    )
    async def analyze_recipe_nutrition(ctx: Context, recipe_id: str) -> str:
        """Analyze the full nutrition breakdown for a recipe.

        Args:
            recipe_id: The recipe to analyze.
        """
        await ctx.info(f"Analyzing nutrition for recipe: '{recipe_id}'")
        service = _get_nutrition_service(ctx)
        try:
            report = await service.analyze_recipe(recipe_id)
            await ctx.debug(f"Nutrition analysis complete for recipe '{recipe_id}'")
            return report.model_dump_json()
        except NotFoundError as exc:
            await ctx.warning(f"Recipe not found for nutrition analysis: '{recipe_id}'")
            return f"Error: {exc}"
        except ExternalAPIError as exc:
            await ctx.error(f"Nutrition API failed for recipe '{recipe_id}': {exc}")
            return f"Error analyzing recipe nutrition: {exc}"
