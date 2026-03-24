"""Recipe service with CRUD, multi-API search, scaling, and substitutions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import structlog

from recipe_mcp_server.clients.dummyjson import DummyJSONClient
from recipe_mcp_server.clients.foodish import FoodishClient
from recipe_mcp_server.clients.spoonacular import SpoonacularClient
from recipe_mcp_server.clients.themealdb import TheMealDBClient
from recipe_mcp_server.db.repository import FavoriteRepo, RecipeRepo
from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.models.common import PaginatedResponse
from recipe_mcp_server.models.recipe import (
    Recipe,
    RecipeCreate,
    RecipeSummary,
    RecipeUpdate,
    ScaledIngredient,
)
from recipe_mcp_server.models.user import Favorite

logger = structlog.get_logger(__name__)

ProgressCallback = Callable[[int, int, str], Awaitable[None]]

_PLACEHOLDER_IMAGE_URL = "https://via.placeholder.com/600x400?text=Recipe"

# ---------------------------------------------------------------------------
# Built-in ingredient substitution rules (fallback when Spoonacular fails)
# ---------------------------------------------------------------------------
_BUILT_IN_SUBSTITUTIONS: dict[str, list[str]] = {
    "butter": ["margarine", "coconut oil", "olive oil"],
    "eggs": ["flax eggs (1 tbsp ground flax + 3 tbsp water)", "applesauce (1/4 cup per egg)"],
    "milk": ["almond milk", "oat milk", "soy milk", "coconut milk"],
    "heavy cream": ["coconut cream", "cashew cream"],
    "sour cream": ["greek yogurt", "coconut cream"],
    "flour": ["almond flour", "coconut flour", "oat flour"],
    "sugar": ["honey", "maple syrup", "stevia"],
    "breadcrumbs": ["crushed crackers", "rolled oats", "cornmeal"],
    "soy sauce": ["coconut aminos", "tamari", "worcestershire sauce"],
    "lemon juice": ["lime juice", "white wine vinegar", "apple cider vinegar"],
}


def _normalize_title(title: str) -> str:
    """Normalize a recipe title for deduplication."""
    return title.strip().lower()


def _to_summary(recipe: Recipe) -> RecipeSummary:
    """Map a full Recipe to a RecipeSummary."""
    return RecipeSummary(
        id=recipe.source_id or recipe.id or "",
        title=recipe.title,
        category=recipe.category,
        area=recipe.area,
        image_url=recipe.image_url,
        source_api=recipe.source_api,
        difficulty=recipe.difficulty,
    )


def _deduplicate(results: list[RecipeSummary]) -> list[RecipeSummary]:
    """Keep first occurrence of each recipe by normalized title."""
    seen: set[str] = set()
    unique: list[RecipeSummary] = []
    for item in results:
        key = _normalize_title(item.title)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


class RecipeService:
    """Orchestrates recipe CRUD, multi-API search, scaling, and substitutions."""

    def __init__(
        self,
        *,
        recipe_repo: RecipeRepo,
        favorite_repo: FavoriteRepo,
        mealdb_client: TheMealDBClient,
        spoonacular_client: SpoonacularClient,
        dummyjson_client: DummyJSONClient,
        foodish_client: FoodishClient,
    ) -> None:
        self._recipe_repo = recipe_repo
        self._favorite_repo = favorite_repo
        self._mealdb_client = mealdb_client
        self._spoonacular_client = spoonacular_client
        self._dummyjson_client = dummyjson_client
        self._foodish_client = foodish_client

    # -- CRUD (delegates to RecipeRepo) -------------------------------------

    async def create(self, data: RecipeCreate) -> Recipe:
        """Create a new recipe in local storage."""
        return await self._recipe_repo.create(data)

    async def get(self, recipe_id: str) -> Recipe:
        """Get a recipe by ID. Raises NotFoundError if missing."""
        recipe = await self._recipe_repo.get(recipe_id)
        if recipe is None:
            raise NotFoundError(f"Recipe '{recipe_id}' not found")
        return recipe

    async def update(self, recipe_id: str, data: RecipeUpdate) -> Recipe:
        """Update a recipe. Raises NotFoundError if missing."""
        recipe = await self._recipe_repo.update(recipe_id, data)
        if recipe is None:
            raise NotFoundError(f"Recipe '{recipe_id}' not found")
        return recipe

    async def delete(self, recipe_id: str) -> bool:
        """Soft-delete a recipe."""
        return await self._recipe_repo.delete(recipe_id)

    async def list_recipes(
        self,
        cursor: str | None = None,
        limit: int = 50,
    ) -> PaginatedResponse[RecipeSummary]:
        """List recipes with cursor-based pagination."""
        return await self._recipe_repo.list_recipes(cursor=cursor, limit=limit)

    # -- Multi-API search with fallback chain -------------------------------

    async def search(
        self,
        query: str,
        *,
        cuisine: str | None = None,
        diet: str | None = None,
        limit: int = 10,
        on_progress: ProgressCallback | None = None,
    ) -> list[RecipeSummary]:
        """Search across TheMealDB, Spoonacular, DummyJSON, and local DB.

        Individual API failures are caught and logged; remaining sources
        still contribute results. Results are deduplicated by title.

        When *on_progress* is provided, APIs are called sequentially so
        progress can be reported after each one. Otherwise, they are
        called in parallel for speed.
        """

        async def _spoon() -> list[RecipeSummary]:
            return await self._search_spoonacular(query, cuisine=cuisine, diet=diet, limit=limit)

        api_searches: list[tuple[str, Callable[[], Awaitable[list[RecipeSummary]]]]] = [
            ("TheMealDB", lambda: self._search_mealdb(query)),
            ("Spoonacular", _spoon),
            ("DummyJSON", lambda: self._search_dummyjson(query)),
        ]

        if on_progress is not None:
            all_results: list[RecipeSummary] = []
            total = len(api_searches)
            for i, (name, search_fn) in enumerate(api_searches):
                await on_progress(i, total, f"Searching {name}...")
                all_results.extend(await search_fn())
            await on_progress(total, total, "Merging results...")
        else:
            mealdb_results, spoonacular_results, dummyjson_results = await asyncio.gather(
                self._search_mealdb(query),
                self._search_spoonacular(query, cuisine=cuisine, diet=diet, limit=limit),
                self._search_dummyjson(query),
            )
            all_results = mealdb_results + spoonacular_results + dummyjson_results

        local_results = await self._recipe_repo.search(
            query,
            cuisine=cuisine,
            limit=limit,
        )

        merged = all_results + local_results
        unique = _deduplicate(merged)
        return unique[:limit]

    async def _search_mealdb(self, query: str) -> list[RecipeSummary]:
        try:
            recipes = await self._mealdb_client.search_by_name(query)
            return [_to_summary(r) for r in recipes]
        except ExternalAPIError:
            logger.warning("mealdb_search_failed", query=query, exc_info=True)
            return []

    async def _search_spoonacular(
        self,
        query: str,
        *,
        cuisine: str | None = None,
        diet: str | None = None,
        limit: int = 10,
    ) -> list[RecipeSummary]:
        try:
            return await self._spoonacular_client.search_recipes(
                query,
                cuisine=cuisine or "",
                diet=diet or "",
                number=limit,
            )
        except ExternalAPIError:
            logger.warning("spoonacular_search_failed", query=query, exc_info=True)
            return []

    async def _search_dummyjson(self, query: str) -> list[RecipeSummary]:
        try:
            recipes = await self._dummyjson_client.search_recipes(query)
            return [_to_summary(r) for r in recipes]
        except ExternalAPIError:
            logger.warning("dummyjson_search_failed", query=query, exc_info=True)
            return []

    # -- Scaling ------------------------------------------------------------

    async def scale_recipe(
        self,
        recipe_id: str,
        target_servings: int,
    ) -> list[ScaledIngredient]:
        """Scale all ingredients in a recipe to *target_servings*."""
        if target_servings <= 0:
            msg = f"target_servings must be positive, got {target_servings}"
            raise ValueError(msg)

        recipe = await self.get(recipe_id)
        if recipe.servings <= 0:
            msg = f"Recipe '{recipe_id}' has invalid servings value: {recipe.servings}"
            raise ValueError(msg)

        scale_factor = target_servings / recipe.servings

        scaled: list[ScaledIngredient] = []
        for ing in recipe.ingredients:
            scaled.append(
                ScaledIngredient(
                    name=ing.name,
                    quantity=ing.quantity * scale_factor if ing.quantity is not None else None,
                    unit=ing.unit,
                    notes=ing.notes,
                    order_index=ing.order_index,
                    original_quantity=ing.quantity,
                    scale_factor=scale_factor,
                ),
            )
        return scaled

    # -- Substitutions (Spoonacular -> built-in rules) ----------------------

    async def get_substitutes(self, ingredient: str) -> list[str]:
        """Find substitutes for an ingredient.

        Falls back to built-in rules when the Spoonacular API is unavailable.
        """
        try:
            subs = await self._spoonacular_client.get_substitutes(ingredient)
            if subs:
                return subs
        except ExternalAPIError:
            logger.warning("spoonacular_substitutes_failed", ingredient=ingredient, exc_info=True)

        builtin = _BUILT_IN_SUBSTITUTIONS.get(ingredient.strip().lower(), [])
        if builtin:
            return builtin

        return []

    # -- Random recipe ------------------------------------------------------

    async def random_recipe(self) -> Recipe:
        """Get a random recipe from TheMealDB with a Foodish image overlay."""
        recipe = await self._mealdb_client.random_meal()
        if recipe is None:
            raise NotFoundError("No random recipe available")

        try:
            image_url = await self._foodish_client.random_image()
            if not image_url:
                image_url = recipe.image_url or _PLACEHOLDER_IMAGE_URL
        except ExternalAPIError:
            logger.warning("foodish_image_failed", exc_info=True)
            image_url = recipe.image_url or _PLACEHOLDER_IMAGE_URL

        recipe = recipe.model_copy(update={"image_url": image_url})
        return recipe

    # -- Favorites (delegates to FavoriteRepo) ------------------------------

    async def save_favorite(
        self,
        user_id: str,
        recipe_id: str,
        *,
        rating: int | None = None,
        notes: str | None = None,
    ) -> Favorite:
        """Save a recipe as a user favorite."""
        return await self._favorite_repo.save(
            user_id,
            recipe_id,
            rating=rating,
            notes=notes,
        )

    async def list_favorites(self, user_id: str) -> list[Favorite]:
        """List a user's favorite recipes."""
        return await self._favorite_repo.list_for_user(user_id)

    async def remove_favorite(self, user_id: str, recipe_id: str) -> bool:
        """Remove a recipe from a user's favorites."""
        return await self._favorite_repo.remove(user_id, recipe_id)
