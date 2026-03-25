"""FastMCP server factory with lifespan-managed infrastructure."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastmcp import FastMCP

from recipe_mcp_server import __version__
from recipe_mcp_server.cache.client import close_redis, init_redis
from recipe_mcp_server.clients.dummyjson import DummyJSONClient
from recipe_mcp_server.clients.foodish import FoodishClient
from recipe_mcp_server.clients.openfoodfacts import OpenFoodFactsClient
from recipe_mcp_server.clients.spoonacular import SpoonacularClient
from recipe_mcp_server.clients.themealdb import TheMealDBClient
from recipe_mcp_server.clients.usda import USDAClient
from recipe_mcp_server.config import get_settings
from recipe_mcp_server.db.engine import get_session_factory, init_engine
from recipe_mcp_server.db.repository import (
    AuditRepo,
    FavoriteRepo,
    MealPlanRepo,
    RecipeRepo,
    UserRepo,
)
from recipe_mcp_server.db.tables import Base
from recipe_mcp_server.exceptions import CacheError
from recipe_mcp_server.observability import configure_logging, init_tracing, shutdown_tracing
from recipe_mcp_server.services.conversion_service import ConversionService
from recipe_mcp_server.services.meal_plan_service import MealPlanService
from recipe_mcp_server.services.nutrition_service import NutritionService
from recipe_mcp_server.services.recipe_service import RecipeService
from recipe_mcp_server.services.shopping_service import ShoppingService

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Initialize and tear down all server infrastructure.

    Startup order: settings -> DB -> Redis -> clients -> repos -> services.
    Shutdown order: clients -> Redis -> DB engine.
    """
    settings = get_settings()

    # -- Observability (configure before anything logs) --------------------
    configure_logging(settings.log_level, settings.log_format)
    init_tracing(settings.server_name, __version__, settings.otlp_endpoint)

    # -- Database ----------------------------------------------------------
    engine = await init_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = get_session_factory(engine)
    logger.info("database_ready", db_path=str(settings.db_path))

    # -- Redis (non-fatal) -------------------------------------------------
    redis_client = None
    try:
        redis_client = await init_redis(settings)
    except CacheError:
        logger.warning("redis_unavailable", msg="Server will run without caching")

    # -- API clients -------------------------------------------------------
    mealdb_client = TheMealDBClient(redis_client=redis_client)
    spoonacular_client = SpoonacularClient(
        api_key=settings.spoonacular_api_key, redis_client=redis_client
    )
    usda_client = USDAClient(api_key=settings.usda_api_key, redis_client=redis_client)
    dummyjson_client = DummyJSONClient(redis_client=redis_client)
    foodish_client = FoodishClient(redis_client=redis_client)
    openfoodfacts_client = OpenFoodFactsClient(redis_client=redis_client)

    clients = [
        mealdb_client,
        spoonacular_client,
        usda_client,
        dummyjson_client,
        foodish_client,
        openfoodfacts_client,
    ]

    # -- Repositories ------------------------------------------------------
    recipe_repo = RecipeRepo(session_factory)
    user_repo = UserRepo(session_factory)
    favorite_repo = FavoriteRepo(session_factory)
    meal_plan_repo = MealPlanRepo(session_factory)
    audit_repo = AuditRepo(session_factory)

    # -- Services ----------------------------------------------------------
    recipe_service = RecipeService(
        recipe_repo=recipe_repo,
        favorite_repo=favorite_repo,
        mealdb_client=mealdb_client,
        spoonacular_client=spoonacular_client,
        dummyjson_client=dummyjson_client,
        foodish_client=foodish_client,
    )
    nutrition_service = NutritionService(
        usda_client=usda_client,
        spoonacular_client=spoonacular_client,
        recipe_repo=recipe_repo,
    )
    meal_plan_service = MealPlanService(
        spoonacular_client=spoonacular_client,
        meal_plan_repo=meal_plan_repo,
    )
    shopping_service = ShoppingService(
        recipe_repo=recipe_repo,
        meal_plan_repo=meal_plan_repo,
    )
    conversion_service = ConversionService(spoonacular_client=spoonacular_client)

    logger.info("server_started", name=settings.server_name, version=__version__)

    try:
        yield {
            # Infrastructure
            "settings": settings,
            "engine": engine,
            "session_factory": session_factory,
            "redis_client": redis_client,
            # Clients
            "mealdb_client": mealdb_client,
            "spoonacular_client": spoonacular_client,
            "usda_client": usda_client,
            "dummyjson_client": dummyjson_client,
            "foodish_client": foodish_client,
            "openfoodfacts_client": openfoodfacts_client,
            # Repositories
            "recipe_repo": recipe_repo,
            "user_repo": user_repo,
            "favorite_repo": favorite_repo,
            "meal_plan_repo": meal_plan_repo,
            "audit_repo": audit_repo,
            # Services
            "recipe_service": recipe_service,
            "nutrition_service": nutrition_service,
            "meal_plan_service": meal_plan_service,
            "shopping_service": shopping_service,
            "conversion_service": conversion_service,
        }
    finally:
        # -- Shutdown (reverse order) --------------------------------------
        for client in clients:
            await client.aclose()
        if redis_client is not None:
            await close_redis(redis_client)
        # Properly stop the aiosqlite background thread before disposing.
        # engine.dispose() closes the StaticPool connection synchronously,
        # which doesn't await aiosqlite's thread stop future — the thread
        # then races against event-loop teardown, causing RuntimeError
        # warnings.  Closing the driver connection via its async close()
        # awaits the thread stop before we hand control to dispose().
        await engine.dispose()
        await shutdown_tracing()
        logger.info("server_stopped")


