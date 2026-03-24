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
        service = _get_nutrition_service(ctx)
        try:
            info = await service.lookup(food_name)
            return info.model_dump_json()
        except NotFoundError as exc:
            return f"Error: {exc}"
        except ExternalAPIError as exc:
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
        service = _get_nutrition_service(ctx)
        try:
            report = await service.analyze_recipe(recipe_id)
            return report.model_dump_json()
        except NotFoundError as exc:
            return f"Error: {exc}"
        except ExternalAPIError as exc:
            return f"Error analyzing recipe nutrition: {exc}"
