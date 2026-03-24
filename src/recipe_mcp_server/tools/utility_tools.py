"""Unit conversion and wine pairing utility tools."""

from __future__ import annotations

import json
from typing import cast

import structlog
from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from recipe_mcp_server.clients.spoonacular import SpoonacularClient
from recipe_mcp_server.exceptions import ExternalAPIError
from recipe_mcp_server.services.conversion_service import ConversionService

logger = structlog.get_logger(__name__)


def _get_conversion_service(ctx: Context) -> ConversionService:
    """Extract ConversionService from the lifespan context."""
    return cast(ConversionService, ctx.lifespan_context["conversion_service"])


def _get_spoonacular_client(ctx: Context) -> SpoonacularClient:
    """Extract SpoonacularClient from the lifespan context."""
    return cast(SpoonacularClient, ctx.lifespan_context["spoonacular_client"])


def register_utility_tools(mcp: FastMCP) -> None:
    """Register all utility tools on the given FastMCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        tags={"utility"},
    )
    async def convert_units(
        ctx: Context,
        value: float,
        from_unit: str,
        to_unit: str,
        ingredient: str | None = None,
    ) -> str:
        """Convert between cooking measurement units.

        Supports volume, weight, and temperature conversions.
        Specify an ingredient for cross-category conversions (e.g. cups to grams).

        Args:
            value: The amount to convert.
            from_unit: Source unit (e.g. "cups", "grams", "fahrenheit").
            to_unit: Target unit (e.g. "ml", "oz", "celsius").
            ingredient: Required for volume-to-weight conversions (e.g. "flour").
        """
        await ctx.info(
            f"Converting units: {value} {from_unit} -> {to_unit}, ingredient={ingredient}"
        )
        service = _get_conversion_service(ctx)
        try:
            if ingredient is not None:
                await ctx.debug(
                    f"Using API fallback for ingredient-based conversion: '{ingredient}'"
                )
                result = await service.convert_with_api_fallback(
                    value, from_unit, to_unit, ingredient=ingredient
                )
            else:
                result = service.convert(value, from_unit, to_unit)
            await ctx.debug(f"Conversion result: {value} {from_unit} = {result} {to_unit}")
            return json.dumps(
                {
                    "result": result,
                    "from": from_unit,
                    "to": to_unit,
                }
            )
        except ValueError as exc:
            await ctx.error(f"Conversion failed: {exc}")
            return f"Error: {exc}"

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True),
        tags={"utility"},
    )
    async def get_wine_pairing(ctx: Context, food: str) -> str:
        """Get wine pairing suggestions for a food.

        Args:
            food: The food to pair with wine (e.g. "salmon", "pasta").
        """
        await ctx.info(f"Getting wine pairing for: '{food}'")
        client = _get_spoonacular_client(ctx)
        try:
            pairing = await client.get_wine_pairing(food)
            await ctx.debug(f"Wine pairing found for '{food}'")
            return json.dumps(pairing)
        except ExternalAPIError as exc:
            await ctx.error(f"Wine pairing API failed for '{food}': {exc}")
            return f"Error getting wine pairing: {exc}"
