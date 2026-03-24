"""Unit tests for all tools modules.

Covers uncovered lines in:
- tools/recipe_tools.py
- tools/meal_plan_tools.py
- tools/nutrition_tools.py
- tools/seasonal.py
- tools/utility_tools.py
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.models.meal_plan import MealPlan, ShoppingItem
from recipe_mcp_server.models.nutrition import FoodItem, NutrientInfo, NutritionReport
from recipe_mcp_server.models.recipe import (
    Recipe,
    RecipeSummary,
    ScaledIngredient,
)
from recipe_mcp_server.models.user import Favorite
from recipe_mcp_server.tools.recipe_tools import _decode_cursor, _encode_cursor

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_ctx(lifespan_context: dict | None = None) -> AsyncMock:
    """Build a minimal mock MCP Context."""
    ctx = AsyncMock()
    ctx.lifespan_context = lifespan_context or {}
    ctx.info = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()
    ctx.set_state = AsyncMock()
    ctx.get_state = AsyncMock(return_value=None)
    ctx.report_progress = AsyncMock()
    ctx.send_notification = AsyncMock()
    ctx.enable_components = AsyncMock()
    ctx.disable_components = AsyncMock()
    return ctx


def _make_recipe_service() -> AsyncMock:
    return AsyncMock()


def _make_meal_plan_service() -> AsyncMock:
    return AsyncMock()


def _make_shopping_service() -> AsyncMock:
    return AsyncMock()


def _make_nutrition_service() -> AsyncMock:
    return AsyncMock()


def _make_conversion_service() -> MagicMock:
    svc = MagicMock()
    svc.convert = MagicMock()
    svc.convert_with_api_fallback = AsyncMock()
    return svc


def _make_spoonacular_client() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# recipe_tools.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEncodeCursor:
    """Unit tests for cursor encoding helpers (line 27)."""

    def test_encode_decode_roundtrip(self) -> None:
        """Encoding then decoding an offset returns the original value."""
        for offset in (0, 10, 100, 999):
            encoded = _encode_cursor(offset)
            assert isinstance(encoded, str)
            assert _decode_cursor(encoded) == offset

    def test_encode_produces_string(self) -> None:
        """_encode_cursor produces a non-empty string."""
        result = _encode_cursor(0)
        assert len(result) > 0


@pytest.mark.unit
class TestGetRecipeServiceExtraction:
    """Covers the _get_recipe_service helper (line 27 of seasonal.py and recipe_tools.py)."""

    def test_extracts_recipe_service_from_lifespan_context(self) -> None:
        """The helper casts and returns the service from the context dict."""
        from recipe_mcp_server.tools.recipe_tools import _get_recipe_service

        mock_service = object()
        ctx = _make_ctx({"recipe_service": mock_service})
        result = _get_recipe_service(ctx)
        assert result is mock_service


# ---------------------------------------------------------------------------
# search_recipes tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSearchRecipesTool:
    """Tests for search_recipes covering pagination and error branches."""

    def _setup(self):
        svc = _make_recipe_service()
        ctx = _make_ctx({"recipe_service": svc})
        return ctx, svc

    async def _call_search(self, ctx, **kwargs):
        """Call search_recipes by invoking the underlying logic directly."""
        from recipe_mcp_server.tools.recipe_tools import register_recipe_tools

        mcp = MagicMock()
        captured = {}

        def _tool_decorator(**_kw):
            def _capture(fn):
                captured[fn.__name__] = fn
                return fn

            return _capture

        mcp.tool = _tool_decorator
        register_recipe_tools(mcp)
        fn = captured["search_recipes"]
        return await fn(ctx, **kwargs)

    async def test_search_with_next_cursor_included(self) -> None:
        """When there are more results, next_cursor is included in response (lines 96-97)."""
        ctx, svc = self._setup()
        # Return 11 results so has_more is True for limit=10
        svc.search.return_value = [RecipeSummary(id=str(i), title=f"Recipe {i}") for i in range(11)]
        result = await self._call_search(ctx, query="pasta", limit=10)
        data = json.loads(result)
        assert "next_cursor" in data
        assert len(data["results"]) == 10

    async def test_search_without_next_cursor_when_no_more(self) -> None:
        """When there are no more results, next_cursor is absent (line 98)."""
        ctx, svc = self._setup()
        svc.search.return_value = [RecipeSummary(id="1", title="Pasta")]
        result = await self._call_search(ctx, query="pasta", limit=10)
        data = json.loads(result)
        assert "next_cursor" not in data

    async def test_search_cancelled_returns_partial_response(self) -> None:
        """asyncio.CancelledError returns cancelled flag (lines 99-101)."""
        ctx, svc = self._setup()
        svc.search.side_effect = asyncio.CancelledError()
        result = await self._call_search(ctx, query="pasta")
        data = json.loads(result)
        assert data["cancelled"] is True
        assert data["results"] == []

    async def test_search_external_api_error_returns_error_string(self) -> None:
        """ExternalAPIError returns an error string (lines 102-104)."""
        ctx, svc = self._setup()
        svc.search.side_effect = ExternalAPIError("upstream down", api_name="Spoonacular")
        result = await self._call_search(ctx, query="pasta")
        assert result.startswith("Error searching recipes:")

    async def test_search_with_cursor_decodes_offset(self) -> None:
        """Passing a cursor decodes the offset and slices results correctly."""
        ctx, svc = self._setup()
        # Simulate page 2: offset=5, limit=5, return 5 results starting at index 5
        svc.search.return_value = [RecipeSummary(id=str(i), title=f"Recipe {i}") for i in range(10)]
        cursor = _encode_cursor(5)
        result = await self._call_search(ctx, query="test", limit=5, cursor=cursor)
        data = json.loads(result)
        assert len(data["results"]) == 5


# ---------------------------------------------------------------------------
# create_recipe tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateRecipeTool:
    """Tests for create_recipe covering ingredient parsing error branch."""

    def _setup(self):
        svc = _make_recipe_service()
        ctx = _make_ctx({"recipe_service": svc})
        return ctx, svc

    async def _call_create(self, ctx, **kwargs):
        from recipe_mcp_server.tools.recipe_tools import register_recipe_tools

        mcp = MagicMock()
        captured = {}

        def _tool_decorator(**_kw):
            def _capture(fn):
                captured[fn.__name__] = fn
                return fn

            return _capture

        mcp.tool = _tool_decorator
        register_recipe_tools(mcp)
        fn = captured["create_recipe"]
        return await fn(ctx, **kwargs)

    async def test_invalid_ingredients_json_returns_error(self) -> None:
        """Bad JSON in ingredients_json returns an error string (lines 177-182)."""
        ctx, _svc = self._setup()
        result = await self._call_create(
            ctx,
            title="Test",
            ingredients_json="not valid json }{",
        )
        assert result.startswith("Error: Invalid ingredients_json format:")

    async def test_valid_ingredients_json_creates_recipe(self) -> None:
        """Valid ingredients_json parses successfully and calls service.create."""
        ctx, svc = self._setup()
        recipe = Recipe(id="new-1", title="Test Recipe")
        svc.create.return_value = recipe
        with (
            patch(
                "recipe_mcp_server.tools.recipe_tools.notify_resource_updated",
                new_callable=AsyncMock,
            ),
            patch(
                "recipe_mcp_server.tools.recipe_tools.notify_resource_list_changed",
                new_callable=AsyncMock,
            ),
        ):
            ingredients_json = json.dumps([{"name": "flour", "quantity": 2.0, "unit": "cups"}])
            result = await self._call_create(
                ctx,
                title="Test Recipe",
                ingredients_json=ingredients_json,
            )
        data = json.loads(result)
        assert data["id"] == "new-1"


# ---------------------------------------------------------------------------
# update_recipe tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateRecipeTool:
    """Tests for update_recipe covering error branches (lines 241-274)."""

    def _setup(self):
        svc = _make_recipe_service()
        ctx = _make_ctx({"recipe_service": svc})
        return ctx, svc

    async def _call_update(self, ctx, **kwargs):
        from recipe_mcp_server.tools.recipe_tools import register_recipe_tools

        mcp = MagicMock()
        captured = {}

        def _tool_decorator(**_kw):
            def _capture(fn):
                captured[fn.__name__] = fn
                return fn

            return _capture

        mcp.tool = _tool_decorator
        register_recipe_tools(mcp)
        fn = captured["update_recipe"]
        return await fn(ctx, **kwargs)

    async def test_invalid_ingredients_json_returns_error(self) -> None:
        """Bad ingredients_json during update returns error string (lines 249-251)."""
        ctx, _svc = self._setup()
        result = await self._call_update(
            ctx,
            recipe_id="r1",
            ingredients_json="{bad json}",
        )
        assert result.startswith("Error: Invalid ingredients_json format:")

    async def test_update_success_notifies_resource(self) -> None:
        """Successful update returns serialised recipe (lines 268-271)."""
        ctx, svc = self._setup()
        updated = Recipe(id="r1", title="Updated Title")
        svc.update.return_value = updated
        with patch(
            "recipe_mcp_server.tools.recipe_tools.notify_resource_updated",
            new_callable=AsyncMock,
        ):
            result = await self._call_update(ctx, recipe_id="r1", title="Updated Title")
        data = json.loads(result)
        assert data["title"] == "Updated Title"

    async def test_update_not_found_returns_error(self) -> None:
        """NotFoundError during update returns error string (lines 272-274)."""
        ctx, svc = self._setup()
        svc.update.side_effect = NotFoundError("Recipe r99 not found")
        result = await self._call_update(ctx, recipe_id="r99", title="X")
        assert result.startswith("Error:")

    async def test_update_with_valid_ingredients_json(self) -> None:
        """Valid ingredients_json is parsed and passed to service.update."""
        ctx, svc = self._setup()
        updated = Recipe(id="r1", title="Recipe")
        svc.update.return_value = updated
        ingredients_json = json.dumps([{"name": "butter", "quantity": 100.0, "unit": "g"}])
        with patch(
            "recipe_mcp_server.tools.recipe_tools.notify_resource_updated",
            new_callable=AsyncMock,
        ):
            result = await self._call_update(
                ctx,
                recipe_id="r1",
                ingredients_json=ingredients_json,
            )
        assert json.loads(result)["id"] == "r1"


# ---------------------------------------------------------------------------
# delete_recipe tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeleteRecipeTool:
    """Tests for delete_recipe covering not-found branch (lines 290-291)."""

    def _setup(self):
        svc = _make_recipe_service()
        ctx = _make_ctx({"recipe_service": svc})
        return ctx, svc

    async def _call_delete(self, ctx, **kwargs):
        from recipe_mcp_server.tools.recipe_tools import register_recipe_tools

        mcp = MagicMock()
        captured = {}

        def _tool_decorator(**_kw):
            def _capture(fn):
                captured[fn.__name__] = fn
                return fn

            return _capture

        mcp.tool = _tool_decorator
        register_recipe_tools(mcp)
        fn = captured["delete_recipe"]
        return await fn(ctx, **kwargs)

    async def test_delete_not_found_returns_error(self) -> None:
        """When service.delete returns False, an error string is returned (lines 290-291)."""
        ctx, svc = self._setup()
        svc.delete.return_value = False
        result = await self._call_delete(ctx, recipe_id="missing-id")
        assert "not found" in result.lower()

    async def test_delete_success_returns_json(self) -> None:
        """When service.delete returns True, a success payload is returned."""
        ctx, svc = self._setup()
        svc.delete.return_value = True
        with (
            patch(
                "recipe_mcp_server.tools.recipe_tools.notify_resource_updated",
                new_callable=AsyncMock,
            ),
            patch(
                "recipe_mcp_server.tools.recipe_tools.notify_resource_list_changed",
                new_callable=AsyncMock,
            ),
        ):
            result = await self._call_delete(ctx, recipe_id="r1")
        data = json.loads(result)
        assert data["deleted"] is True
        assert data["recipe_id"] == "r1"


# ---------------------------------------------------------------------------
# scale_recipe tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScaleRecipeTool:
    """Tests for scale_recipe covering error branches (lines 309-320)."""

    def _setup(self):
        svc = _make_recipe_service()
        ctx = _make_ctx({"recipe_service": svc})
        return ctx, svc

    async def _call_scale(self, ctx, **kwargs):
        from recipe_mcp_server.tools.recipe_tools import register_recipe_tools

        mcp = MagicMock()
        captured = {}

        def _tool_decorator(**_kw):
            def _capture(fn):
                captured[fn.__name__] = fn
                return fn

            return _capture

        mcp.tool = _tool_decorator
        register_recipe_tools(mcp)
        fn = captured["scale_recipe"]
        return await fn(ctx, **kwargs)

    async def test_scale_success_returns_scaled_ingredients(self) -> None:
        """Successful scaling returns JSON list of scaled ingredients (lines 312-314)."""
        ctx, svc = self._setup()
        svc.scale_recipe.return_value = [
            ScaledIngredient(
                name="flour",
                quantity=4.0,
                unit="cups",
                original_quantity=2.0,
                scale_factor=2.0,
            )
        ]
        result = await self._call_scale(ctx, recipe_id="r1", target_servings=8)
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["quantity"] == 4.0

    async def test_scale_not_found_returns_error(self) -> None:
        """NotFoundError returns an error string (lines 315-317)."""
        ctx, svc = self._setup()
        svc.scale_recipe.side_effect = NotFoundError("Recipe not found")
        result = await self._call_scale(ctx, recipe_id="missing", target_servings=4)
        assert result.startswith("Error:")

    async def test_scale_value_error_returns_error(self) -> None:
        """ValueError returns an error string (lines 318-320)."""
        ctx, svc = self._setup()
        svc.scale_recipe.side_effect = ValueError("target_servings must be positive")
        result = await self._call_scale(ctx, recipe_id="r1", target_servings=0)
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# get_substitutes tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSubstitutesTool:
    """Tests for get_substitutes covering the ExternalAPIError branch (lines 332-340)."""

    def _setup(self):
        svc = _make_recipe_service()
        ctx = _make_ctx({"recipe_service": svc})
        return ctx, svc

    async def _call_substitutes(self, ctx, **kwargs):
        from recipe_mcp_server.tools.recipe_tools import register_recipe_tools

        mcp = MagicMock()
        captured = {}

        def _tool_decorator(**_kw):
            def _capture(fn):
                captured[fn.__name__] = fn
                return fn

            return _capture

        mcp.tool = _tool_decorator
        register_recipe_tools(mcp)
        fn = captured["get_substitutes"]
        return await fn(ctx, **kwargs)

    async def test_success_returns_json_list(self) -> None:
        """Successful call returns JSON list of substitutes."""
        ctx, svc = self._setup()
        svc.get_substitutes.return_value = ["margarine", "olive oil"]
        result = await self._call_substitutes(ctx, ingredient="butter")
        data = json.loads(result)
        assert data == ["margarine", "olive oil"]

    async def test_external_api_error_returns_error_string(self) -> None:
        """ExternalAPIError returns an error string (lines 338-340)."""
        ctx, svc = self._setup()
        svc.get_substitutes.side_effect = ExternalAPIError("API down")
        result = await self._call_substitutes(ctx, ingredient="butter")
        assert result.startswith("Error finding substitutes:")


# ---------------------------------------------------------------------------
# get_random_recipe tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetRandomRecipeTool:
    """Tests for get_random_recipe covering error branch (lines 374-382)."""

    def _setup(self):
        svc = _make_recipe_service()
        ctx = _make_ctx({"recipe_service": svc})
        return ctx, svc

    async def _call_random(self, ctx):
        from recipe_mcp_server.tools.recipe_tools import register_recipe_tools

        mcp = MagicMock()
        captured = {}

        def _tool_decorator(**_kw):
            def _capture(fn):
                captured[fn.__name__] = fn
                return fn

            return _capture

        mcp.tool = _tool_decorator
        register_recipe_tools(mcp)
        fn = captured["get_random_recipe"]
        return await fn(ctx)

    async def test_success_returns_recipe_json(self) -> None:
        """Successful call returns serialised recipe (lines 377-379)."""
        ctx, svc = self._setup()
        recipe = Recipe(id="rand-1", title="Random Pasta")
        svc.random_recipe.return_value = recipe
        result = await self._call_random(ctx)
        data = json.loads(result)
        assert data["title"] == "Random Pasta"

    async def test_not_found_error_returns_error_string(self) -> None:
        """NotFoundError returns an error string (lines 380-382)."""
        ctx, svc = self._setup()
        svc.random_recipe.side_effect = NotFoundError("No meal available")
        result = await self._call_random(ctx)
        assert result.startswith("Error getting random recipe:")

    async def test_external_api_error_returns_error_string(self) -> None:
        """ExternalAPIError returns an error string (lines 380-382)."""
        ctx, svc = self._setup()
        svc.random_recipe.side_effect = ExternalAPIError("API failed")
        result = await self._call_random(ctx)
        assert result.startswith("Error getting random recipe:")


# ---------------------------------------------------------------------------
# list_favorites tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListFavoritesTool:
    """Tests for list_favorites covering result serialisation (lines 394-398)."""

    def _setup(self):
        svc = _make_recipe_service()
        ctx = _make_ctx({"recipe_service": svc})
        return ctx, svc

    async def _call_list_favorites(self, ctx, **kwargs):
        from recipe_mcp_server.tools.recipe_tools import register_recipe_tools

        mcp = MagicMock()
        captured = {}

        def _tool_decorator(**_kw):
            def _capture(fn):
                captured[fn.__name__] = fn
                return fn

            return _capture

        mcp.tool = _tool_decorator
        register_recipe_tools(mcp)
        fn = captured["list_favorites"]
        return await fn(ctx, **kwargs)

    async def test_returns_list_of_favorites(self) -> None:
        """Returns serialised list of Favorite records (lines 396-398)."""
        ctx, svc = self._setup()
        svc.list_favorites.return_value = [
            Favorite(user_id="u1", recipe_id="r1", rating=5),
            Favorite(user_id="u1", recipe_id="r2"),
        ]
        result = await self._call_list_favorites(ctx, user_id="u1")
        data = json.loads(result)
        assert len(data) == 2
        assert data[0]["recipe_id"] == "r1"

    async def test_returns_empty_list_when_no_favorites(self) -> None:
        """Returns an empty list when user has no favorites."""
        ctx, svc = self._setup()
        svc.list_favorites.return_value = []
        result = await self._call_list_favorites(ctx, user_id="u1")
        data = json.loads(result)
        assert data == []


# ---------------------------------------------------------------------------
# meal_plan_tools.py
# ---------------------------------------------------------------------------


def _make_meal_plan_tool_helpers():
    """Return a registered (ctx, meal_plan_svc, shopping_svc, captured_fns) tuple."""
    mp_svc = _make_meal_plan_service()
    sh_svc = _make_shopping_service()
    ctx = _make_ctx(
        {
            "meal_plan_service": mp_svc,
            "shopping_service": sh_svc,
        }
    )

    from recipe_mcp_server.tools.meal_plan_tools import register_meal_plan_tools

    mcp = MagicMock()
    captured = {}

    def _tool_decorator(**_kw):
        def _capture(fn):
            captured[fn.__name__] = fn
            return fn

        return _capture

    mcp.tool = _tool_decorator
    register_meal_plan_tools(mcp)
    return ctx, mp_svc, sh_svc, captured


@pytest.mark.unit
class TestGetMealPlanServiceExtraction:
    """Covers _get_meal_plan_service and _get_shopping_service helpers (line 27)."""

    def test_extracts_meal_plan_service(self) -> None:
        from recipe_mcp_server.tools.meal_plan_tools import _get_meal_plan_service

        mock_svc = object()
        ctx = _make_ctx({"meal_plan_service": mock_svc})
        assert _get_meal_plan_service(ctx) is mock_svc

    def test_extracts_shopping_service(self) -> None:
        from recipe_mcp_server.tools.meal_plan_tools import _get_shopping_service

        mock_svc = object()
        ctx = _make_ctx({"shopping_service": mock_svc})
        assert _get_shopping_service(ctx) is mock_svc


@pytest.mark.unit
class TestGenerateMealPlanTool:
    """Tests for generate_meal_plan covering all branches (lines 57-80)."""

    async def test_uses_stored_dietary_preferences_when_diet_empty(self) -> None:
        """When diet is empty and user_preferences has restrictions, they are used (lines 57-61)."""
        ctx, mp_svc, _, captured = _make_meal_plan_tool_helpers()
        ctx.get_state.return_value = {"dietary_restrictions": ["vegetarian", "gluten-free"]}

        meal_plan = MealPlan(
            id="plan-1",
            name="My Plan",
            user_id="u1",
            start_date="2026-03-23",
            end_date="2026-03-29",
        )
        mp_svc.generate.return_value = meal_plan

        result = await captured["generate_meal_plan"](ctx, user_id="u1", name="My Plan", diet="")
        data = json.loads(result)
        assert data["id"] == "plan-1"
        # Verify the assembled diet string was passed to the service
        call_kwargs = mp_svc.generate.call_args.kwargs
        assert "vegetarian" in call_kwargs["diet"]
        assert "gluten-free" in call_kwargs["diet"]

    async def test_skips_stored_prefs_when_diet_provided(self) -> None:
        """When diet is explicitly provided, stored preferences are ignored (line 57)."""
        ctx, mp_svc, _, captured = _make_meal_plan_tool_helpers()
        ctx.get_state.return_value = {"dietary_restrictions": ["keto"]}

        meal_plan = MealPlan(
            id="plan-2",
            name="Plan B",
            user_id="u1",
            start_date="2026-03-23",
            end_date="2026-03-29",
        )
        mp_svc.generate.return_value = meal_plan

        result = await captured["generate_meal_plan"](
            ctx, user_id="u1", name="Plan B", diet="vegan"
        )
        call_kwargs = mp_svc.generate.call_args.kwargs
        assert call_kwargs["diet"] == "vegan"
        assert json.loads(result)["id"] == "plan-2"

    async def test_skips_stored_prefs_when_prefs_not_dict(self) -> None:
        """Non-dict user_preferences state does not cause an error (lines 59-61)."""
        ctx, mp_svc, _, captured = _make_meal_plan_tool_helpers()
        ctx.get_state.return_value = "invalid-state"

        meal_plan = MealPlan(
            id="plan-3",
            name="Plan C",
            user_id="u1",
            start_date="2026-03-23",
            end_date="2026-03-29",
        )
        mp_svc.generate.return_value = meal_plan
        result = await captured["generate_meal_plan"](ctx, user_id="u1", name="Plan C", diet="")
        assert json.loads(result)["id"] == "plan-3"

    async def test_generate_meal_plan_service_extracted_via_lifespan(self) -> None:
        """Service is extracted from lifespan context on line 63 (happy path)."""
        ctx, mp_svc, _, captured = _make_meal_plan_tool_helpers()
        meal_plan = MealPlan(
            id="plan-4",
            name="Happy Plan",
            user_id="u1",
            start_date="2026-03-23",
            end_date="2026-03-29",
        )
        mp_svc.generate.return_value = meal_plan
        result = await captured["generate_meal_plan"](
            ctx, user_id="u1", name="Happy Plan", diet="vegan"
        )
        assert json.loads(result)["name"] == "Happy Plan"

    async def test_cancelled_error_returns_cancelled_flag(self) -> None:
        """asyncio.CancelledError returns cancelled flag (lines 75-77)."""
        ctx, mp_svc, _, captured = _make_meal_plan_tool_helpers()
        mp_svc.generate.side_effect = asyncio.CancelledError()
        result = await captured["generate_meal_plan"](ctx, user_id="u1", name="Test", diet="")
        data = json.loads(result)
        assert data["cancelled"] is True

    async def test_external_api_error_returns_error_string(self) -> None:
        """ExternalAPIError returns an error string (lines 78-80)."""
        ctx, mp_svc, _, captured = _make_meal_plan_tool_helpers()
        mp_svc.generate.side_effect = ExternalAPIError("Plan API down")
        result = await captured["generate_meal_plan"](ctx, user_id="u1", name="Test", diet="")
        assert result.startswith("Error generating meal plan:")


@pytest.mark.unit
class TestGenerateShoppingListTool:
    """Tests for generate_shopping_list covering all branches (lines 96-129)."""

    async def test_both_none_returns_error(self) -> None:
        """Calling with no arguments returns validation error (lines 96-97)."""
        _, _, _, captured = _make_meal_plan_tool_helpers()
        ctx = _make_ctx({"shopping_service": _make_shopping_service()})
        result = await captured["generate_shopping_list"](ctx)
        assert "Error:" in result

    async def test_from_meal_plan_success(self) -> None:
        """Shopping list from meal plan returns serialised items (lines 105-109)."""
        ctx, _, sh_svc, captured = _make_meal_plan_tool_helpers()
        sh_svc.generate_from_meal_plan.return_value = [
            ShoppingItem(ingredient="flour", quantity=2.0, unit="cups"),
        ]
        result = await captured["generate_shopping_list"](ctx, meal_plan_id="plan-1")
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["ingredient"] == "flour"

    async def test_from_meal_plan_not_found_returns_error(self) -> None:
        """NotFoundError for meal plan returns error string (lines 110-112)."""
        ctx, _, sh_svc, captured = _make_meal_plan_tool_helpers()
        sh_svc.generate_from_meal_plan.side_effect = NotFoundError("Meal plan not found")
        result = await captured["generate_shopping_list"](ctx, meal_plan_id="bad-id")
        assert result.startswith("Error:")

    async def test_from_recipes_success(self) -> None:
        """Shopping list from recipe IDs returns serialised items (lines 121-126)."""
        ctx, _, sh_svc, captured = _make_meal_plan_tool_helpers()
        sh_svc.generate_from_recipes.return_value = [
            ShoppingItem(ingredient="butter", quantity=100.0, unit="g"),
        ]
        recipe_ids_json = json.dumps(["r1", "r2"])
        result = await captured["generate_shopping_list"](ctx, recipe_ids_json=recipe_ids_json)
        data = json.loads(result)
        assert data[0]["ingredient"] == "butter"

    async def test_from_recipes_invalid_json_returns_error(self) -> None:
        """Invalid JSON in recipe_ids_json returns error string (lines 117-119)."""
        ctx, _, _sh_svc, captured = _make_meal_plan_tool_helpers()
        result = await captured["generate_shopping_list"](ctx, recipe_ids_json="{not valid}")
        assert result.startswith("Error: Invalid recipe_ids_json format:")

    async def test_from_recipes_not_found_returns_error(self) -> None:
        """NotFoundError for recipes returns error string (lines 127-129)."""
        ctx, _, sh_svc, captured = _make_meal_plan_tool_helpers()
        sh_svc.generate_from_recipes.side_effect = NotFoundError("Recipe not found")
        result = await captured["generate_shopping_list"](
            ctx, recipe_ids_json=json.dumps(["missing"])
        )
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# nutrition_tools.py
# ---------------------------------------------------------------------------


def _make_nutrition_tool_helpers():
    nut_svc = _make_nutrition_service()
    ctx = _make_ctx({"nutrition_service": nut_svc})

    from recipe_mcp_server.tools.nutrition_tools import register_nutrition_tools

    mcp = MagicMock()
    captured = {}

    def _tool_decorator(**_kw):
        def _capture(fn):
            captured[fn.__name__] = fn
            return fn

        return _capture

    mcp.tool = _tool_decorator
    register_nutrition_tools(mcp)
    return ctx, nut_svc, captured


@pytest.mark.unit
class TestGetNutritionServiceExtraction:
    """Covers _get_nutrition_service helper (line 27 of nutrition_tools.py)."""

    def test_extracts_nutrition_service(self) -> None:
        from recipe_mcp_server.tools.nutrition_tools import _get_nutrition_service

        mock_svc = object()
        ctx = _make_ctx({"nutrition_service": mock_svc})
        assert _get_nutrition_service(ctx) is mock_svc


@pytest.mark.unit
class TestLookupNutritionTool:
    """Tests for lookup_nutrition covering all branches (lines 39-46)."""

    async def test_success_returns_food_item_json(self) -> None:
        """Successful lookup returns serialised FoodItem (lines 39-40)."""
        ctx, svc, captured = _make_nutrition_tool_helpers()
        food_item = FoodItem(
            food_name="chicken breast",
            nutrients=NutrientInfo(calories=165.0, protein_g=31.0),
            source="USDA",
        )
        svc.lookup.return_value = food_item
        result = await captured["lookup_nutrition"](ctx, food_name="chicken breast")
        data = json.loads(result)
        assert data["food_name"] == "chicken breast"
        assert data["nutrients"]["calories"] == 165.0

    async def test_not_found_returns_error_string(self) -> None:
        """NotFoundError returns an error string (lines 41-43)."""
        ctx, svc, captured = _make_nutrition_tool_helpers()
        svc.lookup.side_effect = NotFoundError("Food not found")
        result = await captured["lookup_nutrition"](ctx, food_name="unobtainium")
        assert result.startswith("Error:")

    async def test_external_api_error_returns_error_string(self) -> None:
        """ExternalAPIError returns an error string (lines 44-46)."""
        ctx, svc, captured = _make_nutrition_tool_helpers()
        svc.lookup.side_effect = ExternalAPIError("USDA API down")
        result = await captured["lookup_nutrition"](ctx, food_name="apple")
        assert result.startswith("Error looking up nutrition:")


@pytest.mark.unit
class TestAnalyzeRecipeNutritionTool:
    """Tests for analyze_recipe_nutrition covering error branches (lines 67-72)."""

    async def test_success_returns_report_json(self) -> None:
        """Successful analysis returns serialised NutritionReport."""
        ctx, svc, captured = _make_nutrition_tool_helpers()
        report = NutritionReport(
            per_serving=NutrientInfo(calories=500.0),
            total=NutrientInfo(calories=2000.0),
            ingredients=[],
            servings=4,
        )
        svc.analyze_recipe.return_value = report
        result = await captured["analyze_recipe_nutrition"](ctx, recipe_id="r1")
        data = json.loads(result)
        assert data["servings"] == 4

    async def test_not_found_returns_error_string(self) -> None:
        """NotFoundError returns an error string (lines 67-69)."""
        ctx, svc, captured = _make_nutrition_tool_helpers()
        svc.analyze_recipe.side_effect = NotFoundError("Recipe not found")
        result = await captured["analyze_recipe_nutrition"](ctx, recipe_id="missing")
        assert result.startswith("Error:")

    async def test_external_api_error_returns_error_string(self) -> None:
        """ExternalAPIError returns an error string (lines 70-72)."""
        ctx, svc, captured = _make_nutrition_tool_helpers()
        svc.analyze_recipe.side_effect = ExternalAPIError("Nutrition API failed")
        result = await captured["analyze_recipe_nutrition"](ctx, recipe_id="r1")
        assert result.startswith("Error analyzing recipe nutrition:")


# ---------------------------------------------------------------------------
# seasonal.py
# ---------------------------------------------------------------------------


def _make_seasonal_tool_helpers():
    svc = _make_recipe_service()
    ctx = _make_ctx({"recipe_service": svc})

    from recipe_mcp_server.tools.seasonal import register_seasonal_tools

    mcp = MagicMock()
    captured = {}

    def _tool_decorator(**_kw):
        def _capture(fn):
            captured[fn.__name__] = fn
            return fn

        return _capture

    mcp.tool = _tool_decorator
    register_seasonal_tools(mcp)
    return ctx, svc, captured


@pytest.mark.unit
class TestGetRecipeServiceSeasonalExtraction:
    """Covers _get_recipe_service in seasonal.py (line 39)."""

    def test_extracts_recipe_service(self) -> None:
        from recipe_mcp_server.tools.seasonal import _get_recipe_service

        mock_svc = object()
        ctx = _make_ctx({"recipe_service": mock_svc})
        assert _get_recipe_service(ctx) is mock_svc


@pytest.mark.unit
class TestGetHolidayRecipesTool:
    """Tests for get_holiday_recipes covering seasonal branches (lines 66-83)."""

    async def test_returns_error_when_not_holiday_season(self) -> None:
        """Outside Nov/Dec, returns an error JSON (lines 61-64 already covered by is_holiday check).

        We mock _is_holiday_season to return False to exercise this branch.
        """
        ctx, _svc, captured = _make_seasonal_tool_helpers()
        with patch("recipe_mcp_server.tools.seasonal._is_holiday_season", return_value=False):
            result = await captured["get_holiday_recipes"](ctx, holiday="christmas")
        parsed = json.loads(result)
        assert "error" in parsed

    async def test_returns_recipes_during_holiday_season(self) -> None:
        """During holiday season, searches keywords and returns results (lines 66-89)."""
        ctx, svc, captured = _make_seasonal_tool_helpers()
        svc.search.return_value = [
            RecipeSummary(id="1", title="Gingerbread Cookies"),
        ]
        with patch("recipe_mcp_server.tools.seasonal._is_holiday_season", return_value=True):
            result = await captured["get_holiday_recipes"](ctx, holiday="christmas")
        data = json.loads(result)
        assert data["holiday"] == "christmas"
        assert len(data["recipes"]) > 0

    async def test_uses_christmas_keywords_as_fallback_for_unknown_holiday(self) -> None:
        """Unknown holiday falls back to christmas keywords (line 66)."""
        ctx, svc, captured = _make_seasonal_tool_helpers()
        svc.search.return_value = []
        with patch("recipe_mcp_server.tools.seasonal._is_holiday_season", return_value=True):
            await captured["get_holiday_recipes"](ctx, holiday="unknown_holiday")
        # Search should have been called with christmas keywords
        assert svc.search.call_count == 4  # 4 christmas keywords

    async def test_search_failure_for_keyword_is_swallowed(self) -> None:
        """Exception during keyword search is caught and a warning is emitted (lines 79-80)."""
        ctx, svc, captured = _make_seasonal_tool_helpers()
        svc.search.side_effect = Exception("transient failure")
        with patch("recipe_mcp_server.tools.seasonal._is_holiday_season", return_value=True):
            result = await captured["get_holiday_recipes"](ctx, holiday="christmas")
        data = json.loads(result)
        # Result is empty but no exception propagated
        assert data["recipes"] == []
        ctx.warning.assert_called()

    async def test_thanksgiving_holiday_uses_correct_keywords(self) -> None:
        """Thanksgiving keyword list is used when holiday='thanksgiving'."""
        ctx, svc, captured = _make_seasonal_tool_helpers()
        svc.search.return_value = []
        with patch("recipe_mcp_server.tools.seasonal._is_holiday_season", return_value=True):
            await captured["get_holiday_recipes"](ctx, holiday="thanksgiving")
        call_args_list = [call.args[0] for call in svc.search.call_args_list]
        assert "pumpkin pie" in call_args_list


@pytest.mark.unit
class TestToggleSeasonalVisibility:
    """Tests for toggle_seasonal_visibility (lines 98-102)."""

    async def test_enables_components_during_holiday_season(self) -> None:
        """enable_components is called when _is_holiday_season returns True (lines 98-99)."""
        from recipe_mcp_server.tools.seasonal import toggle_seasonal_visibility

        ctx = _make_ctx()
        with patch("recipe_mcp_server.tools.seasonal._is_holiday_season", return_value=True):
            await toggle_seasonal_visibility(ctx)
        ctx.enable_components.assert_called_once_with(names={"get_holiday_recipes"})
        ctx.send_notification.assert_called_once()

    async def test_disables_components_outside_holiday_season(self) -> None:
        """disable_components is called when _is_holiday_season returns False (lines 100-101)."""
        from recipe_mcp_server.tools.seasonal import toggle_seasonal_visibility

        ctx = _make_ctx()
        with patch("recipe_mcp_server.tools.seasonal._is_holiday_season", return_value=False):
            await toggle_seasonal_visibility(ctx)
        ctx.disable_components.assert_called_once_with(names={"get_holiday_recipes"})
        ctx.send_notification.assert_called_once()


# ---------------------------------------------------------------------------
# utility_tools.py
# ---------------------------------------------------------------------------


def _make_utility_tool_helpers():
    conv_svc = _make_conversion_service()
    spoon_client = _make_spoonacular_client()
    ctx = _make_ctx(
        {
            "conversion_service": conv_svc,
            "spoonacular_client": spoon_client,
        }
    )

    from recipe_mcp_server.tools.utility_tools import register_utility_tools

    mcp = MagicMock()
    captured = {}

    def _tool_decorator(**_kw):
        def _capture(fn):
            captured[fn.__name__] = fn
            return fn

        return _capture

    mcp.tool = _tool_decorator
    register_utility_tools(mcp)
    return ctx, conv_svc, spoon_client, captured


@pytest.mark.unit
class TestConversionServiceExtraction:
    """Covers _get_conversion_service and _get_spoonacular_client helpers (lines 38-40)."""

    def test_extracts_conversion_service(self) -> None:
        from recipe_mcp_server.tools.utility_tools import _get_conversion_service

        mock_svc = object()
        ctx = _make_ctx({"conversion_service": mock_svc})
        assert _get_conversion_service(ctx) is mock_svc

    def test_extracts_spoonacular_client(self) -> None:
        from recipe_mcp_server.tools.utility_tools import _get_spoonacular_client

        mock_client = object()
        ctx = _make_ctx({"spoonacular_client": mock_client})
        assert _get_spoonacular_client(ctx) is mock_client


@pytest.mark.unit
class TestConvertUnitsTool:
    """Tests for convert_units covering all branches (lines 74-95)."""

    async def test_convert_with_ingredient_uses_api_fallback(self) -> None:
        """When ingredient is provided, convert_with_api_fallback is used (lines 74-79)."""
        ctx, conv_svc, _, captured = _make_utility_tool_helpers()
        conv_svc.convert_with_api_fallback.return_value = 240.0
        result = await captured["convert_units"](
            ctx, value=1.0, from_unit="cups", to_unit="ml", ingredient="flour"
        )
        data = json.loads(result)
        assert data["result"] == 240.0
        conv_svc.convert_with_api_fallback.assert_called_once()

    async def test_convert_without_ingredient_uses_local_service(self) -> None:
        """When no ingredient, service.convert is used (line 81)."""
        ctx, conv_svc, _, captured = _make_utility_tool_helpers()
        conv_svc.convert.return_value = 28.35
        result = await captured["convert_units"](ctx, value=1.0, from_unit="oz", to_unit="g")
        data = json.loads(result)
        assert data["result"] == 28.35
        conv_svc.convert.assert_called_once()

    async def test_sets_metric_unit_system_state(self) -> None:
        """When to_unit is a metric unit, unit_system state is set to 'metric' (lines 84-85)."""
        ctx, conv_svc, _, captured = _make_utility_tool_helpers()
        conv_svc.convert.return_value = 1000.0
        await captured["convert_units"](ctx, value=1.0, from_unit="l", to_unit="ml")
        ctx.set_state.assert_called_with("unit_system", "metric")

    async def test_sets_imperial_unit_system_state(self) -> None:
        """When to_unit is an imperial unit, unit_system state is set to 'imperial'."""
        ctx, conv_svc, _, captured = _make_utility_tool_helpers()
        conv_svc.convert.return_value = 2.0
        await captured["convert_units"](ctx, value=32.0, from_unit="oz", to_unit="lb")
        ctx.set_state.assert_called_with("unit_system", "imperial")

    async def test_does_not_set_state_for_ambiguous_unit(self) -> None:
        """Ambiguous unit does not trigger set_state (line 84 condition False, line 85 skipped)."""
        ctx, conv_svc, _, captured = _make_utility_tool_helpers()
        conv_svc.convert.return_value = 42.0
        await captured["convert_units"](
            ctx, value=1.0, from_unit="something", to_unit="unknown_unit"
        )
        ctx.set_state.assert_not_called()

    async def test_value_error_returns_error_string(self) -> None:
        """ValueError during conversion returns an error string (lines 93-95)."""
        ctx, conv_svc, _, captured = _make_utility_tool_helpers()
        conv_svc.convert.side_effect = ValueError("unsupported unit")
        result = await captured["convert_units"](ctx, value=1.0, from_unit="bad", to_unit="worse")
        assert result.startswith("Error:")


@pytest.mark.unit
class TestGetWinePairingTool:
    """Tests for get_wine_pairing covering error branch (lines 113-115)."""

    async def test_success_returns_pairing_json(self) -> None:
        """Successful pairing returns JSON (lines 110-112)."""
        ctx, _, spoon, captured = _make_utility_tool_helpers()
        spoon.get_wine_pairing.return_value = {"wines": ["Chardonnay"], "text": "Great match"}
        result = await captured["get_wine_pairing"](ctx, food="salmon")
        data = json.loads(result)
        assert data["wines"] == ["Chardonnay"]

    async def test_external_api_error_returns_error_string(self) -> None:
        """ExternalAPIError returns an error string (lines 113-115)."""
        ctx, _, spoon, captured = _make_utility_tool_helpers()
        spoon.get_wine_pairing.side_effect = ExternalAPIError("Spoonacular failed")
        result = await captured["get_wine_pairing"](ctx, food="steak")
        assert result.startswith("Error getting wine pairing:")
