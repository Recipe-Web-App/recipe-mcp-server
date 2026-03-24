"""Seasonal tool that is dynamically shown/hidden based on current month.

The ``get_holiday_recipes`` tool is registered at startup but only visible
during November and December.  A ``ToolListChangedNotification`` is sent
when the tool first becomes visible in a session.
"""

from __future__ import annotations

import datetime
import json
from typing import cast

import structlog
from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations, ToolListChangedNotification

from recipe_mcp_server.services.recipe_service import RecipeService

logger = structlog.get_logger(__name__)

HOLIDAY_MONTHS = {11, 12}

_HOLIDAY_KEYWORDS: dict[str, list[str]] = {
    "christmas": ["gingerbread", "eggnog", "roast turkey", "candy cane"],
    "thanksgiving": ["pumpkin pie", "stuffing", "cranberry", "sweet potato"],
    "hanukkah": ["latke", "sufganiyah", "brisket", "challah"],
    "new year": ["champagne", "appetizer", "shrimp", "fondue"],
}


def _is_holiday_season() -> bool:
    """Return True if the current month is November or December."""
    return datetime.datetime.now(tz=datetime.UTC).month in HOLIDAY_MONTHS


def _get_recipe_service(ctx: Context) -> RecipeService:
    """Extract RecipeService from the lifespan context."""
    return cast(RecipeService, ctx.lifespan_context["recipe_service"])


def register_seasonal_tools(mcp: FastMCP) -> None:
    """Register seasonal tools on the given FastMCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        tags={"recipe", "seasonal"},
    )
    async def get_holiday_recipes(
        ctx: Context,
        holiday: str = "christmas",
    ) -> str:
        """Get holiday-themed recipe suggestions (available Nov-Dec).

        Args:
            holiday: Holiday theme — christmas, thanksgiving, hanukkah,
                     or new year (default "christmas").
        """
        await ctx.info(f"Getting holiday recipes: holiday='{holiday}'")

        if not _is_holiday_season():
            return json.dumps(
                {"error": "Holiday recipes are only available in November and December"}
            )

        keywords = _HOLIDAY_KEYWORDS.get(holiday.lower(), _HOLIDAY_KEYWORDS["christmas"])
        service = _get_recipe_service(ctx)

        all_results = []
        for keyword in keywords:
            await ctx.report_progress(
                keywords.index(keyword),
                len(keywords),
                f"Searching for {keyword} recipes...",
            )
            try:
                results = await service.search(keyword, limit=3)
                all_results.extend(results)
            except Exception:
                await ctx.warning(f"Search failed for keyword '{keyword}'")

        await ctx.report_progress(len(keywords), len(keywords), "Done")
        return json.dumps(
            {
                "holiday": holiday,
                "recipes": [r.model_dump() for r in all_results],
            },
            default=str,
        )


async def toggle_seasonal_visibility(ctx: Context) -> None:
    """Enable/disable seasonal tools based on current month.

    Should be called during session setup or from a tool handler.
    Sends ``ToolListChangedNotification`` when visibility changes.
    """
    if _is_holiday_season():
        await ctx.enable_components(names=["get_holiday_recipes"])
    else:
        await ctx.disable_components(names=["get_holiday_recipes"])
    await ctx.send_notification(ToolListChangedNotification())
