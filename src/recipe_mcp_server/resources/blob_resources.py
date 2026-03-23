"""Binary/blob MCP resources for recipe photos and nutrition charts."""

from __future__ import annotations

import io
import math
from typing import cast

import httpx
import structlog
from fastmcp import Context, FastMCP
from PIL import Image, ImageDraw, ImageFont

from recipe_mcp_server.clients.foodish import FoodishClient
from recipe_mcp_server.exceptions import ExternalAPIError, NotFoundError
from recipe_mcp_server.models.nutrition import NutrientInfo
from recipe_mcp_server.services.nutrition_service import NutritionService
from recipe_mcp_server.services.recipe_service import RecipeService

logger = structlog.get_logger(__name__)

# -- Constants ----------------------------------------------------------------

CHART_SIZE = 400
IMAGE_FETCH_TIMEOUT = 10.0

# RGB colors for pie chart slices: Protein (green), Fat (orange), Carbs (blue)
CHART_COLORS = (
    (76, 175, 80),  # Protein — green
    (255, 152, 0),  # Fat — orange
    (33, 150, 243),  # Carbs — blue
)

CHART_BG_COLOR = (255, 255, 255)
CHART_TEXT_COLOR = (51, 51, 51)

ERROR_IMAGE_SIZE = 200


# -- Context helpers ----------------------------------------------------------


def _get_recipe_service(ctx: Context) -> RecipeService:
    """Extract RecipeService from the lifespan context."""
    return cast(RecipeService, ctx.lifespan_context["recipe_service"])


def _get_nutrition_service(ctx: Context) -> NutritionService:
    """Extract NutritionService from the lifespan context."""
    return cast(NutritionService, ctx.lifespan_context["nutrition_service"])


def _get_foodish_client(ctx: Context) -> FoodishClient:
    """Extract FoodishClient from the lifespan context."""
    return cast(FoodishClient, ctx.lifespan_context["foodish_client"])


# -- Pure rendering functions -------------------------------------------------


