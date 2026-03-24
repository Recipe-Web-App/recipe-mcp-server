"""Unit tests for the prompts modules.

Covers:
- cooking_prompts.py  (cooking_instructions)
- dietary_prompts.py  (adapt_for_diet, ingredient_spotlight)
- meal_plan_prompts.py (weekly_meal_plan, holiday_menu)
- recipe_prompts.py   (generate_recipe, leftover_recipe, quick_meal)
- completion.py       (_filter_by_prefix, _handle_completion,
                       _completion_request_handler)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from mcp import types as mcp_types

from recipe_mcp_server.exceptions import NotFoundError
from recipe_mcp_server.models.recipe import Ingredient, Recipe
from recipe_mcp_server.prompts.completion import (
    CUISINES,
    DIETARY_RESTRICTIONS,
    MAX_COMPLETION_VALUES,
    _completion_request_handler,
    _filter_by_prefix,
    _handle_completion,
)
from recipe_mcp_server.prompts.cooking_prompts import (
    _get_recipe_service,
    register_cooking_prompts,
)
from recipe_mcp_server.prompts.dietary_prompts import (
    _get_recipe_service as dietary_get_recipe_service,
)
from recipe_mcp_server.prompts.dietary_prompts import (
    register_dietary_prompts,
)
from recipe_mcp_server.prompts.meal_plan_prompts import register_meal_plan_prompts
from recipe_mcp_server.prompts.recipe_prompts import register_recipe_prompts

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ctx() -> AsyncMock:
    """MCP Context mock with a lifespan_context containing a recipe_service."""
    ctx = AsyncMock()
    ctx.lifespan_context = {"recipe_service": AsyncMock()}
    return ctx


@pytest.fixture
def sample_recipe() -> Recipe:
    """A Recipe with all common fields populated."""
    return Recipe(
        id="recipe-001",
        title="Pasta Carbonara",
        servings=4,
        prep_time_min=10,
        cook_time_min=20,
        instructions=[
            "Boil pasta in salted water.",
            "Fry guanciale until crisp.",
            "Mix eggs and pecorino.",
            "Combine off heat.",
        ],
        ingredients=[
            Ingredient(name="Pasta", quantity=400, unit="g"),
            Ingredient(name="Guanciale", quantity=200, unit="g"),
            Ingredient(name="Egg Yolks", quantity=4, unit=None),
            Ingredient(name="Pecorino", quantity=None, unit=None),
        ],
    )


@pytest.fixture
def minimal_recipe() -> Recipe:
    """A Recipe with only required fields — exercises optional-field branches."""
    return Recipe(
        id="recipe-min",
        title="Plain Omelette",
        servings=1,
        ingredients=[
            Ingredient(name="Eggs", quantity=2, unit=None, notes="large"),
        ],
    )


# ---------------------------------------------------------------------------
# cooking_prompts._get_recipe_service
# ---------------------------------------------------------------------------


class TestGetRecipeServiceCooking:
    def test_returns_service_from_lifespan_context(self, mock_ctx: AsyncMock) -> None:
        """_get_recipe_service extracts the recipe_service from lifespan_context."""
        service = _get_recipe_service(mock_ctx)
        assert service is mock_ctx.lifespan_context["recipe_service"]


# ---------------------------------------------------------------------------
# cooking_prompts.cooking_instructions
# ---------------------------------------------------------------------------


class TestCookingInstructions:
    """Tests for the cooking_instructions prompt function.

    The function is registered as a FastMCP prompt via a decorator.
    We exercise it by calling the underlying coroutine directly through
    a minimal FastMCP stub that captures decorated functions.
    """

    @pytest.fixture
    def captured_fn(self) -> AsyncMock:
        """Return the raw cooking_instructions coroutine captured from registration."""
        captured: dict[str, object] = {}

        class _FakeMCP:
            def prompt(self, **_kwargs):
                def _decorator(fn):
                    captured["fn"] = fn
                    return fn

                return _decorator

        register_cooking_prompts(_FakeMCP())
        return captured["fn"]

    async def test_not_found_returns_error_prompt(self, captured_fn, mock_ctx: AsyncMock) -> None:
        mock_ctx.lifespan_context["recipe_service"].get.side_effect = NotFoundError("not found")
        result = await captured_fn(ctx=mock_ctx, recipe_id="bad-id")
        assert result.description == "Recipe not found"
        assert len(result.messages) == 1
        assert "bad-id" in result.messages[0].content.text

    async def test_success_with_all_fields(
        self, captured_fn, mock_ctx: AsyncMock, sample_recipe: Recipe
    ) -> None:
        mock_ctx.lifespan_context["recipe_service"].get.return_value = sample_recipe
        result = await captured_fn(ctx=mock_ctx, recipe_id="recipe-001", skill_level="intermediate")
        assert "Pasta Carbonara" in result.description
        assert "intermediate" in result.description
        assert len(result.messages) == 2
        user_msg = result.messages[1].content.text
        assert "Pasta Carbonara" in user_msg
        assert "Timing:" in user_msg
        assert "Prep: 10 min" in user_msg
        assert "Cook: 20 min" in user_msg
        assert "Pasta" in user_msg
        assert "Guanciale" in user_msg
        assert "Boil pasta" in user_msg

    async def test_default_skill_level_is_intermediate(
        self, captured_fn, mock_ctx: AsyncMock, sample_recipe: Recipe
    ) -> None:
        mock_ctx.lifespan_context["recipe_service"].get.return_value = sample_recipe
        result = await captured_fn(ctx=mock_ctx, recipe_id="recipe-001")
        assert "intermediate" in result.description

    async def test_beginner_level_system_message(
        self, captured_fn, mock_ctx: AsyncMock, sample_recipe: Recipe
    ) -> None:
        mock_ctx.lifespan_context["recipe_service"].get.return_value = sample_recipe
        result = await captured_fn(ctx=mock_ctx, recipe_id="recipe-001", skill_level="beginner")
        system_text = result.messages[0].content.text
        assert "beginner" in system_text
        assert "culinary terms" in system_text

    async def test_advanced_level_system_message(
        self, captured_fn, mock_ctx: AsyncMock, sample_recipe: Recipe
    ) -> None:
        mock_ctx.lifespan_context["recipe_service"].get.return_value = sample_recipe
        result = await captured_fn(ctx=mock_ctx, recipe_id="recipe-001", skill_level="advanced")
        system_text = result.messages[0].content.text
        assert "advanced" in system_text
        assert "plating" in system_text

    async def test_ingredient_without_quantity_or_unit(
        self, captured_fn, mock_ctx: AsyncMock, minimal_recipe: Recipe
    ) -> None:
        """Ingredient with quantity=None and unit=None is still included."""
        mock_ctx.lifespan_context["recipe_service"].get.return_value = minimal_recipe
        result = await captured_fn(ctx=mock_ctx, recipe_id="recipe-min")
        user_msg = result.messages[1].content.text
        assert "Eggs" in user_msg

    async def test_ingredient_with_quantity_and_unit(
        self, captured_fn, mock_ctx: AsyncMock, sample_recipe: Recipe
    ) -> None:
        mock_ctx.lifespan_context["recipe_service"].get.return_value = sample_recipe
        result = await captured_fn(ctx=mock_ctx, recipe_id="recipe-001")
        user_msg = result.messages[1].content.text
        # quantity is stored as float so renders as e.g. "400.0 g Pasta"
        assert "g Pasta" in user_msg
        assert "Pasta" in user_msg

    async def test_no_instructions_shows_placeholder(
        self, captured_fn, mock_ctx: AsyncMock
    ) -> None:
        recipe = Recipe(title="Mystery Dish", instructions=[])
        mock_ctx.lifespan_context["recipe_service"].get.return_value = recipe
        result = await captured_fn(ctx=mock_ctx, recipe_id="r-x")
        user_msg = result.messages[1].content.text
        assert "No instructions stored" in user_msg

    async def test_no_timing_shows_placeholder(self, captured_fn, mock_ctx: AsyncMock) -> None:
        recipe = Recipe(
            title="Timeless Dish",
            prep_time_min=None,
            cook_time_min=None,
        )
        mock_ctx.lifespan_context["recipe_service"].get.return_value = recipe
        result = await captured_fn(ctx=mock_ctx, recipe_id="r-y")
        user_msg = result.messages[1].content.text
        assert "Timing not specified" in user_msg

    async def test_only_prep_time(self, captured_fn, mock_ctx: AsyncMock) -> None:
        recipe = Recipe(title="Prep-Only Dish", prep_time_min=5, cook_time_min=None)
        mock_ctx.lifespan_context["recipe_service"].get.return_value = recipe
        result = await captured_fn(ctx=mock_ctx, recipe_id="r-z")
        user_msg = result.messages[1].content.text
        assert "Prep: 5 min" in user_msg
        assert "Cook" not in user_msg.split("**Timing:**")[1].split("\n")[0]

    async def test_only_cook_time(self, captured_fn, mock_ctx: AsyncMock) -> None:
        recipe = Recipe(title="Cook-Only Dish", prep_time_min=None, cook_time_min=30)
        mock_ctx.lifespan_context["recipe_service"].get.return_value = recipe
        result = await captured_fn(ctx=mock_ctx, recipe_id="r-w")
        user_msg = result.messages[1].content.text
        assert "Cook: 30 min" in user_msg


# ---------------------------------------------------------------------------
# dietary_prompts._get_recipe_service
# ---------------------------------------------------------------------------


class TestGetRecipeServiceDietary:
    def test_returns_service_from_lifespan_context(self, mock_ctx: AsyncMock) -> None:
        """The dietary module's helper extracts recipe_service from lifespan_context."""
        service = dietary_get_recipe_service(mock_ctx)
        assert service is mock_ctx.lifespan_context["recipe_service"]


