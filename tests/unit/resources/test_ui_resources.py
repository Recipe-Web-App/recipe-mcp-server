"""Tests for HTML UI resources (recipe card and nutrition label)."""

from __future__ import annotations

import pytest

from recipe_mcp_server.models.nutrition import NutrientInfo
from recipe_mcp_server.models.recipe import Ingredient, Recipe
from recipe_mcp_server.resources.ui_resources import (
    _pct_dv,
    render_nutrition_label,
    render_recipe_card,
)


@pytest.fixture()
def sample_recipe() -> Recipe:
    return Recipe(
        id="test-123",
        title="Spaghetti Carbonara",
        category="Pasta",
        area="Italian",
        image_url="https://example.com/carbonara.jpg",
        prep_time_min=10,
        cook_time_min=20,
        servings=4,
        ingredients=[
            Ingredient(name="Spaghetti", quantity=400, unit="g", order_index=0),
            Ingredient(name="Guanciale", quantity=200, unit="g", order_index=1),
            Ingredient(name="Egg Yolks", quantity=4, unit=None, notes="large", order_index=2),
        ],
        instructions=[
            "Boil pasta in salted water until al dente.",
            "Crisp guanciale in a skillet over medium heat.",
            "Whisk egg yolks with pecorino.",
            "Toss hot pasta with guanciale, then stir in egg mixture off heat.",
        ],
    )


@pytest.fixture()
def minimal_recipe() -> Recipe:
    return Recipe(title="Simple Toast")


@pytest.fixture()
def sample_nutrients() -> NutrientInfo:
    return NutrientInfo(
        calories=250,
        protein_g=12.5,
        fat_g=8,
        carbs_g=30,
        fiber_g=3.5,
        sugar_g=6,
        sodium_mg=480,
    )


class TestRenderRecipeCard:
    def test_contains_title(self, sample_recipe: Recipe) -> None:
        html = render_recipe_card(sample_recipe)
        assert "Spaghetti Carbonara" in html

    def test_contains_image(self, sample_recipe: Recipe) -> None:
        html = render_recipe_card(sample_recipe)
        assert "https://example.com/carbonara.jpg" in html

    def test_no_image_when_absent(self, minimal_recipe: Recipe) -> None:
        html = render_recipe_card(minimal_recipe)
        assert "<img" not in html

    def test_contains_category_badge(self, sample_recipe: Recipe) -> None:
        html = render_recipe_card(sample_recipe)
        assert "Pasta" in html
        assert "Italian" in html

    def test_contains_time_info(self, sample_recipe: Recipe) -> None:
        html = render_recipe_card(sample_recipe)
        assert "Prep: 10 min" in html
        assert "Cook: 20 min" in html
        assert "Total: 30 min" in html

    def test_contains_servings(self, sample_recipe: Recipe) -> None:
        html = render_recipe_card(sample_recipe)
        assert "Servings: 4" in html

    def test_contains_ingredients(self, sample_recipe: Recipe) -> None:
        html = render_recipe_card(sample_recipe)
        assert "Spaghetti" in html
        assert "400 g" in html
        assert "Guanciale" in html
        assert "Egg Yolks" in html
        assert "(large)" in html

    def test_contains_instructions(self, sample_recipe: Recipe) -> None:
        html = render_recipe_card(sample_recipe)
        assert "Boil pasta in salted water until al dente." in html
        assert "<ol>" in html
        assert "<li>" in html

    def test_html_escapes_title(self) -> None:
        recipe = Recipe(title='Eggs & "Toast" <br>')
        html = render_recipe_card(recipe)
        assert "Eggs &amp; &quot;Toast&quot; &lt;br&gt;" in html

    def test_minimal_recipe_renders(self, minimal_recipe: Recipe) -> None:
        html = render_recipe_card(minimal_recipe)
        assert "Simple Toast" in html
        assert "<!DOCTYPE html>" in html

    def test_is_valid_html_document(self, sample_recipe: Recipe) -> None:
        html = render_recipe_card(sample_recipe)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html


class TestRenderNutritionLabel:
    def test_contains_food_name(self, sample_nutrients: NutrientInfo) -> None:
        html = render_nutrition_label(sample_nutrients, "Chicken Breast")
        assert "Chicken Breast" in html

    def test_contains_calories(self, sample_nutrients: NutrientInfo) -> None:
        html = render_nutrition_label(sample_nutrients, "Chicken Breast")
        assert "250" in html

    def test_contains_macronutrients(self, sample_nutrients: NutrientInfo) -> None:
        html = render_nutrition_label(sample_nutrients, "Chicken Breast")
        assert "Total Fat" in html
        assert "8g" in html
        assert "Total Carbohydrate" in html
        assert "30g" in html
        assert "Protein" in html
        assert "12.5g" in html

    def test_contains_fiber_and_sugar(self, sample_nutrients: NutrientInfo) -> None:
        html = render_nutrition_label(sample_nutrients, "Chicken Breast")
        assert "Dietary Fiber" in html
        assert "3.5g" in html
        assert "Total Sugars" in html
        assert "6g" in html

    def test_contains_sodium(self, sample_nutrients: NutrientInfo) -> None:
        html = render_nutrition_label(sample_nutrients, "Chicken Breast")
        assert "Sodium" in html
        assert "480mg" in html

    def test_contains_percent_daily_values(self, sample_nutrients: NutrientInfo) -> None:
        html = render_nutrition_label(sample_nutrients, "Chicken Breast")
        assert "% Daily Value" in html

    def test_contains_footnote(self, sample_nutrients: NutrientInfo) -> None:
        html = render_nutrition_label(sample_nutrients, "Chicken Breast")
        assert "2,000 calorie diet" in html

    def test_html_escapes_food_name(self) -> None:
        nutrients = NutrientInfo()
        html = render_nutrition_label(nutrients, 'Beef & "Broccoli"')
        assert "Beef &amp; &quot;Broccoli&quot;" in html

    def test_is_valid_html_document(self, sample_nutrients: NutrientInfo) -> None:
        html = render_nutrition_label(sample_nutrients, "Apple")
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_zero_nutrients_renders(self) -> None:
        nutrients = NutrientInfo()
        html = render_nutrition_label(nutrients, "Water")
        assert "Water" in html
        assert "Nutrition Facts" in html


class TestPctDv:
    def test_normal_calculation(self) -> None:
        assert _pct_dv(78, 78) == 100

    def test_zero_daily_value(self) -> None:
        assert _pct_dv(10, 0) == 0

    def test_zero_value(self) -> None:
        assert _pct_dv(0, 78) == 0

    def test_partial_value(self) -> None:
        assert _pct_dv(39, 78) == 50
