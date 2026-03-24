"""HTML UI resources for recipe cards and nutrition labels."""

from __future__ import annotations

from html import escape
from typing import cast

import structlog
from fastmcp import Context, FastMCP

from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.models.nutrition import NutrientInfo
from recipe_mcp_server.models.recipe import Recipe
from recipe_mcp_server.services.nutrition_service import NutritionService
from recipe_mcp_server.services.recipe_service import RecipeService

logger = structlog.get_logger(__name__)

# FDA recommended daily values for percent calculation
_DAILY_VALUES = {
    "fat_g": 78.0,
    "carbs_g": 275.0,
    "fiber_g": 28.0,
    "protein_g": 50.0,
    "sodium_mg": 2300.0,
    "sugar_g": 50.0,
}


def _get_recipe_service(ctx: Context) -> RecipeService:
    """Extract RecipeService from the lifespan context."""
    return cast(RecipeService, ctx.lifespan_context["recipe_service"])


def _get_nutrition_service(ctx: Context) -> NutritionService:
    """Extract NutritionService from the lifespan context."""
    return cast(NutritionService, ctx.lifespan_context["nutrition_service"])


def _pct_dv(value: float, daily_value: float) -> int:
    """Calculate percent daily value, clamped to 0."""
    if daily_value <= 0:
        return 0
    return round(value / daily_value * 100)