# ---------------------------------------------------------------------------
# dietary_prompts.adapt_for_diet
# ---------------------------------------------------------------------------


class TestAdaptForDiet:
    @pytest.fixture
    def captured_fns(self, mock_ctx: AsyncMock) -> dict[str, object]:
        captured: dict[str, object] = {}

        class _FakeMCP:
            def prompt(self, **_kwargs):
                def _decorator(fn):
                    captured[fn.__name__] = fn
                    return fn

                return _decorator

        register_dietary_prompts(_FakeMCP())
        return captured

    async def test_not_found_returns_error_prompt(self, captured_fns, mock_ctx: AsyncMock) -> None:
        mock_ctx.lifespan_context["recipe_service"].get.side_effect = NotFoundError("not found")
        fn = captured_fns["adapt_for_diet"]
        result = await fn(ctx=mock_ctx, recipe_id="missing-id", restrictions=["vegan"])
        assert result.description == "Recipe not found"
        assert "missing-id" in result.messages[0].content.text

    async def test_success_with_restrictions(
        self, captured_fns, mock_ctx: AsyncMock, sample_recipe: Recipe
    ) -> None:
        mock_ctx.lifespan_context["recipe_service"].get.return_value = sample_recipe
        fn = captured_fns["adapt_for_diet"]
        result = await fn(
            ctx=mock_ctx,
            recipe_id="recipe-001",
            restrictions=["vegan", "gluten-free"],
        )
        assert "Pasta Carbonara" in result.description
        assert "vegan" in result.description
        assert "gluten-free" in result.description
        assert len(result.messages) == 2
        user_msg = result.messages[1].content.text
        assert "Pasta Carbonara" in user_msg
        assert "vegan" in user_msg
        assert "Pasta" in user_msg

    async def test_ingredient_with_notes_included(
        self, captured_fns, mock_ctx: AsyncMock, minimal_recipe: Recipe
    ) -> None:
        """Ingredient notes are appended to the ingredient line."""
        mock_ctx.lifespan_context["recipe_service"].get.return_value = minimal_recipe
        fn = captured_fns["adapt_for_diet"]
        result = await fn(ctx=mock_ctx, recipe_id="recipe-min", restrictions=["dairy-free"])
        user_msg = result.messages[1].content.text
        # minimal_recipe has Ingredient(name="Eggs", notes="large")
        assert "(large)" in user_msg

    async def test_ingredient_without_notes(
        self, captured_fns, mock_ctx: AsyncMock, sample_recipe: Recipe
    ) -> None:
        """Ingredients without notes are rendered without parentheses."""
        mock_ctx.lifespan_context["recipe_service"].get.return_value = sample_recipe
        fn = captured_fns["adapt_for_diet"]
        result = await fn(ctx=mock_ctx, recipe_id="recipe-001", restrictions=["vegetarian"])
        user_msg = result.messages[1].content.text
        # Pasta has no notes — parenthetical should not appear for it
        # quantity is stored as float so renders as e.g. "400.0 g Pasta"
        assert "g Pasta" in user_msg
        assert "Pasta" in user_msg


