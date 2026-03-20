# Implementation Plan

> Reference: [REQUIREMENTS.md](./REQUIREMENTS.md) for full specifications.
> This document maps implementation phases to beads epics and tasks.

## Phase Overview

| Phase | Epic                  | Description                                                                                                              | Dependencies   |
| ----- | --------------------- | ------------------------------------------------------------------------------------------------------------------------ | -------------- |
| 1     | Foundation            | Project skeleton: config, models, database, migrations                                                                   | None           |
| 2     | API Clients + Cache   | Downstream API integrations with Redis caching                                                                           | Phase 1        |
| 3     | Services              | Business logic orchestration layer                                                                                       | Phases 1, 2    |
| 4     | MCP Core Primitives   | Tools, resources, prompts, sampling, elicitation                                                                         | Phases 1, 2, 3 |
| 5     | MCP Protocol Features | Subscriptions, notifications, progress, logging, pagination, cancellation, session state, visibility, composition, tasks | Phase 4        |
| 6     | Cross-Cutting         | Auth (OAuth 2.1), observability (OTel + Jaeger), audit trail, middleware                                                 | Phases 4, 5    |
| 7     | Deployment + Polish   | Docker, CI, documentation, load tests, coverage                                                                          | Phase 6        |

## Phase 1: Foundation

**Reference:** REQUIREMENTS.md sections 1.3, 1.4, 5.1, 5.2, 9.1, 9.2

| Task                | Description                                                        | Key Files                                |
| ------------------- | ------------------------------------------------------------------ | ---------------------------------------- |
| Project scaffolding | `.mise.toml`, `pyproject.toml`, `.env.example`, `.gitignore`       | Root files                               |
| Configuration       | `pydantic-settings` with `RECIPE_MCP_` prefix, all env vars        | `src/recipe_mcp_server/config.py`        |
| Pydantic models     | Recipe, Ingredient, NutrientInfo, MealPlan, UserPreferences, enums | `src/recipe_mcp_server/models/*.py`      |
| SQLite engine       | Async SQLAlchemy 2.0 + aiosqlite, WAL mode, session factory        | `src/recipe_mcp_server/db/engine.py`     |
| ORM tables          | SQLAlchemy mapped classes for all 8 tables                         | `src/recipe_mcp_server/db/tables.py`     |
| Repository layer    | RecipeRepo, UserRepo, FavoriteRepo, MealPlanRepo, AuditRepo        | `src/recipe_mcp_server/db/repository.py` |
| Alembic setup       | Initial migration with complete schema                             | `alembic.ini`, `migrations/`             |
| Test fixtures       | conftest.py with in-memory SQLite, test settings, factories        | `tests/conftest.py`, `tests/factories/`  |
| Unit tests          | Models, config validation, repository CRUD                         | `tests/unit/`                            |

## Phase 2: API Clients + Cache

**Reference:** REQUIREMENTS.md sections 4.1-4.6, 5.3

| Task                   | Description                                                                                 | Key Files                                        |
| ---------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| Redis client           | Async Redis connection pool, `@cached()` decorator, key namespaces                          | `src/recipe_mcp_server/cache/`                   |
| Base API client        | httpx.AsyncClient with retry (tenacity), circuit breaker, cache integration, error wrapping | `src/recipe_mcp_server/clients/base.py`          |
| TheMealDB client       | Search, lookup, filter, list endpoints; map to domain models                                | `src/recipe_mcp_server/clients/themealdb.py`     |
| USDA client            | Food search, food detail, bulk lookup; nutrient mapping                                     | `src/recipe_mcp_server/clients/usda.py`          |
| Spoonacular client     | Recipe search, meal plan, wine pairing, substitutions, nutrition, conversion                | `src/recipe_mcp_server/clients/spoonacular.py`   |
| Open Food Facts client | Product by barcode, product search; allergen extraction                                     | `src/recipe_mcp_server/clients/openfoodfacts.py` |
| Foodish client         | Random food image by category                                                               | `src/recipe_mcp_server/clients/foodish.py`       |
| DummyJSON client       | Recipe list, search, tags, meal type filtering                                              | `src/recipe_mcp_server/clients/dummyjson.py`     |
| API response fixtures  | Recorded JSON responses for all endpoints                                                   | `tests/fixtures/api_responses/`                  |
| Client unit tests      | respx-mocked tests for each client                                                          | `tests/unit/clients/`                            |

