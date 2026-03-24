"""Standalone nutrition MCP sub-server for composition demonstration.

This server is mounted into the main recipe-mcp-server under the
``nutrition`` namespace, exposing nutrition-specific tools and resources
with prefixed names (e.g. ``nutrition_lookup_food_nutrition``).
"""

from __future__ import annotations

from typing import cast

import structlog
from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.services.nutrition_service import NutritionService

logger = structlog.get_logger(__name__)

nutrition_mcp = FastMCP(
    "nutrition-server",
    instructions="Nutrition lookup and analysis sub-server.",
)


def _get_nutrition_service(ctx: Context) -> NutritionService:
    """Extract NutritionService from the parent lifespan context."""
    return cast(NutritionService, ctx.lifespan_context["nutrition_service"])


@nutrition_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True),
    tags={"nutrition"},
)
async def lookup_food_nutrition(ctx: Context, food_name: str) -> str:
    """Look up nutrition information for a food item (via nutrition sub-server).

    Args:
        food_name: The food to look up (e.g. "chicken breast", "apple").
    """
    await ctx.info(f"[nutrition-server] Looking up nutrition for: '{food_name}'")
    service = _get_nutrition_service(ctx)
    try:
        info = await service.lookup(food_name)
        return info.model_dump_json()
    except NotFoundError as exc:
        return f"Error: {exc}"
    except ExternalAPIError as exc:
        return f"Error looking up nutrition: {exc}"


@nutrition_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True),
    tags={"nutrition"},
)
async def analyze_food_nutrition(ctx: Context, recipe_id: str) -> str:
    """Analyze the full nutrition breakdown for a recipe (via nutrition sub-server).

    Args:
        recipe_id: The recipe to analyze.
    """
    await ctx.info(f"[nutrition-server] Analyzing nutrition for recipe: '{recipe_id}'")
    service = _get_nutrition_service(ctx)
    try:
        report = await service.analyze_recipe(recipe_id)
        return report.model_dump_json()
    except NotFoundError as exc:
        return f"Error: {exc}"
    except ExternalAPIError as exc:
        return f"Error analyzing recipe nutrition: {exc}"


@nutrition_mcp.resource(
    "nutrition://composed/{food_name}",
    name="composed_nutrition",
    description="Nutrition data for a food item (via nutrition sub-server)",
    mime_type="application/json",
    tags={"nutrition"},
)
async def composed_nutrition_resource(food_name: str, ctx: Context) -> str:
    """Return nutrition data for a food item via the composed sub-server."""
    service = _get_nutrition_service(ctx)
    try:
        info = await service.lookup(food_name)
        return info.model_dump_json()
    except (NotFoundError, ExternalAPIError) as exc:
        return f'{{"error": "{exc}"}}'