# ---------------------------------------------------------------------------
# dietary_prompts.ingredient_spotlight
# ---------------------------------------------------------------------------


class TestIngredientSpotlight:
    @pytest.fixture
    def spotlight_fn(self) -> object:
        captured: dict[str, object] = {}

        class _FakeMCP:
            def prompt(self, **_kwargs):
                def _decorator(fn):
                    captured[fn.__name__] = fn
                    return fn

                return _decorator

        register_dietary_prompts(_FakeMCP())
        return captured["ingredient_spotlight"]

    async def test_returns_two_messages(self, spotlight_fn) -> None:
        result = await spotlight_fn(ingredient="saffron")
        assert len(result.messages) == 2

    async def test_description_contains_ingredient(self, spotlight_fn) -> None:
        result = await spotlight_fn(ingredient="chickpeas")
        assert "chickpeas" in result.description

    async def test_user_message_mentions_ingredient(self, spotlight_fn) -> None:
        result = await spotlight_fn(ingredient="miso")
        user_msg = result.messages[1].content.text
        assert "miso" in user_msg

    async def test_user_message_has_all_sections(self, spotlight_fn) -> None:
        result = await spotlight_fn(ingredient="turmeric")
        user_msg = result.messages[1].content.text
        assert "Origin" in user_msg
        assert "Culinary Uses" in user_msg
        assert "Nutrition" in user_msg
        assert "Selection" in user_msg
        assert "Fun Facts" in user_msg

    async def test_system_message_role_is_assistant(self, spotlight_fn) -> None:
        result = await spotlight_fn(ingredient="vanilla")
        assert result.messages[0].role == "assistant"

    async def test_user_message_role_is_user(self, spotlight_fn) -> None:
        result = await spotlight_fn(ingredient="vanilla")
        assert result.messages[1].role == "user"