## Phase 3: Services

**Reference:** REQUIREMENTS.md sections 3.1, 7.4, 8.3

| Task               | Description                                                              | Key Files                                              |
| ------------------ | ------------------------------------------------------------------------ | ------------------------------------------------------ |
| Recipe service     | CRUD, multi-API search with fallback chain, dedup, scaling, substitution | `src/recipe_mcp_server/services/recipe_service.py`     |
| Nutrition service  | USDA lookup, recipe nutrition analysis, caching to nutrition_cache       | `src/recipe_mcp_server/services/nutrition_service.py`  |
| Conversion service | Volume/weight/temperature conversion tables, density-based conversions   | `src/recipe_mcp_server/services/conversion_service.py` |
| Meal plan service  | Spoonacular meal plan integration, local recipe incorporation            | `src/recipe_mcp_server/services/meal_plan_service.py`  |
| Shopping service   | Ingredient aggregation, deduplication, unit normalization                | `src/recipe_mcp_server/services/shopping_service.py`   |
| Service unit tests | Mock clients, test business logic, test fallback chains                  | `tests/unit/test_*_service.py`                         |

## Phase 4: MCP Core Primitives

**Reference:** REQUIREMENTS.md sections 3.1-3.5, 3.6, 3.7, 3.16

| Task                   | Description                                                               | Key Files                                              |
| ---------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------ |
| FastMCP server factory | App creation, lifespan events (DB/Redis/client init+shutdown)             | `src/recipe_mcp_server/server.py`                      |
| Recipe tools           | 5 CRUD tools + search + random + scale + substitute + favorites           | `src/recipe_mcp_server/tools/recipe_tools.py`          |
| Nutrition tools        | lookup_nutrition, analyze_recipe_nutrition with embedded resources        | `src/recipe_mcp_server/tools/nutrition_tools.py`       |
| Meal plan tools        | generate_meal_plan, generate_shopping_list                                | `src/recipe_mcp_server/tools/meal_plan_tools.py`       |
| Utility tools          | convert_units, get_wine_pairing                                           | `src/recipe_mcp_server/tools/utility_tools.py`         |
| Tool annotations       | readOnlyHint, destructiveHint, idempotentHint, openWorldHint on all tools | All `tools/*.py`                                       |
| Static resources       | catalog, categories, cuisines, ingredients                                | `src/recipe_mcp_server/resources/static_resources.py`  |
| Dynamic resources      | recipe://{id}, nutrition://{food}, mealplan://{id}, favorites/{user}      | `src/recipe_mcp_server/resources/dynamic_resources.py` |
| UI resources           | HTML recipe card, FDA nutrition label                                     | `src/recipe_mcp_server/resources/ui_resources.py`      |
| Blob resources         | Recipe photo PNG, nutrition chart PNG (Pillow)                            | `src/recipe_mcp_server/resources/blob_resources.py`    |
| Embedded resources     | In get_recipe and analyze_recipe_nutrition tool results                   | `tools/recipe_tools.py`, `tools/nutrition_tools.py`    |
| Prompts                | All 8 prompts with typed parameters                                       | `src/recipe_mcp_server/prompts/*.py`                   |
| Sampling handlers      | Recipe variations, ingredient pairing via ctx.sample()                    | `src/recipe_mcp_server/sampling/handlers.py`           |
| Elicitation handlers   | Dietary prefs, serving confirm, ingredient clarify via ctx.elicit()       | `src/recipe_mcp_server/elicitation/handlers.py`        |
| Tags & icons           | Tag and icon metadata on all tools, resources, prompts                    | All primitive files                                    |
| Entry point            | `__main__.py` with stdio transport                                        | `src/recipe_mcp_server/__main__.py`                    |
| Protocol tests         | Tool call/response, resource read, prompt get via test client             | `tests/e2e/`, `tests/protocol/`                        |

## Phase 5: MCP Protocol Features

**Reference:** REQUIREMENTS.md sections 3.8-3.15, 3.17-3.18

