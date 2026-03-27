"""Locust load tests for the Recipe MCP Server over streamable HTTP.

The MCP server uses JSON-RPC 2.0 over HTTP. Each user establishes a
session via the ``initialize`` handshake, then sends ``tools/call``
requests to exercise the server under load.

Prerequisites:
    docker compose up -d          # Start server + Redis + Jaeger
    uv run python scripts/seed_db.py   # Seed sample data

Run:
    uv run locust -f tests/performance/locustfile.py \\
        --headless -u 10 -r 2 --run-time 60s \\
        --host http://localhost:8000

Web UI:
    uv run locust -f tests/performance/locustfile.py --host http://localhost:8000
    # Open http://localhost:8089
"""

from __future__ import annotations

import json
import uuid

from locust import HttpUser, between, events, tag, task
from locust.env import Environment

MCP_PATH = "/mcp/"

CLIENT_INFO = {
    "name": "locust-load-tester",
    "version": "1.0.0",
}

PROTOCOL_VERSION = "2025-11-25"

# Seed recipe IDs from scripts/seed_db.py
SEED_RECIPE_IDS = [
    "seed-recipe-001",
    "seed-recipe-002",
    "seed-recipe-003",
    "seed-recipe-004",
    "seed-recipe-005",
]

# Foods with pre-seeded nutrition cache (should be fast / cache hit)
CACHED_FOODS = ["chicken breast", "olive oil", "mozzarella cheese", "dark chocolate"]

# Foods without cache (will trigger API calls / cache miss)
UNCACHED_FOODS = ["quinoa", "salmon", "avocado", "sweet potato"]


def _jsonrpc(method: str, params: dict | None = None) -> dict:
    """Build a JSON-RPC 2.0 request payload."""
    payload: dict = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex[:12],
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return payload


@events.test_start.add_listener
def on_test_start(environment: Environment, **_kwargs: object) -> None:
    """Verify the server is reachable before starting the load test."""
    import httpx

    host = environment.host or "http://localhost:8000"
    try:
        resp = httpx.get(f"{host}/health", timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        msg = f"Server not reachable at {host}/health: {exc}"
        raise SystemExit(msg) from exc


class MCPUser(HttpUser):
    """Base class for MCP load test users.

    Handles the JSON-RPC initialize handshake on session start.
    Subclasses define specific tool call scenarios.
    """

    abstract = True
    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Perform MCP initialize handshake."""
        payload = _jsonrpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        with self.client.post(
            MCP_PATH,
            json=payload,
            name="initialize",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Initialize failed: {resp.status_code}")
            else:
                resp.success()

        # Send initialized notification
        notif = _jsonrpc("notifications/initialized")
        del notif["id"]  # notifications have no id
        self.client.post(MCP_PATH, json=notif, name="initialized_notification")

    def _call_tool(self, tool_name: str, arguments: dict, label: str | None = None) -> None:
        """Send a tools/call JSON-RPC request."""
        payload = _jsonrpc(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )
        name = label or f"tools/call/{tool_name}"
        with self.client.post(
            MCP_PATH,
            json=payload,
            name=name,
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"{tool_name} failed: {resp.status_code}")
                return
            try:
                body = resp.json()
            except ValueError:
                resp.failure(f"{tool_name}: invalid JSON response")
                return
            if "error" in body:
                resp.failure(f"{tool_name} JSON-RPC error: {body['error']}")
            else:
                resp.success()


class RecipeSearchUser(MCPUser):
    """Simulates recipe search and retrieval workload (most common)."""

    weight = 5

    @tag("recipe", "search")
    @task(3)
    def search_recipes(self) -> None:
        queries = ["pasta", "chicken", "salad", "thai", "dessert", "pizza"]
        import random

        query = random.choice(queries)
        self._call_tool("search_recipes", {"query": query})

    @tag("recipe", "get")
    @task(2)
    def get_recipe(self) -> None:
        import random

        recipe_id = random.choice(SEED_RECIPE_IDS)
        self._call_tool("get_recipe", {"recipe_id": recipe_id})

    @tag("recipe", "random")
    @task(1)
    def get_random_recipe(self) -> None:
        self._call_tool("get_random_recipe", {})


class NutritionUser(MCPUser):
    """Tests cache hit vs miss performance for nutrition lookups."""

    weight = 3

    @tag("nutrition", "cached")
    @task(3)
    def lookup_cached_nutrition(self) -> None:
        import random

        food = random.choice(CACHED_FOODS)
        self._call_tool(
            "lookup_nutrition",
            {"food_name": food},
            label="tools/call/lookup_nutrition[cached]",
        )

    @tag("nutrition", "uncached")
    @task(1)
    def lookup_uncached_nutrition(self) -> None:
        import random

        food = random.choice(UNCACHED_FOODS)
        self._call_tool(
            "lookup_nutrition",
            {"food_name": food},
            label="tools/call/lookup_nutrition[uncached]",
        )


class MealPlanUser(MCPUser):
    """Tests heavier meal plan operations (low frequency)."""

    weight = 1

    @tag("mealplan")
    @task(2)
    def generate_meal_plan(self) -> None:
        self._call_tool(
            "generate_meal_plan",
            {
                "user_id": "locust-user",
                "name": "load-test-plan",
                "time_frame": "day",
                "target_calories": 2000,
                "diet": "balanced",
            },
        )

    @tag("mealplan", "shopping")
    @task(1)
    def generate_shopping_list(self) -> None:
        self._call_tool(
            "generate_shopping_list",
            {
                "recipe_ids_json": json.dumps(SEED_RECIPE_IDS[:3]),
            },
        )
