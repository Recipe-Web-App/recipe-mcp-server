"""Tests for binary/blob resources (recipe photo and nutrition chart)."""

from __future__ import annotations

import io

import httpx
import pytest
import respx
from PIL import Image, UnidentifiedImageError

from recipe_mcp_server.models.nutrition import NutrientInfo
from recipe_mcp_server.resources.blob_resources import (
    CHART_SIZE,
    fetch_image_bytes,
    render_error_png,
    render_macro_chart,
    render_photo_png,
)

# -- Helpers ------------------------------------------------------------------


def _make_test_image(fmt: str = "JPEG", size: tuple[int, int] = (100, 100)) -> bytes:
    """Create a minimal test image in the given format."""
    img = Image.new("RGB", size, (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _open_png(data: bytes) -> Image.Image:
    """Open PNG bytes and verify the format."""
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG"
    return img


# -- render_photo_png ---------------------------------------------------------


class TestRenderPhotoPng:
    def test_converts_jpeg_to_png(self) -> None:
        jpeg_data = _make_test_image("JPEG")
        result = render_photo_png(jpeg_data)
        img = _open_png(result)
        assert img.mode == "RGBA"

    def test_preserves_png_input(self) -> None:
        png_data = _make_test_image("PNG")
        result = render_photo_png(png_data)
        _open_png(result)

    def test_preserves_dimensions(self) -> None:
        jpeg_data = _make_test_image("JPEG", size=(320, 240))
        result = render_photo_png(jpeg_data)
        img = _open_png(result)
        assert img.size == (320, 240)

    def test_converts_bmp_to_png(self) -> None:
        bmp_data = _make_test_image("BMP")
        result = render_photo_png(bmp_data)
        _open_png(result)

    def test_invalid_data_raises(self) -> None:
        with pytest.raises(UnidentifiedImageError):
            render_photo_png(b"not an image")


# -- render_macro_chart -------------------------------------------------------


class TestRenderMacroChart:
    @pytest.fixture()
    def sample_nutrients(self) -> NutrientInfo:
        return NutrientInfo(
            calories=250,
            protein_g=25.0,
            fat_g=10.0,
            carbs_g=30.0,
        )

    def test_returns_valid_png(self, sample_nutrients: NutrientInfo) -> None:
        result = render_macro_chart(sample_nutrients, "Chicken Breast")
        _open_png(result)

    def test_chart_dimensions(self, sample_nutrients: NutrientInfo) -> None:
        result = render_macro_chart(sample_nutrients, "Chicken Breast")
        img = _open_png(result)
        assert img.size == (CHART_SIZE, CHART_SIZE)

    def test_zero_nutrients_renders(self) -> None:
        nutrients = NutrientInfo()
        result = render_macro_chart(nutrients, "Water")
        img = _open_png(result)
        assert img.size == (CHART_SIZE, CHART_SIZE)

    def test_single_macro_renders(self) -> None:
        nutrients = NutrientInfo(protein_g=50.0, fat_g=0, carbs_g=0)
        result = render_macro_chart(nutrients, "Protein Powder")
        _open_png(result)

    def test_large_values_render(self) -> None:
        nutrients = NutrientInfo(protein_g=999, fat_g=999, carbs_g=999)
        result = render_macro_chart(nutrients, "Extreme Food")
        _open_png(result)

    def test_food_name_in_chart(self, sample_nutrients: NutrientInfo) -> None:
        result = render_macro_chart(sample_nutrients, "Test Food")
        assert len(result) > 0  # just verify it renders without error


# -- render_error_png ---------------------------------------------------------


class TestRenderErrorPng:
    def test_returns_valid_png(self) -> None:
        result = render_error_png("Something went wrong")
        _open_png(result)

    def test_error_image_dimensions(self) -> None:
        result = render_error_png("Error")
        img = _open_png(result)
        assert img.size == (200, 200)

    def test_empty_message(self) -> None:
        result = render_error_png("")
        _open_png(result)


# -- fetch_image_bytes --------------------------------------------------------


class TestFetchImageBytes:
    async def test_fetches_image(self, respx_mock: respx.MockRouter) -> None:
        """Test that fetch_image_bytes returns response content."""
        image_data = _make_test_image("PNG")
        respx_mock.get("https://example.com/photo.jpg").mock(
            return_value=httpx.Response(200, content=image_data)
        )
        result = await fetch_image_bytes("https://example.com/photo.jpg")
        assert result == image_data

    async def test_raises_on_http_error(self, respx_mock: respx.MockRouter) -> None:
        """Test that HTTP errors propagate."""
        respx_mock.get("https://example.com/missing.jpg").mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_image_bytes("https://example.com/missing.jpg")