def create_server() -> FastMCP:
    """Create and return a configured FastMCP server instance."""
    settings = get_settings()

    from recipe_mcp_server.auth import create_auth_provider

    auth_provider = create_auth_provider(settings)

    server = FastMCP(
        name=settings.server_name,
        version=__version__,
        instructions=(
            "Production-ready MCP server for recipe management, "
            "nutrition analysis, and meal planning."
        ),
        lifespan=app_lifespan,
        list_page_size=50,
        auth=auth_provider,
    )

    # Add global auth middleware when OAuth is enabled
    if auth_provider is not None:
        from fastmcp.server.auth import require_scopes
        from fastmcp.server.middleware import AuthMiddleware

        server.add_middleware(AuthMiddleware(auth=require_scopes("recipe:read")))

    from recipe_mcp_server.prompts import (
        register_cooking_prompts,
        register_dietary_prompts,
        register_meal_plan_prompts,
        register_recipe_prompts,
    )
    from recipe_mcp_server.prompts.completion import register_completion_handler
    from recipe_mcp_server.resources import (
        register_blob_resources,
        register_dynamic_resources,
        register_static_resources,
        register_ui_resources,
    )
    from recipe_mcp_server.tools import (
        register_meal_plan_tools,
        register_nutrition_tools,
        register_recipe_tools,
        register_seasonal_tools,
        register_utility_tools,
    )

    register_recipe_tools(server)
    register_nutrition_tools(server)
    register_meal_plan_tools(server)
    register_utility_tools(server)
    register_seasonal_tools(server)

    register_static_resources(server)
    register_dynamic_resources(server)
    register_ui_resources(server)
    register_blob_resources(server)

    register_recipe_prompts(server)
    register_meal_plan_prompts(server)
    register_dietary_prompts(server)
    register_cooking_prompts(server)
    register_completion_handler(server)

    # Mount nutrition sub-server for composition demonstration
    from recipe_mcp_server.composition import nutrition_mcp

    server.mount(nutrition_mcp, namespace="nutrition")

    return server


mcp = create_server()