def render_recipe_card(recipe: Recipe) -> str:
    """Render a styled HTML recipe card.

    Pure function — no I/O. Returns a complete HTML document string
    with inline CSS suitable for rendering in MCP clients.
    """
    title = escape(recipe.title)

    # Build metadata badges
    badges: list[str] = []
    if recipe.category:
        badges.append(f'<span class="badge">{escape(recipe.category)}</span>')
    if recipe.area:
        badges.append(f'<span class="badge">{escape(recipe.area)}</span>')
    if recipe.difficulty:
        badges.append(f'<span class="badge">{escape(recipe.difficulty.value)}</span>')
    badges_html = " ".join(badges)

    # Build time and servings info
    meta_items: list[str] = []
    if recipe.prep_time_min is not None:
        meta_items.append(f"Prep: {recipe.prep_time_min} min")
    if recipe.cook_time_min is not None:
        meta_items.append(f"Cook: {recipe.cook_time_min} min")
    total = (recipe.prep_time_min or 0) + (recipe.cook_time_min or 0)
    if total > 0:
        meta_items.append(f"Total: {total} min")
    meta_items.append(f"Servings: {recipe.servings}")
    meta_html = " &middot; ".join(meta_items)

    # Build image section
    image_html = ""
    if recipe.image_url:
        image_html = (
            f'<div class="image-container">'
            f'<img src="{escape(recipe.image_url)}" alt="{title}">'
            f"</div>"
        )

    # Build ingredients list
    ingredient_rows: list[str] = []
    for ing in recipe.ingredients:
        qty = ""
        if ing.quantity is not None:
            qty = f"{ing.quantity:g}"
        unit = escape(ing.unit) if ing.unit else ""
        name = escape(ing.name)
        notes = f" ({escape(ing.notes)})" if ing.notes else ""
        ingredient_rows.append(f"<tr><td>{qty} {unit}</td><td>{name}{notes}</td></tr>")
    ingredients_html = "\n".join(ingredient_rows)

    # Build instructions list
    steps: list[str] = []
    for step in recipe.instructions:
        steps.append(f"<li>{escape(step)}</li>")
    instructions_html = "\n".join(steps)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 0; padding: 16px; background: #f9f9f9; color: #333; }}
  .card {{ max-width: 640px; margin: 0 auto; background: #fff; border-radius: 12px;
           box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow: hidden; }}
  .image-container {{ width: 100%; }}
  .image-container img {{ width: 100%; height: auto; display: block; }}
  .content {{ padding: 20px; }}
  h1 {{ margin: 0 0 8px; font-size: 1.5rem; }}
  .badges {{ margin-bottom: 8px; }}
  .badge {{ display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 2px 10px;
            border-radius: 12px; font-size: 0.8rem; margin-right: 4px; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 16px; }}
  h2 {{ font-size: 1.1rem; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; }}
  td {{ padding: 4px 8px; border-bottom: 1px solid #f0f0f0; }}
  td:first-child {{ white-space: nowrap; color: #666; width: 30%; }}
  ol {{ padding-left: 20px; }}
  li {{ margin-bottom: 8px; line-height: 1.5; }}
</style>
</head>
<body>
<div class="card">
  {image_html}
  <div class="content">
    <h1>{title}</h1>
    <div class="badges">{badges_html}</div>
    <div class="meta">{meta_html}</div>
    <h2>Ingredients</h2>
    <table>{ingredients_html}</table>
    <h2>Instructions</h2>
    <ol>{instructions_html}</ol>
  </div>
</div>
</body>
</html>"""


def render_nutrition_label(nutrients: NutrientInfo, food_name: str) -> str:
    """Render an FDA-style nutrition facts label as HTML.

    Pure function — no I/O. Returns a complete HTML document string
    with inline CSS mimicking the standard FDA nutrition facts panel.
    """
    n = nutrients
    food_name = escape(food_name)

    rows = [
        ("Total Fat", f"{n.fat_g:g}g", _pct_dv(n.fat_g, _DAILY_VALUES["fat_g"]), True),
        (
            "Total Carbohydrate",
            f"{n.carbs_g:g}g",
            _pct_dv(n.carbs_g, _DAILY_VALUES["carbs_g"]),
            True,
        ),
        ("Dietary Fiber", f"{n.fiber_g:g}g", _pct_dv(n.fiber_g, _DAILY_VALUES["fiber_g"]), False),
        ("Total Sugars", f"{n.sugar_g:g}g", _pct_dv(n.sugar_g, _DAILY_VALUES["sugar_g"]), False),
        ("Protein", f"{n.protein_g:g}g", _pct_dv(n.protein_g, _DAILY_VALUES["protein_g"]), True),
        ("Sodium", f"{n.sodium_mg:g}mg", _pct_dv(n.sodium_mg, _DAILY_VALUES["sodium_mg"]), True),
    ]

    row_html_parts: list[str] = []
    for label, amount, pct, is_bold in rows:
        weight = "bold" if is_bold else "normal"
        indent = "padding-left: 16px;" if not is_bold else ""
        row_html_parts.append(
            f'<tr><td style="font-weight:{weight};{indent}">{label}</td>'
            f"<td>{amount}</td>"
            f"<td><b>{pct}%</b></td></tr>"
        )
    nutrient_rows = "\n".join(row_html_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nutrition Facts — {food_name}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 16px;
         background: #f9f9f9; color: #000; }}
  .label {{ max-width: 320px; margin: 0 auto; border: 2px solid #000; padding: 4px 8px;
            background: #fff; }}
  .title {{ font-size: 1.8rem; font-weight: 900; margin: 0; }}
  .food-name {{ font-size: 0.9rem; color: #555; margin-bottom: 4px; }}
  .thick-bar {{ border-top: 8px solid #000; margin: 4px 0; }}
  .thin-bar {{ border-top: 1px solid #000; margin: 2px 0; }}
  .medium-bar {{ border-top: 4px solid #000; margin: 4px 0; }}
  .calories-row {{ display: flex; justify-content: space-between; align-items: baseline; }}
  .calories-label {{ font-size: 0.9rem; font-weight: bold; }}
  .calories-value {{ font-size: 2rem; font-weight: 900; }}
  .dv-header {{ text-align: right; font-size: 0.75rem; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ padding: 2px 0; font-size: 0.85rem; border-bottom: 1px solid #ddd; }}
  td:last-child {{ text-align: right; white-space: nowrap; }}
  td:nth-child(2) {{ text-align: right; padding-right: 8px; }}
  .footnote {{ font-size: 0.7rem; color: #555; margin-top: 4px; }}
</style>
</head>
<body>
<div class="label">
  <p class="title">Nutrition Facts</p>
  <p class="food-name">{food_name}</p>
  <div class="thick-bar"></div>
  <div class="calories-row">
    <span class="calories-label">Calories</span>
    <span class="calories-value">{n.calories:g}</span>
  </div>
  <div class="medium-bar"></div>
  <div class="dv-header">% Daily Value*</div>
  <div class="thin-bar"></div>
  <table>{nutrient_rows}</table>
  <div class="medium-bar"></div>
  <p class="footnote">* Percent Daily Values are based on a 2,000 calorie diet.</p>
</div>
</body>
</html>"""


def register_ui_resources(mcp: FastMCP) -> None:
    """Register HTML UI resources on the FastMCP server."""

    @mcp.resource(
        "recipe://card/{recipe_id}",
        name="recipe_card",
        description=(
            "HTML-rendered recipe card with image, ingredients, and instructions "
            "— styled for display in supporting MCP clients"
        ),
        mime_type="text/html",
        tags={"recipe"},
    )
    async def recipe_card(recipe_id: str, ctx: Context) -> str:
        """Return a styled HTML recipe card."""
        service = _get_recipe_service(ctx)
        try:
            recipe = await service.get(recipe_id)
            return render_recipe_card(recipe)
        except NotFoundError as exc:
            return f"<html><body><p>Error: {escape(str(exc))}</p></body></html>"

    @mcp.resource(
        "nutrition://label/{food_name}",
        name="nutrition_label",
        description="HTML-rendered FDA-style nutrition facts label",
        mime_type="text/html",
        tags={"nutrition"},
    )
    async def nutrition_label(food_name: str, ctx: Context) -> str:
        """Return an FDA-style nutrition facts label as HTML."""
        service = _get_nutrition_service(ctx)
        try:
            info = await service.lookup(food_name)
            return render_nutrition_label(info, food_name)
        except (NotFoundError, ExternalAPIError) as exc:
            return f"<html><body><p>Error: {escape(str(exc))}</p></body></html>"