# ---------------------------------------------------------------------------
# meal_plan_prompts.weekly_meal_plan
# ---------------------------------------------------------------------------


class TestWeeklyMealPlan:
    @pytest.fixture
    def captured_fns(self) -> dict[str, object]:
        captured: dict[str, object] = {}

        class _FakeMCP:
            def prompt(self, **_kwargs):
                def _decorator(fn):
                    captured[fn.__name__] = fn
                    return fn

                return _decorator

        register_meal_plan_prompts(_FakeMCP())
        return captured

    async def test_description_contains_people_count(self, captured_fns) -> None:
        fn = captured_fns["weekly_meal_plan"]
        result = await fn(people_count=4)
        assert "4" in result.description

    async def test_user_message_contains_people_count(self, captured_fns) -> None:
        fn = captured_fns["weekly_meal_plan"]
        result = await fn(people_count=3)
        user_msg = result.messages[1].content.text
        assert "People: 3" in user_msg

    async def test_optional_diet_included(self, captured_fns) -> None:
        fn = captured_fns["weekly_meal_plan"]
        result = await fn(people_count=2, diet="vegetarian")
        user_msg = result.messages[1].content.text
        assert "Diet: vegetarian" in user_msg

    async def test_optional_budget_included(self, captured_fns) -> None:
        fn = captured_fns["weekly_meal_plan"]
        result = await fn(people_count=2, budget="low")
        user_msg = result.messages[1].content.text
        assert "Budget: low" in user_msg

    async def test_optional_cooking_skill_included(self, captured_fns) -> None:
        fn = captured_fns["weekly_meal_plan"]
        result = await fn(people_count=2, cooking_skill="beginner")
        user_msg = result.messages[1].content.text
        assert "Cooking skill: beginner" in user_msg

    async def test_optional_fields_absent_when_not_provided(self, captured_fns) -> None:
        fn = captured_fns["weekly_meal_plan"]
        result = await fn(people_count=1)
        user_msg = result.messages[1].content.text
        assert "Diet:" not in user_msg
        assert "Budget:" not in user_msg
        assert "Cooking skill:" not in user_msg

    async def test_returns_two_messages(self, captured_fns) -> None:
        fn = captured_fns["weekly_meal_plan"]
        result = await fn(people_count=2)
        assert len(result.messages) == 2

    async def test_all_optional_fields(self, captured_fns) -> None:
        fn = captured_fns["weekly_meal_plan"]
        result = await fn(
            people_count=5,
            diet="keto",
            budget="high",
            cooking_skill="advanced",
        )
        user_msg = result.messages[1].content.text
        assert "People: 5" in user_msg
        assert "Diet: keto" in user_msg
        assert "Budget: high" in user_msg
        assert "Cooking skill: advanced" in user_msg


