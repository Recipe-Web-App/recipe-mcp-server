"""Foodish API client.

Wraps https://foodish-api.com/api for random food images.
No authentication required. No caching per requirements.
"""

from __future__ import annotations

from typing import Any

import structlog

from recipe_mcp_server.clients.base import BaseAPIClient

logger = structlog.get_logger(__name__)


class FoodishClient(BaseAPIClient):
    """Client for the Foodish random food image API."""

    api_name = "Foodish"
    base_url = "https://foodish-api.com/api"

    # -- Abstract method required by BaseAPIClient ----------------------------

    def _build_cache_key(self, endpoint: str, params: dict[str, Any] | None) -> str:
        """Foodish responses are never cached, but the method is required."""
        return f"foodish:{endpoint}"

    # -- Public API methods ---------------------------------------------------

    async def random_image(self) -> str:
        """Get a random food image URL."""
        data = await self._get("/")
        if isinstance(data, dict):
            return data.get("image", "")
        return ""

    async def random_image_by_category(self, category: str) -> str:
        """Get a random food image URL from a specific category."""
        data = await self._get(f"/images/{category}/")
        if isinstance(data, dict):
            return data.get("image", "")
        return ""
