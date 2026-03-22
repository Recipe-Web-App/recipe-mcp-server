"""Cache key namespace definitions with TTL constants.

All key patterns and TTLs match REQUIREMENTS.md section 5.3.
"""

from __future__ import annotations

import hashlib

# TTL constants in seconds
TTL_SEARCH: int = 3600  # 1 hour
TTL_RECIPE: int = 86400  # 24 hours
TTL_NUTRITION: int = 604800  # 7 days
TTL_CATEGORIES: int = 86400  # 24 hours
TTL_CUISINES: int = 86400  # 24 hours
TTL_INGREDIENTS: int = 604800  # 7 days
TTL_FILTER: int = 21600  # 6 hours
TTL_WINE_PAIRING: int = 86400  # 24 hours
TTL_SUBSTITUTES: int = 604800  # 7 days
TTL_PRODUCT: int = 604800  # 7 days
TTL_CONVERSION: int = 2592000  # 30 days
TTL_SESSION: int = 3600  # 1 hour


def search_key(query: str, cuisine: str = "", diet: str = "") -> str:
    """Build cache key for recipe search results."""
    raw = f"{query}:{cuisine}:{diet}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"recipe_search:{digest}"


def recipe_key(source: str, source_id: str) -> str:
    """Build cache key for a single recipe from an API."""
    return f"recipe:{source}:{source_id}"


def nutrition_key(food_name: str) -> str:
    """Build cache key for USDA nutrition data."""
    return f"nutrition:{food_name.strip().lower()}"


def categories_key() -> str:
    """Build cache key for aggregated category list."""
    return "categories:all"


def cuisines_key() -> str:
    """Build cache key for aggregated cuisine/area list."""
    return "cuisines:all"


def ingredients_key() -> str:
    """Build cache key for master ingredient list."""
    return "ingredients:all"


def wine_pairing_key(food: str) -> str:
    """Build cache key for wine pairing results."""
    return f"wine_pairing:{food.strip().lower()}"


def substitutes_key(ingredient: str) -> str:
    """Build cache key for ingredient substitution results."""
    return f"substitutes:{ingredient.strip().lower()}"


def product_key(barcode: str) -> str:
    """Build cache key for Open Food Facts product."""
    return f"product:{barcode}"


def conversion_key(ingredient: str, source_unit: str, target_unit: str) -> str:
    """Build cache key for unit conversion results."""
    normalized = f"{ingredient.strip().lower()}:{source_unit.lower()}:{target_unit.lower()}"
    return f"conversion:{normalized}"


def ratelimit_key(api: str, window: str) -> str:
    """Build cache key for sliding window rate limit counter."""
    return f"ratelimit:{api}:{window}"


def session_key(session_id: str) -> str:
    """Build cache key for MCP session state."""
    return f"session:{session_id}"