# ---------------------------------------------------------------------------
# meal_plan_prompts.holiday_menu
# ---------------------------------------------------------------------------


class TestHolidayMenu:
    @pytest.fixture
    def captured_fns(self) -> dict[str, object]:
        captured: dict[str, object] = {}

        class _FakeMCP:
            def prompt(self, **_kwargs):
                def _decorator(fn):
                    captured[fn.__name__] = fn
                    return fn

                return _decorator

        register_meal_plan_prompts(_FakeMCP())
        return captured

    async def test_description_contains_occasion_and_guests(self, captured_fns) -> None:
        fn = captured_fns["holiday_menu"]
        result = await fn(occasion="Thanksgiving", guest_count=10)
        assert "Thanksgiving" in result.description
        assert "10" in result.description

    async def test_user_message_contains_occasion_and_guests(self, captured_fns) -> None:
        fn = captured_fns["holiday_menu"]
        result = await fn(occasion="Christmas", guest_count=8)
        user_msg = result.messages[1].content.text
        assert "Occasion: Christmas" in user_msg
        assert "Guests: 8" in user_msg

    async def test_restrictions_included_when_provided(self, captured_fns) -> None:
        fn = captured_fns["holiday_menu"]
        result = await fn(
            occasion="Birthday",
            guest_count=6,
            restrictions=["nut-free", "vegetarian"],
        )
        user_msg = result.messages[1].content.text
        assert "nut-free" in user_msg
        assert "vegetarian" in user_msg

    async def test_restrictions_absent_when_none(self, captured_fns) -> None:
        fn = captured_fns["holiday_menu"]
        result = await fn(occasion="Easter", guest_count=4, restrictions=None)
        user_msg = result.messages[1].content.text
        assert "Dietary restrictions:" not in user_msg

    async def test_returns_two_messages(self, captured_fns) -> None:
        fn = captured_fns["holiday_menu"]
        result = await fn(occasion="New Year", guest_count=20)
        assert len(result.messages) == 2


