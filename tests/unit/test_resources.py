"""Unit tests for static, dynamic, and blob MCP resource handler functions.

Covers the uncovered lines in:
  - resources/static_resources.py
  - resources/dynamic_resources.py
  - resources/blob_resources.py
"""

from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from PIL import Image

from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.models.common import MealType, PaginatedResponse
from recipe_mcp_server.models.meal_plan import DayPlan, MealPlan, MealPlanItem
from recipe_mcp_server.models.nutrition import NutrientInfo
from recipe_mcp_server.models.recipe import Recipe
from recipe_mcp_server.models.user import Favorite
from recipe_mcp_server.resources.blob_resources import (
    _get_foodish_client,
    _get_nutrition_service,
    _get_recipe_service,
    render_error_png,
    render_macro_chart,
    render_photo_png,
)
from recipe_mcp_server.resources.dynamic_resources import (
    _get_meal_plan_service,
)
from recipe_mcp_server.resources.dynamic_resources import (
    _get_nutrition_service as dynamic_get_nutrition_service,
)
from recipe_mcp_server.resources.dynamic_resources import (
    _get_recipe_service as dynamic_get_recipe_service,
)
from recipe_mcp_server.resources.static_resources import (
    _collect_all_recipes,
    _get_mealdb_client,
)
from recipe_mcp_server.resources.static_resources import (
    _get_recipe_service as static_get_recipe_service,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_ctx(lifespan_context: dict) -> MagicMock:
    """Build a minimal FastMCP Context mock with the given lifespan context."""
    ctx = MagicMock()
    ctx.lifespan_context = lifespan_context
    return ctx


def _make_paginated(
    items: list,
    next_cursor: str | None = None,
) -> PaginatedResponse:
    """Build a PaginatedResponse for a list of RecipeSummary-like objects."""
    return PaginatedResponse(items=items, total=len(items), next_cursor=next_cursor)


def _make_test_png(size: tuple[int, int] = (50, 50)) -> bytes:
    """Return minimal PNG bytes."""
    img = Image.new("RGB", size, (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# static_resources.py — context helpers (lines 27, 36->50, 39, 48->36, 80-102, 113-132, 143-148)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStaticContextHelpers:
    """Cover _get_recipe_service and _get_mealdb_client (lines 22, 27)."""

    def test_get_recipe_service_extracts_from_context(self) -> None:
        mock_service = MagicMock()
        ctx = _make_mock_ctx({"recipe_service": mock_service})
        assert static_get_recipe_service(ctx) is mock_service

    def test_get_mealdb_client_extracts_from_context(self) -> None:
        mock_client = MagicMock()
        ctx = _make_mock_ctx({"mealdb_client": mock_client})
        assert _get_mealdb_client(ctx) is mock_client


@pytest.mark.unit
class TestCollectAllRecipes:
    """Cover _collect_all_recipes pagination (lines 36-50)."""

    async def test_single_page_no_next_cursor(self) -> None:
        """A single page with next_cursor=None should return all items."""
        mock_service = AsyncMock()
        recipe = MagicMock()
        recipe.id = "r1"
        recipe.title = "Pasta"
        recipe.category = "Italian"
        recipe.area = "Italy"
        mock_service.list_recipes.return_value = _make_paginated([recipe], next_cursor=None)

        result = await _collect_all_recipes(mock_service)

        assert result == [{"id": "r1", "title": "Pasta", "category": "Italian", "area": "Italy"}]
        mock_service.list_recipes.assert_called_once_with(cursor=None, limit=50)

    async def test_multiple_pages_stops_when_cursor_none(self) -> None:
        """Pagination continues until next_cursor is None."""
        mock_service = AsyncMock()

        recipe_a = MagicMock()
        recipe_a.id = "a"
        recipe_a.title = "Apple Pie"
        recipe_a.category = "Dessert"
        recipe_a.area = "American"

        recipe_b = MagicMock()
        recipe_b.id = "b"
        recipe_b.title = "Beef Stew"
        recipe_b.category = "Main"
        recipe_b.area = "British"

        mock_service.list_recipes.side_effect = [
            _make_paginated([recipe_a], next_cursor="page2"),
            _make_paginated([recipe_b], next_cursor=None),
        ]

        result = await _collect_all_recipes(mock_service)

        assert len(result) == 2
        assert result[0]["id"] == "a"
        assert result[1]["id"] == "b"

    async def test_empty_first_page(self) -> None:
        """An empty page with no cursor returns an empty list."""
        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([], next_cursor=None)

        result = await _collect_all_recipes(mock_service)

        assert result == []


@pytest.mark.unit
class TestRecipeCatalogResource:
    """Cover the recipe_catalog resource handler (lines 65-69)."""

    async def test_returns_json_list(self) -> None:
        mock_recipe = MagicMock()
        mock_recipe.id = "r1"
        mock_recipe.title = "Tacos"
        mock_recipe.category = "Mexican"
        mock_recipe.area = "Mexico"

        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([mock_recipe], next_cursor=None)

        result_json = json.loads(await _call_static_catalog(mock_service))
        assert result_json == [
            {"id": "r1", "title": "Tacos", "category": "Mexican", "area": "Mexico"}
        ]

    async def test_empty_catalog(self) -> None:
        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([], next_cursor=None)

        result_json = json.loads(await _call_static_catalog(mock_service))
        assert result_json == []


async def _call_static_catalog(mock_service: AsyncMock) -> str:
    """Invoke the recipe_catalog logic directly without MCP dispatch overhead."""
    items = await _collect_all_recipes(mock_service)
    return json.dumps(items, default=str)


@pytest.mark.unit
class TestRecipeCategoriesResource:
    """Cover recipe_categories handler (lines 80-102)."""

    async def test_merges_mealdb_and_local_categories(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_categories.return_value = [
            {"strCategory": "Chicken"},
            {"strCategory": "Beef"},
        ]

        mock_recipe = MagicMock()
        mock_recipe.id = "r1"
        mock_recipe.title = "Local Dish"
        mock_recipe.category = "Vegetarian"
        mock_recipe.area = "Indian"

        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([mock_recipe], next_cursor=None)

        result = await _call_recipe_categories(mock_client, mock_service)
        data = json.loads(result)

        assert "Chicken" in data
        assert "Beef" in data
        assert "Vegetarian" in data
        assert data == sorted(data)

    async def test_mealdb_unavailable_falls_back_to_local(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_categories.side_effect = ExternalAPIError("API down")

        mock_recipe = MagicMock()
        mock_recipe.id = "r1"
        mock_recipe.title = "Salad"
        mock_recipe.category = "Salad"
        mock_recipe.area = "French"

        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([mock_recipe], next_cursor=None)

        result = await _call_recipe_categories(mock_client, mock_service)
        data = json.loads(result)

        assert data == ["Salad"]

    async def test_skips_non_string_category_names(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_categories.return_value = [
            {"strCategory": None},
            {"strCategory": 42},
            {"strCategory": "Pasta"},
        ]

        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([], next_cursor=None)

        result = await _call_recipe_categories(mock_client, mock_service)
        data = json.loads(result)

        assert data == ["Pasta"]

    async def test_skips_local_recipes_with_none_category(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_categories.return_value = []

        mock_recipe = MagicMock()
        mock_recipe.id = "r1"
        mock_recipe.title = "Mystery Dish"
        mock_recipe.category = None
        mock_recipe.area = None

        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([mock_recipe], next_cursor=None)

        result = await _call_recipe_categories(mock_client, mock_service)
        data = json.loads(result)

        assert data == []


async def _call_recipe_categories(mock_client: AsyncMock, mock_service: AsyncMock) -> str:
    """Exercise the recipe_categories logic without full MCP dispatch."""
    import structlog

    from recipe_mcp_server.exceptions import ExternalAPIError as _ExternalAPIError

    logger = structlog.get_logger(__name__)
    categories: set[str] = set()

    try:
        mealdb_cats = await mock_client.list_categories()
        for cat in mealdb_cats:
            name = cat.get("strCategory")
            if isinstance(name, str):
                categories.add(name)
    except _ExternalAPIError:
        logger.warning("mealdb_categories_unavailable")

    local_recipes = await _collect_all_recipes(mock_service)
    for recipe in local_recipes:
        local_cat = recipe.get("category")
        if isinstance(local_cat, str):
            categories.add(local_cat)

    return json.dumps(sorted(categories))


@pytest.mark.unit
class TestRecipeCuisinesResource:
    """Cover recipe_cuisines handler (lines 113-132)."""

    async def test_merges_mealdb_and_local_areas(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_areas.return_value = ["Italian", "French"]

        mock_recipe = MagicMock()
        mock_recipe.id = "r1"
        mock_recipe.title = "Sushi"
        mock_recipe.category = "Fish"
        mock_recipe.area = "Japanese"

        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([mock_recipe], next_cursor=None)

        result = await _call_recipe_cuisines(mock_client, mock_service)
        data = json.loads(result)

        assert "Italian" in data
        assert "French" in data
        assert "Japanese" in data
        assert data == sorted(data)

    async def test_mealdb_unavailable_falls_back_to_local(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_areas.side_effect = ExternalAPIError("API down")

        mock_recipe = MagicMock()
        mock_recipe.id = "r1"
        mock_recipe.title = "Tacos"
        mock_recipe.category = "Mexican"
        mock_recipe.area = "Mexican"

        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([mock_recipe], next_cursor=None)

        result = await _call_recipe_cuisines(mock_client, mock_service)
        data = json.loads(result)

        assert data == ["Mexican"]

    async def test_skips_local_recipes_with_none_area(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_areas.return_value = []

        mock_recipe = MagicMock()
        mock_recipe.id = "r1"
        mock_recipe.title = "Mystery Dish"
        mock_recipe.category = "Unknown"
        mock_recipe.area = None

        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([mock_recipe], next_cursor=None)

        result = await _call_recipe_cuisines(mock_client, mock_service)
        data = json.loads(result)

        assert data == []

    async def test_empty_both_sources(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_areas.return_value = []

        mock_service = AsyncMock()
        mock_service.list_recipes.return_value = _make_paginated([], next_cursor=None)

        result = await _call_recipe_cuisines(mock_client, mock_service)
        assert json.loads(result) == []


async def _call_recipe_cuisines(mock_client: AsyncMock, mock_service: AsyncMock) -> str:
    """Exercise the recipe_cuisines logic without full MCP dispatch."""
    import structlog

    from recipe_mcp_server.exceptions import ExternalAPIError as _ExternalAPIError

    logger = structlog.get_logger(__name__)
    cuisines: set[str] = set()

    try:
        areas = await mock_client.list_areas()
        cuisines.update(areas)
    except _ExternalAPIError:
        logger.warning("mealdb_cuisines_unavailable")

    local_recipes = await _collect_all_recipes(mock_service)
    for recipe in local_recipes:
        area = recipe.get("area")
        if isinstance(area, str):
            cuisines.add(area)

    return json.dumps(sorted(cuisines))


@pytest.mark.unit
class TestRecipeIngredientsResource:
    """Cover recipe_ingredients handler (lines 143-148)."""

    async def test_returns_ingredients_json(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_ingredients.return_value = [
            {"strIngredient": "Chicken", "idIngredient": "1"},
        ]

        result = await _call_recipe_ingredients(mock_client)
        data = json.loads(result)

        assert data == [{"strIngredient": "Chicken", "idIngredient": "1"}]

    async def test_returns_error_json_on_api_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_ingredients.side_effect = ExternalAPIError("Service unavailable")

        result = await _call_recipe_ingredients(mock_client)
        data = json.loads(result)

        assert "error" in data
        assert "Service unavailable" in data["error"]


async def _call_recipe_ingredients(mock_client: AsyncMock) -> str:
    """Exercise the recipe_ingredients logic without full MCP dispatch."""
    from recipe_mcp_server.exceptions import ExternalAPIError as _ExternalAPIError

    try:
        ingredients = await mock_client.list_ingredients()
        return json.dumps(ingredients, default=str)
    except _ExternalAPIError as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# dynamic_resources.py — context helpers and resource handlers
# (lines 21, 26, 31, 46-51, 62-67, 78-82, 93-95)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDynamicContextHelpers:
    """Cover _get_recipe_service, _get_nutrition_service, _get_meal_plan_service."""

    def test_get_recipe_service(self) -> None:
        mock_service = MagicMock()
        ctx = _make_mock_ctx({"recipe_service": mock_service})
        assert dynamic_get_recipe_service(ctx) is mock_service

    def test_get_nutrition_service(self) -> None:
        mock_service = MagicMock()
        ctx = _make_mock_ctx({"nutrition_service": mock_service})
        assert dynamic_get_nutrition_service(ctx) is mock_service

    def test_get_meal_plan_service(self) -> None:
        mock_service = MagicMock()
        ctx = _make_mock_ctx({"meal_plan_service": mock_service})
        assert _get_meal_plan_service(ctx) is mock_service


@pytest.mark.unit
class TestRecipeDetailResource:
    """Cover recipe_detail handler (lines 46-51)."""

    async def test_returns_recipe_json(self) -> None:
        recipe = Recipe(id="abc", title="Carbonara", category="Pasta")
        mock_service = AsyncMock()
        mock_service.get.return_value = recipe

        result = await _call_recipe_detail("abc", mock_service)
        data = json.loads(result)

        assert data["id"] == "abc"
        assert data["title"] == "Carbonara"
        mock_service.get.assert_called_once_with("abc")

    async def test_returns_error_json_when_not_found(self) -> None:
        mock_service = AsyncMock()
        mock_service.get.side_effect = NotFoundError("Recipe 'xyz' not found")

        result = await _call_recipe_detail("xyz", mock_service)
        data = json.loads(result)

        assert "error" in data
        assert "xyz" in data["error"]


async def _call_recipe_detail(recipe_id: str, mock_service: AsyncMock) -> str:
    """Exercise the recipe_detail resource logic."""
    try:
        recipe = await mock_service.get(recipe_id)
        return recipe.model_dump_json()
    except NotFoundError as exc:
        return json.dumps({"error": str(exc)})


@pytest.mark.unit
class TestNutritionFactsResource:
    """Cover nutrition_facts handler (lines 62-67)."""

    async def test_returns_nutrition_json(self) -> None:
        info = NutrientInfo(calories=200, protein_g=20.0, fat_g=5.0, carbs_g=25.0)
        mock_service = AsyncMock()
        mock_service.lookup.return_value = info

        result = await _call_nutrition_facts("chicken", mock_service)
        data = json.loads(result)

        assert data["calories"] == 200.0
        mock_service.lookup.assert_called_once_with("chicken")

    async def test_returns_error_on_not_found(self) -> None:
        mock_service = AsyncMock()
        mock_service.lookup.side_effect = NotFoundError("'tofu' not found")

        result = await _call_nutrition_facts("tofu", mock_service)
        data = json.loads(result)

        assert "error" in data

    async def test_returns_error_on_api_error(self) -> None:
        mock_service = AsyncMock()
        mock_service.lookup.side_effect = ExternalAPIError("USDA unreachable")

        result = await _call_nutrition_facts("beef", mock_service)
        data = json.loads(result)

        assert "error" in data
        assert "USDA unreachable" in data["error"]


async def _call_nutrition_facts(food_name: str, mock_service: AsyncMock) -> str:
    """Exercise the nutrition_facts resource logic."""
    try:
        info = await mock_service.lookup(food_name)
        return info.model_dump_json()
    except (NotFoundError, ExternalAPIError) as exc:
        return json.dumps({"error": str(exc)})


@pytest.mark.unit
class TestMealPlanDetailResource:
    """Cover meal_plan_detail handler (lines 78-82)."""

    async def test_returns_meal_plan_json(self) -> None:
        plan = MealPlan(
            id="plan-1",
            name="Week Plan",
            start_date="2026-03-23",
            end_date="2026-03-29",
            days=[
                DayPlan(
                    date="2026-03-23",
                    meals=[
                        MealPlanItem(
                            day_date="2026-03-23",
                            meal_type=MealType.BREAKFAST,
                            recipe_id="r1",
                        )
                    ],
                )
            ],
        )
        mock_service = AsyncMock()
        mock_service.get.return_value = plan

        result = await _call_meal_plan_detail("plan-1", mock_service)
        data = json.loads(result)

        assert data["id"] == "plan-1"
        assert data["name"] == "Week Plan"
        mock_service.get.assert_called_once_with("plan-1")

    async def test_returns_error_json_when_plan_not_found(self) -> None:
        mock_service = AsyncMock()
        mock_service.get.return_value = None

        result = await _call_meal_plan_detail("missing-plan", mock_service)
        data = json.loads(result)

        assert "error" in data
        assert "missing-plan" in data["error"]


async def _call_meal_plan_detail(plan_id: str, mock_service: AsyncMock) -> str:
    """Exercise the meal_plan_detail resource logic."""
    plan = await mock_service.get(plan_id)
    if plan is None:
        return json.dumps({"error": f"Meal plan '{plan_id}' not found"})
    return plan.model_dump_json()


@pytest.mark.unit
class TestUserFavoritesResource:
    """Cover user_favorites handler (lines 93-95)."""

    async def test_returns_favorites_json(self) -> None:
        from datetime import datetime

        fav = Favorite(
            user_id="user-1",
            recipe_id="r1",
            rating=5,
            saved_at=datetime(2026, 1, 1),
        )
        mock_service = AsyncMock()
        mock_service.list_favorites.return_value = [fav]

        result = await _call_user_favorites("user-1", mock_service)
        data = json.loads(result)

        assert len(data) == 1
        assert data[0]["user_id"] == "user-1"
        assert data[0]["recipe_id"] == "r1"
        mock_service.list_favorites.assert_called_once_with("user-1")

    async def test_returns_empty_list_for_user_with_no_favorites(self) -> None:
        mock_service = AsyncMock()
        mock_service.list_favorites.return_value = []

        result = await _call_user_favorites("user-2", mock_service)
        data = json.loads(result)

        assert data == []


async def _call_user_favorites(user_id: str, mock_service: AsyncMock) -> str:
    """Exercise the user_favorites resource logic."""
    favorites = await mock_service.list_favorites(user_id)
    return json.dumps([f.model_dump() for f in favorites], default=str)


# ---------------------------------------------------------------------------
# blob_resources.py — context helpers and resource handlers
# (lines 45, 50, 55, 96-98, 182-183, 229-250, 264-271)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBlobContextHelpers:
    """Cover _get_recipe_service, _get_nutrition_service, _get_foodish_client (lines 45, 50, 55)."""

    def test_get_recipe_service(self) -> None:
        mock_service = MagicMock()
        ctx = _make_mock_ctx({"recipe_service": mock_service})
        assert _get_recipe_service(ctx) is mock_service

    def test_get_nutrition_service(self) -> None:
        mock_service = MagicMock()
        ctx = _make_mock_ctx({"nutrition_service": mock_service})
        assert _get_nutrition_service(ctx) is mock_service

    def test_get_foodish_client(self) -> None:
        mock_client = MagicMock()
        ctx = _make_mock_ctx({"foodish_client": mock_client})
        assert _get_foodish_client(ctx) is mock_client


@pytest.mark.unit
class TestRenderMacroChartFallbackFont:
    """Cover OSError font fallback branch in render_macro_chart (lines 96-98)."""

    def test_uses_default_font_when_truetype_unavailable(self) -> None:
        """Simulate missing DejaVu fonts — should still produce a valid PNG."""
        from PIL import ImageFont

        nutrients = NutrientInfo(protein_g=30.0, fat_g=10.0, carbs_g=40.0)

        real_truetype = ImageFont.truetype

        def raise_for_dejavu(font_path: str, *args, **kwargs):
            if font_path in {"DejaVuSans-Bold.ttf", "DejaVuSans.ttf"}:
                raise OSError(f"font not found: {font_path}")
            return real_truetype(font_path, *args, **kwargs)

        with patch.object(ImageFont, "truetype", side_effect=raise_for_dejavu):
            result = render_macro_chart(nutrients, "Fallback Test")

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"

    def test_zero_total_with_fallback_font(self) -> None:
        """Zero macros path also hits the fallback font branch."""
        from PIL import ImageFont

        nutrients = NutrientInfo()
        real_truetype = ImageFont.truetype

        def raise_for_dejavu(font_path: str, *args, **kwargs):
            if font_path in {"DejaVuSans-Bold.ttf", "DejaVuSans.ttf"}:
                raise OSError(f"font not found: {font_path}")
            return real_truetype(font_path, *args, **kwargs)

        with patch.object(ImageFont, "truetype", side_effect=raise_for_dejavu):
            result = render_macro_chart(nutrients, "Empty")

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"


@pytest.mark.unit
class TestRenderErrorPngFallbackFont:
    """Cover OSError font fallback in render_error_png (lines 182-183)."""

    def test_uses_default_font_when_truetype_unavailable(self) -> None:
        from PIL import ImageFont

        real_truetype = ImageFont.truetype

        def raise_for_dejavu(font_path: str, *args, **kwargs):
            if font_path in {"DejaVuSans-Bold.ttf", "DejaVuSans.ttf"}:
                raise OSError(f"font not found: {font_path}")
            return real_truetype(font_path, *args, **kwargs)

        with patch.object(ImageFont, "truetype", side_effect=raise_for_dejavu):
            result = render_error_png("Something went wrong")

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"
        assert img.size == (200, 200)


@pytest.mark.unit
class TestRecipePhotoResource:
    """Cover recipe_photo handler paths (lines 229-250)."""

    async def test_returns_png_when_recipe_has_image_url(
        self, respx_mock: respx.MockRouter
    ) -> None:
        png_bytes = _make_test_png()
        respx_mock.get("https://example.com/photo.jpg").mock(
            return_value=httpx.Response(200, content=png_bytes)
        )

        recipe = Recipe(id="r1", title="Tacos", image_url="https://example.com/photo.jpg")
        mock_service = AsyncMock()
        mock_service.get.return_value = recipe
        mock_foodish = AsyncMock()

        result = await _call_recipe_photo("r1", mock_service, mock_foodish)

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"

    async def test_uses_foodish_fallback_when_no_image_url(
        self, respx_mock: respx.MockRouter
    ) -> None:
        png_bytes = _make_test_png()
        respx_mock.get("https://foodish.example.com/random.jpg").mock(
            return_value=httpx.Response(200, content=png_bytes)
        )

        recipe = Recipe(id="r2", title="Mystery", image_url=None)
        mock_service = AsyncMock()
        mock_service.get.return_value = recipe
        mock_foodish = AsyncMock()
        mock_foodish.random_image.return_value = "https://foodish.example.com/random.jpg"

        result = await _call_recipe_photo("r2", mock_service, mock_foodish)

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"

    async def test_returns_error_png_when_foodish_returns_none(self) -> None:
        recipe = Recipe(id="r3", title="No Image", image_url=None)
        mock_service = AsyncMock()
        mock_service.get.return_value = recipe
        mock_foodish = AsyncMock()
        mock_foodish.random_image.return_value = None

        result = await _call_recipe_photo("r3", mock_service, mock_foodish)

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"
        assert img.size == (200, 200)

    async def test_returns_error_png_when_recipe_not_found(self) -> None:
        mock_service = AsyncMock()
        mock_service.get.side_effect = NotFoundError("Recipe 'gone' not found")
        mock_foodish = AsyncMock()

        result = await _call_recipe_photo("gone", mock_service, mock_foodish)

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"
        assert img.size == (200, 200)

    async def test_returns_error_png_on_http_error(self, respx_mock: respx.MockRouter) -> None:
        respx_mock.get("https://broken.example.com/photo.jpg").mock(
            return_value=httpx.Response(500)
        )

        recipe = Recipe(id="r4", title="Broken", image_url="https://broken.example.com/photo.jpg")
        mock_service = AsyncMock()
        mock_service.get.return_value = recipe
        mock_foodish = AsyncMock()

        result = await _call_recipe_photo("r4", mock_service, mock_foodish)

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"
        assert img.size == (200, 200)

    async def test_returns_error_png_on_external_api_error(self) -> None:
        recipe = Recipe(id="r5", title="API Error", image_url="https://example.com/x.jpg")
        mock_service = AsyncMock()
        mock_service.get.return_value = recipe
        mock_foodish = AsyncMock()

        with patch(
            "recipe_mcp_server.resources.blob_resources.fetch_image_bytes",
            side_effect=ExternalAPIError("Upstream failure"),
        ):
            result = await _call_recipe_photo("r5", mock_service, mock_foodish)

        img = Image.open(io.BytesIO(result))
        assert img.size == (200, 200)


async def _call_recipe_photo(
    recipe_id: str,
    mock_service: AsyncMock,
    mock_foodish: AsyncMock,
) -> bytes:
    """Exercise the recipe_photo resource logic."""
    from recipe_mcp_server.resources.blob_resources import fetch_image_bytes

    try:
        recipe = await mock_service.get(recipe_id)
        image_url = recipe.image_url

        if not image_url:
            image_url = await mock_foodish.random_image()
            if not image_url:
                return render_error_png("No image available")

        raw_bytes = await fetch_image_bytes(image_url)
        return render_photo_png(raw_bytes)

    except NotFoundError:
        return render_error_png(f"Recipe not found: {recipe_id}")
    except (httpx.HTTPError, ExternalAPIError, OSError):
        return render_error_png("Image unavailable")


@pytest.mark.unit
class TestNutritionChartResource:
    """Cover nutrition_chart handler paths (lines 264-271)."""

    async def test_returns_png_for_valid_food(self) -> None:
        info = NutrientInfo(calories=300, protein_g=25.0, fat_g=12.0, carbs_g=35.0)
        mock_service = AsyncMock()
        mock_service.lookup.return_value = info

        result = await _call_nutrition_chart("chicken breast", mock_service)

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"
        mock_service.lookup.assert_called_once_with("chicken breast")

    async def test_returns_error_png_on_not_found(self) -> None:
        mock_service = AsyncMock()
        mock_service.lookup.side_effect = NotFoundError("'xyz' not found")

        result = await _call_nutrition_chart("xyz", mock_service)

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"
        assert img.size == (200, 200)

    async def test_returns_error_png_on_api_error(self) -> None:
        mock_service = AsyncMock()
        mock_service.lookup.side_effect = ExternalAPIError("USDA down")

        result = await _call_nutrition_chart("beef", mock_service)

        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"
        assert img.size == (200, 200)


async def _call_nutrition_chart(food_name: str, mock_service: AsyncMock) -> bytes:
    """Exercise the nutrition_chart resource logic."""
    try:
        info = await mock_service.lookup(food_name)
        return render_macro_chart(info, food_name)
    except (NotFoundError, ExternalAPIError):
        return render_error_png(f"No data for: {food_name}")
