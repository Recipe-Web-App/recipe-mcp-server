"""Unit conversion service for cooking measurements."""

from __future__ import annotations

from typing import Any

import structlog

from recipe_mcp_server.clients.spoonacular import SpoonacularClient

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Unit alias mapping: alternate spellings -> canonical name
# ---------------------------------------------------------------------------
_UNIT_ALIASES: dict[str, str] = {
    "cups": "cup",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "fluid_ounce": "fl_oz",
    "fluid_ounces": "fl_oz",
    "fluid ounce": "fl_oz",
    "fluid ounces": "fl_oz",
    "pints": "pint",
    "quarts": "quart",
    "gallons": "gallon",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "gram": "g",
    "grams": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "ounce": "oz",
    "ounces": "oz",
    "pound": "lb",
    "pounds": "lb",
    "fahrenheit": "f",
    "celsius": "c",
    "centigrade": "c",
    "kelvin": "k",
}

# ---------------------------------------------------------------------------
# Volume units -> milliliters
# ---------------------------------------------------------------------------
_ML_PER_UNIT: dict[str, float] = {
    "ml": 1.0,
    "l": 1000.0,
    "tsp": 4.929,
    "tbsp": 14.787,
    "fl_oz": 29.574,
    "cup": 236.588,
    "pint": 473.176,
    "quart": 946.353,
    "gallon": 3785.411,
}

# ---------------------------------------------------------------------------
# Weight units -> grams
# ---------------------------------------------------------------------------
_G_PER_UNIT: dict[str, float] = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.3495,
    "lb": 453.592,
}

# ---------------------------------------------------------------------------
# Temperature unit identifiers
# ---------------------------------------------------------------------------
_TEMP_UNITS: frozenset[str] = frozenset({"f", "c", "k"})

# ---------------------------------------------------------------------------
# Ingredient densities (grams per milliliter) for volume <-> weight conversion
# ---------------------------------------------------------------------------
_DENSITY_G_PER_ML: dict[str, float] = {
    "water": 1.0,
    "milk": 1.03,
    "flour": 0.593,
    "all-purpose flour": 0.593,
    "bread flour": 0.55,
    "sugar": 0.845,
    "granulated sugar": 0.845,
    "brown sugar": 0.93,
    "powdered sugar": 0.56,
    "butter": 0.911,
    "honey": 1.42,
    "olive oil": 0.92,
    "vegetable oil": 0.92,
    "salt": 1.217,
    "cocoa powder": 0.52,
    "rice": 0.85,
    "oats": 0.41,
    "cornstarch": 0.54,
    "baking powder": 0.90,
    "baking soda": 1.10,
}

# Absolute zero offset for Kelvin conversions
_KELVIN_OFFSET = 273.15

# Fahrenheit conversion constants
_FAHRENHEIT_RATIO = 9.0 / 5.0
_FAHRENHEIT_OFFSET = 32.0


def _normalize_unit(unit: str) -> str:
    """Lowercase, strip, and resolve aliases to a canonical unit name."""
    canonical = unit.strip().lower()
    return _UNIT_ALIASES.get(canonical, canonical)


class ConversionService:
    """Converts between cooking measurement units.

    Handles volume-to-volume, weight-to-weight, temperature, and
    density-based volume-to-weight conversions using static lookup tables.
    Falls back to the Spoonacular API for unknown ingredient densities.
    """

    def __init__(
        self,
        *,
        spoonacular_client: SpoonacularClient | None = None,
    ) -> None:
        self._spoonacular_client = spoonacular_client

    # -- Public API ---------------------------------------------------------

    def convert(
        self,
        amount: float,
        from_unit: str,
        to_unit: str,
        *,
        ingredient: str | None = None,
    ) -> float:
        """Convert *amount* between two units using static data only.

        Raises ``ValueError`` when the conversion cannot be performed
        (unknown unit or cross-category without an ingredient density).
        """
        src = _normalize_unit(from_unit)
        dst = _normalize_unit(to_unit)

        if src == dst:
            return amount

        # Temperature
        if src in _TEMP_UNITS and dst in _TEMP_UNITS:
            return self.convert_temperature(amount, src, dst)

        src_is_volume = src in _ML_PER_UNIT
        dst_is_volume = dst in _ML_PER_UNIT
        src_is_weight = src in _G_PER_UNIT
        dst_is_weight = dst in _G_PER_UNIT

        # Volume -> Volume
        if src_is_volume and dst_is_volume:
            return amount * _ML_PER_UNIT[src] / _ML_PER_UNIT[dst]

        # Weight -> Weight
        if src_is_weight and dst_is_weight:
            return amount * _G_PER_UNIT[src] / _G_PER_UNIT[dst]

        # Cross-category: requires ingredient density
        if (src_is_volume and dst_is_weight) or (src_is_weight and dst_is_volume):
            if ingredient is None:
                msg = (
                    f"Cannot convert between {from_unit} and {to_unit} "
                    "without specifying an ingredient for density lookup"
                )
                raise ValueError(msg)

            density = _DENSITY_G_PER_ML.get(ingredient.strip().lower())
            if density is None:
                msg = (
                    f"No density data for ingredient '{ingredient}'. "
                    "Use convert_with_api_fallback() for API-based conversion."
                )
                raise ValueError(msg)

            if src_is_volume and dst_is_weight:
                ml = amount * _ML_PER_UNIT[src]
                grams = ml * density
                return grams / _G_PER_UNIT[dst]

            # src_is_weight and dst_is_volume
            grams = amount * _G_PER_UNIT[src]
            ml = grams / density
            return ml / _ML_PER_UNIT[dst]

        msg = f"Unknown unit(s): '{from_unit}' and/or '{to_unit}'"
        raise ValueError(msg)

    def convert_temperature(
        self,
        amount: float,
        from_unit: str,
        to_unit: str,
    ) -> float:
        """Convert between Fahrenheit, Celsius, and Kelvin."""
        src = _normalize_unit(from_unit)
        dst = _normalize_unit(to_unit)

        if src == dst:
            return amount

        if src not in _TEMP_UNITS or dst not in _TEMP_UNITS:
            msg = f"Unknown temperature unit(s): '{from_unit}' and/or '{to_unit}'"
            raise ValueError(msg)

        # Convert to Celsius first
        if src == "f":
            celsius = (amount - _FAHRENHEIT_OFFSET) / _FAHRENHEIT_RATIO
        elif src == "k":
            celsius = amount - _KELVIN_OFFSET
        else:
            celsius = amount

        # Convert from Celsius to target
        if dst == "f":
            return celsius * _FAHRENHEIT_RATIO + _FAHRENHEIT_OFFSET
        if dst == "k":
            return celsius + _KELVIN_OFFSET
        return celsius

    async def convert_with_api_fallback(
        self,
        amount: float,
        from_unit: str,
        to_unit: str,
        *,
        ingredient: str,
    ) -> float:
        """Try local conversion first, then fall back to Spoonacular API."""
        try:
            return self.convert(amount, from_unit, to_unit, ingredient=ingredient)
        except ValueError:
            if self._spoonacular_client is None:
                raise

        logger.info(
            "conversion_api_fallback",
            ingredient=ingredient,
            from_unit=from_unit,
            to_unit=to_unit,
        )
        data: dict[str, Any] = await self._spoonacular_client.convert_amounts(
            ingredient,
            amount,
            from_unit,
            to_unit,
        )
        target_amount = data.get("targetAmount")
        if target_amount is None:
            msg = (
                f"Spoonacular could not convert {amount} {from_unit} "
                f"to {to_unit} for '{ingredient}'"
            )
            raise ValueError(msg)
        return float(target_amount)