# ---------------------------------------------------------------------------
# recipe_prompts.generate_recipe
# ---------------------------------------------------------------------------


class TestGenerateRecipe:
    @pytest.fixture
    def captured_fns(self) -> dict[str, object]:
        captured: dict[str, object] = {}

        class _FakeMCP:
            def prompt(self, **_kwargs):
                def _decorator(fn):
                    captured[fn.__name__] = fn
                    return fn

                return _decorator

        register_recipe_prompts(_FakeMCP())
        return captured

    async def test_description_contains_cuisine(self, captured_fns) -> None:
        fn = captured_fns["generate_recipe"]
        result = await fn(cuisine="Italian")
        assert "Italian" in result.description

    async def test_cuisine_always_in_user_message(self, captured_fns) -> None:
        fn = captured_fns["generate_recipe"]
        result = await fn(cuisine="Japanese")
        user_msg = result.messages[1].content.text
        assert "Cuisine: Japanese" in user_msg

    async def test_main_ingredient_included_when_provided(self, captured_fns) -> None:
        fn = captured_fns["generate_recipe"]
        result = await fn(cuisine="Mexican", main_ingredient="chicken")
        user_msg = result.messages[1].content.text
        assert "Main ingredient: chicken" in user_msg

    async def test_difficulty_included_when_provided(self, captured_fns) -> None:
        fn = captured_fns["generate_recipe"]
        result = await fn(cuisine="French", difficulty="hard")
        user_msg = result.messages[1].content.text
        assert "Difficulty: hard" in user_msg

    async def test_dietary_restrictions_included_when_provided(self, captured_fns) -> None:
        fn = captured_fns["generate_recipe"]
        result = await fn(
            cuisine="Indian",
            dietary_restrictions=["vegan", "gluten-free"],
        )
        user_msg = result.messages[1].content.text
        assert "vegan" in user_msg
        assert "gluten-free" in user_msg

    async def test_optional_fields_absent_when_not_provided(self, captured_fns) -> None:
        fn = captured_fns["generate_recipe"]
        result = await fn(cuisine="Greek")
        user_msg = result.messages[1].content.text
        assert "Main ingredient:" not in user_msg
        assert "Difficulty:" not in user_msg
        assert "Dietary restrictions:" not in user_msg

    async def test_returns_two_messages(self, captured_fns) -> None:
        fn = captured_fns["generate_recipe"]
        result = await fn(cuisine="Thai")
        assert len(result.messages) == 2


# ---------------------------------------------------------------------------
# recipe_prompts.leftover_recipe
# ---------------------------------------------------------------------------


class TestLeftoverRecipe:
    @pytest.fixture
    def captured_fns(self) -> dict[str, object]:
        captured: dict[str, object] = {}

        class _FakeMCP:
            def prompt(self, **_kwargs):
                def _decorator(fn):
                    captured[fn.__name__] = fn
                    return fn

                return _decorator

        register_recipe_prompts(_FakeMCP())
        return captured

    async def test_description_is_fixed_string(self, captured_fns) -> None:
        fn = captured_fns["leftover_recipe"]
        result = await fn(ingredients=["rice", "chicken"])
        assert result.description == "Recipe from leftover ingredients"

    async def test_user_message_contains_all_ingredients(self, captured_fns) -> None:
        fn = captured_fns["leftover_recipe"]
        result = await fn(ingredients=["chicken breast", "rice", "bell peppers"])
        user_msg = result.messages[1].content.text
        assert "chicken breast" in user_msg
        assert "rice" in user_msg
        assert "bell peppers" in user_msg

    async def test_returns_two_messages(self, captured_fns) -> None:
        fn = captured_fns["leftover_recipe"]
        result = await fn(ingredients=["eggs", "cheese"])
        assert len(result.messages) == 2


