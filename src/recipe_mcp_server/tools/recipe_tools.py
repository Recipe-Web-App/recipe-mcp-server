"""Recipe CRUD, search, scaling, substitution, and favorites tools."""

from __future__ import annotations

import json
from typing import cast

import structlog
from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.models.recipe import Ingredient, RecipeCreate, RecipeUpdate
from recipe_mcp_server.services.recipe_service import RecipeService

logger = structlog.get_logger(__name__)


def _get_recipe_service(ctx: Context) -> RecipeService:
    """Extract RecipeService from the lifespan context."""
    return cast(RecipeService, ctx.lifespan_context["recipe_service"])


def register_recipe_tools(mcp: FastMCP) -> None:
    """Register all recipe tools on the given FastMCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        tags={"recipe"},
    )
    async def search_recipes(
        ctx: Context,
        query: str,
        cuisine: str | None = None,
        diet: str | None = None,
        limit: int = 10,
    ) -> str:
        """Search for recipes across multiple sources.

        Args:
            query: Search term (e.g. "chicken curry").
            cuisine: Optional cuisine filter (e.g. "Italian").
            diet: Optional dietary filter (e.g. "vegetarian").
            limit: Maximum number of results (default 10).
        """
        await ctx.info(
            f"Searching recipes: query='{query}', cuisine={cuisine}, diet={diet}, limit={limit}"
        )
        service = _get_recipe_service(ctx)
        try:
            results = await service.search(
                query,
                cuisine=cuisine,
                diet=diet,
                limit=limit,
                on_progress=lambda c, t, m: ctx.report_progress(c, t, m),
            )
            await ctx.debug(f"Found {len(results)} results for query='{query}'")
            await ctx.set_state(
                "last_search",
                {"query": query, "result_ids": [r.id for r in results]},
            )
            return json.dumps([r.model_dump() for r in results], default=str)
        except ExternalAPIError as exc:
            await ctx.error(f"All recipe APIs failed for query='{query}': {exc}")
            return f"Error searching recipes: {exc}"

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True),
        tags={"recipe"},
    )
    async def get_recipe(
        ctx: Context,
        recipe_id: str,
        include_variations: bool = False,
    ) -> str:
        """Get a recipe by its ID, optionally with AI-generated variations.

        Args:
            recipe_id: The unique recipe identifier.
            include_variations: If true, include AI-suggested recipe variations
                via sampling (fusion twist, seasonal adaptation, simplified).
        """
        await ctx.info(f"Getting recipe: id='{recipe_id}', include_variations={include_variations}")
        service = _get_recipe_service(ctx)
        try:
            recipe = await service.get(recipe_id)
            data = recipe.model_dump()

            if include_variations:
                await ctx.debug(f"Requesting AI-generated variations for recipe '{recipe_id}'")
                from recipe_mcp_server.sampling.handlers import suggest_recipe_variations

                variations_text = await suggest_recipe_variations(ctx, recipe)
                data["variations"] = variations_text

            return json.dumps(data, default=str)
        except NotFoundError as exc:
            await ctx.warning(f"Recipe not found: '{recipe_id}'")
            return f"Error: {exc}"

    @mcp.tool(tags={"recipe"})
    async def create_recipe(
        ctx: Context,
        title: str,
        description: str | None = None,
        instructions: list[str] | None = None,
        category: str | None = None,
        area: str | None = None,
        image_url: str | None = None,
        source_url: str | None = None,
        prep_time_min: int | None = None,
        cook_time_min: int | None = None,
        servings: int = 4,
        tags: list[str] | None = None,
        ingredients_json: str | None = None,
    ) -> str:
        """Create a new recipe.

        Args:
            title: Recipe title.
            description: Optional description.
            instructions: List of instruction steps.
            category: Recipe category (e.g. "Dessert").
            area: Cuisine area (e.g. "Italian").
            image_url: URL of recipe image.
            source_url: Original source URL.
            prep_time_min: Preparation time in minutes.
            cook_time_min: Cooking time in minutes.
            servings: Number of servings (default 4).
            tags: Optional list of tags.
            ingredients_json: JSON array of ingredients, each with name, quantity, unit, notes.
        """
        await ctx.info(f"Creating recipe: title='{title}'")
        service = _get_recipe_service(ctx)

        ingredients: list[Ingredient] = []
        if ingredients_json:
            try:
                raw = json.loads(ingredients_json)
                ingredients = [Ingredient(**item) for item in raw]
            except (json.JSONDecodeError, TypeError) as exc:
                await ctx.error(f"Invalid ingredients_json format: {exc}")
                return f"Error: Invalid ingredients_json format: {exc}"

        data = RecipeCreate(
            title=title,
            description=description,
            instructions=instructions or [],
            category=category,
            area=area,
            image_url=image_url,
            source_url=source_url,
            prep_time_min=prep_time_min,
            cook_time_min=cook_time_min,
            servings=servings,
            tags=tags or [],
            ingredients=ingredients,
        )
        recipe = await service.create(data)
        await ctx.debug(f"Created recipe with id='{recipe.id}'")
        return recipe.model_dump_json()

    @mcp.tool(
        annotations=ToolAnnotations(idempotentHint=True),
        tags={"recipe"},
    )
    async def update_recipe(
        ctx: Context,
        recipe_id: str,
        title: str | None = None,
        description: str | None = None,
        instructions: list[str] | None = None,
        category: str | None = None,
        area: str | None = None,
        image_url: str | None = None,
        source_url: str | None = None,
        prep_time_min: int | None = None,
        cook_time_min: int | None = None,
        servings: int | None = None,
        tags: list[str] | None = None,
        ingredients_json: str | None = None,
    ) -> str:
        """Update an existing recipe. Only provided fields are changed.

        Args:
            recipe_id: The recipe to update.
            title: New title.
            description: New description.
            instructions: New instruction steps.
            category: New category.
            area: New cuisine area.
            image_url: New image URL.
            source_url: New source URL.
            prep_time_min: New prep time.
            cook_time_min: New cook time.
            servings: New servings count.
            tags: New tags list.
            ingredients_json: JSON array of updated ingredients.
        """
        await ctx.info(f"Updating recipe: id='{recipe_id}'")
        service = _get_recipe_service(ctx)

        ingredients: list[Ingredient] | None = None
        if ingredients_json is not None:
            try:
                raw = json.loads(ingredients_json)
                ingredients = [Ingredient(**item) for item in raw]
            except (json.JSONDecodeError, TypeError) as exc:
                await ctx.error(f"Invalid ingredients_json format: {exc}")
                return f"Error: Invalid ingredients_json format: {exc}"

        data = RecipeUpdate(
            title=title,
            description=description,
            instructions=instructions,
            category=category,
            area=area,
            image_url=image_url,
            source_url=source_url,
            prep_time_min=prep_time_min,
            cook_time_min=cook_time_min,
            servings=servings,
            tags=tags,
            ingredients=ingredients,
        )
        try:
            recipe = await service.update(recipe_id, data)
            await ctx.debug(f"Updated recipe '{recipe_id}'")
            return recipe.model_dump_json()
        except NotFoundError as exc:
            await ctx.warning(f"Recipe not found for update: '{recipe_id}'")
            return f"Error: {exc}"

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=True),
        tags={"recipe"},
    )
    async def delete_recipe(ctx: Context, recipe_id: str) -> str:
        """Delete a recipe (soft-delete).

        Args:
            recipe_id: The recipe to delete.
        """
        await ctx.info(f"Deleting recipe: id='{recipe_id}'")
        service = _get_recipe_service(ctx)
        deleted = await service.delete(recipe_id)
        if not deleted:
            await ctx.warning(f"Recipe not found for deletion: '{recipe_id}'")
            return f"Error: Recipe '{recipe_id}' not found"
        await ctx.debug(f"Deleted recipe '{recipe_id}'")
        return json.dumps({"deleted": True, "recipe_id": recipe_id})

    @mcp.tool(tags={"recipe", "utility"})
    async def scale_recipe(
        ctx: Context,
        recipe_id: str,
        target_servings: int,
    ) -> str:
        """Scale recipe ingredients to a target number of servings.

        Args:
            recipe_id: The recipe to scale.
            target_servings: Desired number of servings.
        """
        await ctx.info(f"Scaling recipe: id='{recipe_id}', target_servings={target_servings}")
        service = _get_recipe_service(ctx)
        try:
            scaled = await service.scale_recipe(recipe_id, target_servings)
            await ctx.debug(f"Scaled {len(scaled)} ingredients for recipe '{recipe_id}'")
            return json.dumps([s.model_dump() for s in scaled], default=str)
        except NotFoundError as exc:
            await ctx.warning(f"Recipe not found for scaling: '{recipe_id}'")
            return f"Error: {exc}"
        except ValueError as exc:
            await ctx.error(f"Scaling error: {exc}")
            return f"Error: {exc}"

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True),
        tags={"recipe", "utility"},
    )
    async def get_substitutes(ctx: Context, ingredient: str) -> str:
        """Find substitutes for an ingredient.

        Args:
            ingredient: The ingredient to find substitutes for (e.g. "butter").
        """
        await ctx.info(f"Finding substitutes for: '{ingredient}'")
        service = _get_recipe_service(ctx)
        try:
            subs = await service.get_substitutes(ingredient)
            await ctx.debug(f"Found {len(subs)} substitutes for '{ingredient}'")
            return json.dumps(subs)
        except ExternalAPIError as exc:
            await ctx.error(f"Failed to find substitutes for '{ingredient}': {exc}")
            return f"Error finding substitutes: {exc}"

    @mcp.tool(
        annotations=ToolAnnotations(idempotentHint=True),
        tags={"recipe"},
    )
    async def save_favorite(
        ctx: Context,
        user_id: str,
        recipe_id: str,
        rating: int | None = None,
        notes: str | None = None,
    ) -> str:
        """Save a recipe as a user's favorite.

        Args:
            user_id: The user saving the favorite.
            recipe_id: The recipe to favorite.
            rating: Optional rating from 1 to 5.
            notes: Optional notes about the recipe.
        """
        await ctx.info(f"Saving favorite: user='{user_id}', recipe='{recipe_id}'")
        service = _get_recipe_service(ctx)
        favorite = await service.save_favorite(user_id, recipe_id, rating=rating, notes=notes)
        await ctx.debug(f"Saved favorite for user '{user_id}', recipe '{recipe_id}'")
        return favorite.model_dump_json()

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True),
        tags={"recipe", "creative"},
    )
    async def get_random_recipe(ctx: Context) -> str:
        """Get a random recipe for inspiration."""
        await ctx.info("Getting random recipe")
        service = _get_recipe_service(ctx)
        try:
            recipe = await service.random_recipe()
            await ctx.debug(f"Random recipe selected: '{recipe.title}'")
            return recipe.model_dump_json()
        except (NotFoundError, ExternalAPIError) as exc:
            await ctx.error(f"Failed to get random recipe: {exc}")
            return f"Error getting random recipe: {exc}"

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True),
        tags={"recipe"},
    )
    async def list_favorites(ctx: Context, user_id: str) -> str:
        """List a user's favorite recipes.

        Args:
            user_id: The user whose favorites to list.
        """
        await ctx.info(f"Listing favorites for user: '{user_id}'")
        service = _get_recipe_service(ctx)
        favorites = await service.list_favorites(user_id)
        await ctx.debug(f"Found {len(favorites)} favorites for user '{user_id}'")
        return json.dumps([f.model_dump() for f in favorites], default=str)
