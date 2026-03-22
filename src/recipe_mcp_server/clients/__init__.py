"""Downstream API clients with retry, circuit breaker, and cache integration."""

from recipe_mcp_server.clients.base import BaseAPIClient
from recipe_mcp_server.clients.dummyjson import DummyJSONClient
from recipe_mcp_server.clients.foodish import FoodishClient
from recipe_mcp_server.clients.openfoodfacts import OpenFoodFactsClient
from recipe_mcp_server.clients.spoonacular import SpoonacularClient
from recipe_mcp_server.clients.themealdb import TheMealDBClient
from recipe_mcp_server.clients.usda import USDAClient

__all__ = [
    "BaseAPIClient",
    "DummyJSONClient",
    "FoodishClient",
    "OpenFoodFactsClient",
    "SpoonacularClient",
    "TheMealDBClient",
    "USDAClient",
]