| Task                   | Description                                                             | Key Files                                                                       |
| ---------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Resource subscriptions | Subscribe/unsubscribe for catalog + favorites; emit updates on mutation | `src/recipe_mcp_server/resources/subscriptions.py`                              |
| Resource list changed  | Notification on recipe create/delete (new/removed URIs)                 | `resources/subscriptions.py`                                                    |
| Tool list changed      | Seasonal `get_holiday_recipes` registration; emit notification          | `tools/seasonal.py`                                                             |
| Progress reporting     | ctx.report_progress() in search, meal plan, nutrition analysis          | `tools/recipe_tools.py`, `tools/meal_plan_tools.py`, `tools/nutrition_tools.py` |
| Server logging         | ctx.debug/info/warning/error in all tool handlers                       | All `tools/*.py`                                                                |
| Argument completion    | Cuisine, restriction, recipe_id auto-complete providers                 | `prompts/*.py`, `resources/dynamic_resources.py`                                |
| Pagination             | Cursor-based on catalog resource + search tool + list endpoints         | `resources/static_resources.py`, `tools/recipe_tools.py`                        |
| Cancellation           | Cancel support in generate_meal_plan and search_recipes                 | `tools/meal_plan_tools.py`, `tools/recipe_tools.py`                             |
| Session state          | set/get/delete state for preferences, last search, unit system          | Throughout `tools/*.py`                                                         |
| Component visibility   | Disable elicitation after dietary prefs collected                       | `tools/meal_plan_tools.py`                                                      |
| Server composition     | NutritionMCPServer as separate server, mounted into main                | `src/recipe_mcp_server/composition/nutrition_server.py`, `server.py`            |
| Async tasks            | task=True on generate_meal_plan; status polling                         | `tools/meal_plan_tools.py`                                                      |
| Protocol feature tests | Tests for subscriptions, progress, pagination, cancellation, tasks      | `tests/e2e/`, `tests/protocol/`                                                 |

## Phase 6: Cross-Cutting

**Reference:** REQUIREMENTS.md sections 7.2, 7.3, 8.1-8.2

| Task                | Description                                                            | Key Files                                           |
| ------------------- | ---------------------------------------------------------------------- | --------------------------------------------------- |
| OAuth 2.1 provider  | Provider config for HTTP transport, PKCE support                       | `src/recipe_mcp_server/auth/oauth_provider.py`      |
| Auth middleware     | JWT validation (issuer, audience, expiry, scopes)                      | `src/recipe_mcp_server/auth/middleware.py`          |
| OTel tracing        | OpenTelemetry SDK + OTLP exporter + Jaeger, custom @traced decorator   | `src/recipe_mcp_server/observability/tracing.py`    |
| Structured logging  | structlog JSON config, request ID correlation, dev console mode        | `src/recipe_mcp_server/observability/logging.py`    |
| Audit trail         | @audited decorator, before/after snapshots, MCP request ID correlation | `src/recipe_mcp_server/observability/audit.py`      |
| Error handler       | Unified error handling, domain exception → MCP error mapping           | `src/recipe_mcp_server/middleware/error_handler.py` |
| Rate limiter        | Redis-backed sliding window per-client rate limiting                   | `src/recipe_mcp_server/middleware/rate_limiter.py`  |
| Input validators    | Sanitization layer for tool parameters                                 | `src/recipe_mcp_server/middleware/validators.py`    |
| Cross-cutting tests | Auth flow E2E, OTel span verification, audit log assertions            | `tests/e2e/`, `tests/integration/`                  |

## Phase 7: Deployment + Polish

**Reference:** REQUIREMENTS.md sections 10, 11

| Task                  | Description                                                        | Key Files                         |
| --------------------- | ------------------------------------------------------------------ | --------------------------------- |
| Dockerfile            | Multi-stage build with uv, non-root user, healthcheck              | `Dockerfile`                      |
| Docker Compose        | MCP server + Redis + Jaeger, volumes, health checks                | `docker-compose.yml`              |
| CLAUDE.md             | Build/test/run commands for Claude Code                            | `CLAUDE.md`                       |
| README                | Quickstart guide, architecture overview, MCP capability index      | `README.md`                       |
| Database seeding      | Sample recipes, users, favorites, meal plans                       | `scripts/seed_db.py`              |
| Load tests            | Locust scenarios for concurrent tool calls, cache performance      | `tests/performance/locustfile.py` |
| Coverage verification | Ensure 85%+ with branch coverage, configure exclusions             | `pyproject.toml` [tool.coverage]  |
| CI pipeline           | GitHub Actions: lint → unit → integration → e2e → security → build | `.github/workflows/ci.yml`        |