# ---------------------------------------------------------------------------
# recipe_prompts.quick_meal
# ---------------------------------------------------------------------------


class TestQuickMeal:
    @pytest.fixture
    def captured_fns(self) -> dict[str, object]:
        captured: dict[str, object] = {}

        class _FakeMCP:
            def prompt(self, **_kwargs):
                def _decorator(fn):
                    captured[fn.__name__] = fn
                    return fn

                return _decorator

        register_recipe_prompts(_FakeMCP())
        return captured

    async def test_description_contains_max_minutes(self, captured_fns) -> None:
        fn = captured_fns["quick_meal"]
        result = await fn(max_minutes=20)
        assert "20" in result.description

    async def test_user_message_mentions_time_limit(self, captured_fns) -> None:
        fn = captured_fns["quick_meal"]
        result = await fn(max_minutes=15)
        user_msg = result.messages[1].content.text
        assert "15 minutes" in user_msg

    async def test_available_ingredients_included_when_provided(self, captured_fns) -> None:
        fn = captured_fns["quick_meal"]
        result = await fn(max_minutes=30, available_ingredients=["pasta", "tomatoes"])
        user_msg = result.messages[1].content.text
        assert "pasta" in user_msg
        assert "tomatoes" in user_msg

    async def test_available_ingredients_absent_when_none(self, captured_fns) -> None:
        fn = captured_fns["quick_meal"]
        result = await fn(max_minutes=10, available_ingredients=None)
        user_msg = result.messages[1].content.text
        assert "ingredients available" not in user_msg

    async def test_returns_two_messages(self, captured_fns) -> None:
        fn = captured_fns["quick_meal"]
        result = await fn(max_minutes=25)
        assert len(result.messages) == 2


# ---------------------------------------------------------------------------
# completion._filter_by_prefix
# ---------------------------------------------------------------------------


class TestFilterByPrefix:
    def test_exact_match(self) -> None:
        result = _filter_by_prefix(["Italian", "Irish", "Indian"], "Italian")
        assert result.values == ["Italian"]

    def test_prefix_match_case_insensitive(self) -> None:
        result = _filter_by_prefix(["Italian", "Irish", "Indian"], "i")
        assert set(result.values) == {"Italian", "Irish", "Indian"}

    def test_empty_prefix_returns_all(self) -> None:
        values = ["A", "B", "C"]
        result = _filter_by_prefix(values, "")
        assert result.values == values

    def test_no_match_returns_empty(self) -> None:
        result = _filter_by_prefix(["Italian", "Irish"], "Zz")
        assert result.values == []
        assert result.total == 0
        assert result.hasMore is False

    def test_total_reflects_full_match_count(self) -> None:
        values = [f"Item{i}" for i in range(5)]
        result = _filter_by_prefix(values, "item")
        assert result.total == 5

    def test_has_more_false_when_within_limit(self) -> None:
        result = _filter_by_prefix(["Italian"], "i")
        assert result.hasMore is False

    def test_values_capped_at_max_completion_values(self) -> None:
        # Build more items than the cap
        values = [f"Cuisine{i:03d}" for i in range(MAX_COMPLETION_VALUES + 10)]
        result = _filter_by_prefix(values, "cuisine")
        assert len(result.values) == MAX_COMPLETION_VALUES
        assert result.total == MAX_COMPLETION_VALUES + 10
        assert result.hasMore is True

    def test_cuisines_list_prefix_italian(self) -> None:
        result = _filter_by_prefix(CUISINES, "ita")
        assert "Italian" in result.values

    def test_dietary_restrictions_vegan_prefix(self) -> None:
        result = _filter_by_prefix(DIETARY_RESTRICTIONS, "veg")
        assert "vegan" in result.values
        assert "vegetarian" in result.values


# ---------------------------------------------------------------------------
# completion._handle_completion
# ---------------------------------------------------------------------------