def render_photo_png(image_data: bytes) -> bytes:
    """Convert raw image bytes (any format Pillow supports) to PNG.

    Pure function — no I/O. Accepts raw image data, returns PNG bytes.
    """
    raw = Image.open(io.BytesIO(image_data))
    img = raw.convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_macro_chart(nutrients: NutrientInfo, food_name: str) -> bytes:
    """Generate a macronutrient pie chart as PNG bytes.

    Pure function — no I/O. Creates a pie chart with slices for
    protein, fat, and carbs using Pillow drawing primitives.
    """
    slices = [
        ("Protein", nutrients.protein_g, CHART_COLORS[0]),
        ("Fat", nutrients.fat_g, CHART_COLORS[1]),
        ("Carbs", nutrients.carbs_g, CHART_COLORS[2]),
    ]

    total = sum(s[1] for s in slices)

    img = Image.new("RGB", (CHART_SIZE, CHART_SIZE), CHART_BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Title
    title_font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
        label_font = ImageFont.truetype("DejaVuSans.ttf", 12)
    except OSError:
        title_font = ImageFont.load_default()
        label_font = title_font

    # Draw title centered at top
    title_bbox = draw.textbbox((0, 0), food_name, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(((CHART_SIZE - title_w) / 2, 10), food_name, fill=CHART_TEXT_COLOR, font=title_font)

    # Pie chart area
    pie_margin = 60
    pie_box = (pie_margin, 40, CHART_SIZE - pie_margin, CHART_SIZE - pie_margin)

    if total <= 0:
        # No data — draw empty circle with message
        draw.ellipse(pie_box, outline=(200, 200, 200), width=2)
        no_data = "No macronutrient data"
        nd_bbox = draw.textbbox((0, 0), no_data, font=label_font)
        nd_w = nd_bbox[2] - nd_bbox[0]
        draw.text(
            ((CHART_SIZE - nd_w) / 2, CHART_SIZE / 2),
            no_data,
            fill=CHART_TEXT_COLOR,
            font=label_font,
        )
    else:
        # Draw pie slices
        start_angle = -90.0  # Start from top
        pie_cx = (pie_box[0] + pie_box[2]) / 2
        pie_cy = (pie_box[1] + pie_box[3]) / 2
        pie_r = (pie_box[2] - pie_box[0]) / 2

        for name, value, color in slices:
            if value <= 0:
                continue
            sweep = (value / total) * 360
            draw.pieslice(pie_box, start_angle, start_angle + sweep, fill=color)

            # Place label at midpoint angle
            mid_angle = math.radians(start_angle + sweep / 2)
            label_r = pie_r * 0.65
            lx = pie_cx + label_r * math.cos(mid_angle)
            ly = pie_cy + label_r * math.sin(mid_angle)
            label_text = f"{name}\n{value:g}g"
            lb_bbox = draw.textbbox((0, 0), label_text, font=label_font)
            lb_w = lb_bbox[2] - lb_bbox[0]
            lb_h = lb_bbox[3] - lb_bbox[1]
            draw.text(
                (lx - lb_w / 2, ly - lb_h / 2),
                label_text,
                fill=(255, 255, 255),
                font=label_font,
                align="center",
            )

            start_angle += sweep

    # Legend at bottom
    legend_y = CHART_SIZE - pie_margin + 10
    legend_x = 20
    for name, value, color in slices:
        draw.rectangle((legend_x, legend_y, legend_x + 12, legend_y + 12), fill=color)
        draw.text(
            (legend_x + 16, legend_y - 1),
            f"{name}: {value:g}g",
            fill=CHART_TEXT_COLOR,
            font=label_font,
        )
        legend_x += 130

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_error_png(message: str) -> bytes:
    """Generate a small error placeholder PNG with a text message.

    Pure function — no I/O.
    """
    img = Image.new("RGB", (ERROR_IMAGE_SIZE, ERROR_IMAGE_SIZE), (245, 245, 245))
    draw = ImageDraw.Draw(img)

    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 12)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), message, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    draw.text(
        ((ERROR_IMAGE_SIZE - text_w) / 2, (ERROR_IMAGE_SIZE - text_h) / 2),
        message,
        fill=(180, 0, 0),
        font=font,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# -- Async helpers ------------------------------------------------------------


async def fetch_image_bytes(url: str) -> bytes:
    """Fetch image bytes from a URL using a short-lived HTTP client."""
    async with httpx.AsyncClient(timeout=IMAGE_FETCH_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


# -- Registration -------------------------------------------------------------


def register_blob_resources(mcp: FastMCP) -> None:
    """Register binary/blob resources on the FastMCP server."""

    @mcp.resource(
        "recipe://photo/{recipe_id}",
        name="recipe_photo",
        description=(
            "Recipe photo as PNG. Fetched from TheMealDB thumbnail or "
            "Foodish fallback, converted to PNG blob."
        ),
        mime_type="image/png",
        tags={"recipe", "blob"},
    )
    async def recipe_photo(recipe_id: str, ctx: Context) -> bytes:
        """Return a recipe photo as PNG bytes."""
        service = _get_recipe_service(ctx)
        foodish = _get_foodish_client(ctx)

        try:
            recipe = await service.get(recipe_id)
            image_url = recipe.image_url

            if not image_url:
                # Fallback to Foodish random image
                image_url = await foodish.random_image()
                if not image_url:
                    return render_error_png("No image available")

            raw_bytes = await fetch_image_bytes(image_url)
            return render_photo_png(raw_bytes)

        except NotFoundError as exc:
            logger.warning("recipe_photo_not_found", recipe_id=recipe_id, error=str(exc))
            return render_error_png(f"Recipe not found: {recipe_id}")
        except (httpx.HTTPError, ExternalAPIError, OSError) as exc:
            logger.warning("recipe_photo_fetch_error", recipe_id=recipe_id, error=str(exc))
            return render_error_png("Image unavailable")

    @mcp.resource(
        "nutrition://chart/{food_name}",
        name="nutrition_chart",
        description=(
            "Macronutrient pie chart (protein/fat/carbs) as PNG. "
            "Generated server-side from USDA nutrition data using Pillow."
        ),
        mime_type="image/png",
        tags={"nutrition", "blob"},
    )
    async def nutrition_chart(food_name: str, ctx: Context) -> bytes:
        """Return a macronutrient pie chart as PNG bytes."""
        service = _get_nutrition_service(ctx)

        try:
            info = await service.lookup(food_name)
            return render_macro_chart(info, food_name)
        except (NotFoundError, ExternalAPIError) as exc:
            logger.warning("nutrition_chart_error", food_name=food_name, error=str(exc))
            return render_error_png(f"No data for: {food_name}")
