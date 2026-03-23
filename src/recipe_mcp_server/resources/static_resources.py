"""Static MCP resources for recipe catalog, categories, cuisines, and ingredients."""

from __future__ import annotations

import json
from typing import Any, cast

import structlog
from fastmcp import Context, FastMCP

from recipe_mcp_server.clients.themealdb import TheMealDBClient
from recipe_mcp_server.exceptions import ExternalAPIError
from recipe_mcp_server.services.recipe_service import RecipeService

logger = structlog.get_logger(__name__)

MAX_CATALOG_ITEMS = 10_000


def _get_recipe_service(ctx: Context) -> RecipeService:
    """Extract RecipeService from the lifespan context."""
    return cast(RecipeService, ctx.lifespan_context["recipe_service"])


def _get_mealdb_client(ctx: Context) -> TheMealDBClient:
    """Extract TheMealDBClient from the lifespan context."""
    return cast(TheMealDBClient, ctx.lifespan_context["mealdb_client"])


async def _collect_all_recipes(
    service: RecipeService,
) -> list[dict[str, Any]]:
    """Paginate through all local recipes, returning summary dicts."""
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while len(items) < MAX_CATALOG_ITEMS:
        page = await service.list_recipes(cursor=cursor, limit=50)
        for recipe in page.items:
            items.append(
                {
                    "id": recipe.id,
                    "title": recipe.title,
                    "category": recipe.category,
                    "area": recipe.area,
                }
            )
        cursor = page.next_cursor
        if cursor is None:
            break
    return items


def register_static_resources(mcp: FastMCP) -> None:
    """Register all static (non-templated) resources on the FastMCP server."""

    @mcp.resource(
        "recipe://catalog",
        name="recipe_catalog",
        description=(
            "Complete list of locally-stored recipe summaries (id, title, category, area)"
        ),
        mime_type="application/json",
        tags={"recipe", "catalog"},
    )
    async def recipe_catalog(ctx: Context) -> str:
        """Return all locally-stored recipe summaries."""
        service = _get_recipe_service(ctx)
        items = await _collect_all_recipes(service)
        return json.dumps(items, default=str)

    @mcp.resource(
        "recipe://categories",
        name="recipe_categories",
        description=("All available recipe categories aggregated from TheMealDB and local storage"),
        mime_type="application/json",
        tags={"recipe", "reference"},
    )
    async def recipe_categories(ctx: Context) -> str:
        """Return deduplicated, sorted list of recipe categories."""
        client = _get_mealdb_client(ctx)
        service = _get_recipe_service(ctx)

        categories: set[str] = set()

        # TheMealDB categories
        try:
            mealdb_cats = await client.list_categories()
            for cat in mealdb_cats:
                name = cat.get("strCategory")
                if isinstance(name, str):
                    categories.add(name)
        except ExternalAPIError:
            logger.warning("mealdb_categories_unavailable")

        # Local recipe categories
        local_recipes = await _collect_all_recipes(service)
        for recipe in local_recipes:
            local_cat = recipe.get("category")
            if isinstance(local_cat, str):
                categories.add(local_cat)

        return json.dumps(sorted(categories))

    @mcp.resource(
        "recipe://cuisines",
        name="recipe_cuisines",
        description=("All available cuisine areas/regions from TheMealDB and local storage"),
        mime_type="application/json",
        tags={"recipe", "reference"},
    )
    async def recipe_cuisines(ctx: Context) -> str:
        """Return deduplicated, sorted list of cuisine areas."""
        client = _get_mealdb_client(ctx)
        service = _get_recipe_service(ctx)

        cuisines: set[str] = set()

        # TheMealDB areas
        try:
            areas = await client.list_areas()
            cuisines.update(areas)
        except ExternalAPIError:
            logger.warning("mealdb_cuisines_unavailable")

        # Local recipe areas
        local_recipes = await _collect_all_recipes(service)
        for recipe in local_recipes:
            area = recipe.get("area")
            if isinstance(area, str):
                cuisines.add(area)

        return json.dumps(sorted(cuisines))

    @mcp.resource(
        "recipe://ingredients",
        name="recipe_ingredients",
        description="Master ingredient list from TheMealDB and USDA",
        mime_type="application/json",
        tags={"recipe", "reference"},
    )
    async def recipe_ingredients(ctx: Context) -> str:
        """Return curated ingredient list from TheMealDB."""
        client = _get_mealdb_client(ctx)
        try:
            ingredients = await client.list_ingredients()
            return json.dumps(ingredients, default=str)
        except ExternalAPIError as exc:
            return json.dumps({"error": str(exc)})