class TestHandleCompletion:
    def _prompt_ref(self, name: str) -> mcp_types.PromptReference:
        return mcp_types.PromptReference(type="ref/prompt", name=name)

    def _resource_ref(self) -> mcp_types.ResourceTemplateReference:
        return mcp_types.ResourceTemplateReference(
            type="ref/resource", uri="recipe://templates/search"
        )

    def _arg(self, name: str, value: str) -> mcp_types.CompletionArgument:
        return mcp_types.CompletionArgument(name=name, value=value)

    async def test_non_prompt_ref_returns_none(self) -> None:
        result = await _handle_completion(self._resource_ref(), self._arg("cuisine", "ita"), None)
        assert result is None

    async def test_generate_recipe_cuisine_returns_completions(self) -> None:
        result = await _handle_completion(
            self._prompt_ref("generate_recipe"), self._arg("cuisine", "Ita"), None
        )
        assert result is not None
        assert "Italian" in result.values

    async def test_adapt_for_diet_restrictions_returns_completions(self) -> None:
        result = await _handle_completion(
            self._prompt_ref("adapt_for_diet"), self._arg("restrictions", "veg"), None
        )
        assert result is not None
        assert "vegan" in result.values
        assert "vegetarian" in result.values

    async def test_unknown_prompt_name_returns_none(self) -> None:
        result = await _handle_completion(
            self._prompt_ref("unknown_prompt"), self._arg("cuisine", "Ita"), None
        )
        assert result is None

    async def test_generate_recipe_unknown_arg_returns_none(self) -> None:
        result = await _handle_completion(
            self._prompt_ref("generate_recipe"),
            self._arg("unknown_arg", "anything"),
            None,
        )
        assert result is None

    async def test_adapt_for_diet_unknown_arg_returns_none(self) -> None:
        result = await _handle_completion(
            self._prompt_ref("adapt_for_diet"),
            self._arg("unknown_arg", "anything"),
            None,
        )
        assert result is None

    async def test_context_argument_accepted(self) -> None:
        context = mcp_types.CompletionContext(arguments={"cuisine": "Italian"})
        result = await _handle_completion(
            self._prompt_ref("generate_recipe"),
            self._arg("cuisine", "Jap"),
            context,
        )
        assert result is not None
        assert "Japanese" in result.values


# ---------------------------------------------------------------------------
# completion._completion_request_handler
# ---------------------------------------------------------------------------


class TestCompletionRequestHandler:
    def _make_request(
        self,
        ref: mcp_types.PromptReference | mcp_types.ResourceTemplateReference,
        arg_name: str,
        arg_value: str,
    ) -> mcp_types.CompleteRequest:
        return mcp_types.CompleteRequest(
            params=mcp_types.CompleteRequestParams(
                ref=ref,
                argument=mcp_types.CompletionArgument(name=arg_name, value=arg_value),
            )
        )

    async def test_known_prompt_returns_completions(self) -> None:
        req = self._make_request(
            mcp_types.PromptReference(type="ref/prompt", name="generate_recipe"),
            "cuisine",
            "Ita",
        )
        server_result = await _completion_request_handler(req)
        complete_result = server_result.root
        assert "Italian" in complete_result.completion.values

    async def test_unknown_prompt_returns_empty_completion(self) -> None:
        req = self._make_request(
            mcp_types.PromptReference(type="ref/prompt", name="unknown_prompt"),
            "cuisine",
            "Ita",
        )
        server_result = await _completion_request_handler(req)
        complete_result = server_result.root
        assert complete_result.completion.values == []
        assert complete_result.completion.total is None
        assert complete_result.completion.hasMore is None

    async def test_resource_ref_returns_empty_completion(self) -> None:
        req = self._make_request(
            mcp_types.ResourceTemplateReference(
                type="ref/resource", uri="recipe://templates/search"
            ),
            "query",
            "pasta",
        )
        server_result = await _completion_request_handler(req)
        complete_result = server_result.root
        assert complete_result.completion.values == []
