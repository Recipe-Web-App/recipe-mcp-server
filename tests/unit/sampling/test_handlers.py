"""Tests for sampling handlers."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from recipe_mcp_server.models.recipe import Recipe
from recipe_mcp_server.sampling.handlers import (
    MAX_TOKENS_PAIRING,
    MAX_TOKENS_VARIATIONS,
    PAIRING_PROMPT,
    VARIATION_PROMPT,
    pair_ingredients,
    suggest_recipe_variations,
)


@dataclass
class FakeSamplingResult:
    """Minimal stand-in for fastmcp SamplingResult."""

    text: str
    result: str
    history: list[object]


@pytest.fixture
def mock_ctx() -> AsyncMock:
    """Create a mock MCP Context with a sample() method."""
    ctx = AsyncMock()
    ctx.sample = AsyncMock()
    return ctx


@pytest.fixture
def sample_recipe() -> Recipe:
    return Recipe(
        id="test-123",
        title="Classic Margherita Pizza",
        category="Main",
        area="Italian",
    )


@pytest.mark.asyncio
async def test_suggest_recipe_variations_calls_sample(
    mock_ctx: AsyncMock, sample_recipe: Recipe
) -> None:
    """suggest_recipe_variations should call ctx.sample with the correct prompt."""
    mock_ctx.sample.return_value = FakeSamplingResult(
        text="1. Fusion: ...\n2. Seasonal: ...\n3. Simplified: ...",
        result="1. Fusion: ...\n2. Seasonal: ...\n3. Simplified: ...",
        history=[],
    )

    result = await suggest_recipe_variations(mock_ctx, sample_recipe)

    expected_prompt = VARIATION_PROMPT.format(title="Classic Margherita Pizza")
    mock_ctx.sample.assert_awaited_once_with(expected_prompt, max_tokens=MAX_TOKENS_VARIATIONS)
    assert result == "1. Fusion: ...\n2. Seasonal: ...\n3. Simplified: ..."


@pytest.mark.asyncio
async def test_suggest_recipe_variations_returns_text(
    mock_ctx: AsyncMock, sample_recipe: Recipe
) -> None:
    """suggest_recipe_variations should return the text from the sampling result."""
    expected = "Three great variations for this pizza"
    mock_ctx.sample.return_value = FakeSamplingResult(text=expected, result=expected, history=[])

    result = await suggest_recipe_variations(mock_ctx, sample_recipe)

    assert result == expected


@pytest.mark.asyncio
async def test_pair_ingredients_calls_sample(mock_ctx: AsyncMock) -> None:
    """pair_ingredients should call ctx.sample with the correct prompt."""
    mock_ctx.sample.return_value = FakeSamplingResult(
        text="1. Jasmine rice ...\n2. Bok choy ...\n3. Pickled ginger ...",
        result="1. Jasmine rice ...\n2. Bok choy ...\n3. Pickled ginger ...",
        history=[],
    )

    result = await pair_ingredients(mock_ctx, "chicken", "Thai")

    expected_prompt = PAIRING_PROMPT.format(main_ingredient="chicken", cuisine="Thai")
    mock_ctx.sample.assert_awaited_once_with(expected_prompt, max_tokens=MAX_TOKENS_PAIRING)
    assert result == "1. Jasmine rice ...\n2. Bok choy ...\n3. Pickled ginger ..."


@pytest.mark.asyncio
async def test_pair_ingredients_returns_text(mock_ctx: AsyncMock) -> None:
    """pair_ingredients should return the text from the sampling result."""
    expected = "Complementary sides: rice, vegetables, sauce"
    mock_ctx.sample.return_value = FakeSamplingResult(text=expected, result=expected, history=[])

    result = await pair_ingredients(mock_ctx, "salmon", "Japanese")

    assert result == expected
