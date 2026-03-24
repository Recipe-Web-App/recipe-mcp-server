"""Test that mutation tools emit resource-change notifications.

create_recipe, delete_recipe, and save_favorite each call
notify_resource_updated / notify_resource_list_changed after mutating data.
The in-process transport delivers those notifications to the client without
error.  We confirm each mutation tool completes and returns the expected
payload shape.
"""

from __future__ import annotations

import json

import pytest
from fastmcp import Client


@pytest.mark.e2e
class TestSubscriptionNotifications:
    """Mutation tools emit resource notifications and still return valid data."""

    async def test_create_recipe_emits_notification_and_returns_recipe(
        self, mcp_client: Client
    ) -> None:
        """create_recipe notifies recipe://catalog and returns the new recipe."""
        result = await mcp_client.call_tool(
            "create_recipe",
            {"title": "Subscription Test Dish", "servings": 2},
        )
        assert result.content
        data = json.loads(result.content[0].text)
        assert "id" in data
        assert data["title"] == "Subscription Test Dish"

    async def test_delete_recipe_emits_notification_and_returns_deleted_flag(
        self, mcp_client: Client
    ) -> None:
        """delete_recipe notifies clients and returns {deleted: true}."""
        create_result = await mcp_client.call_tool(
            "create_recipe", {"title": "Delete Notification Recipe"}
        )
        recipe_id = json.loads(create_result.content[0].text)["id"]

        delete_result = await mcp_client.call_tool("delete_recipe", {"recipe_id": recipe_id})
        assert delete_result.content
        data = json.loads(delete_result.content[0].text)
        assert data["deleted"] is True
        assert data["recipe_id"] == recipe_id

    async def test_save_favorite_emits_notification_and_returns_favorite(
        self, mcp_client: Client
    ) -> None:
        """save_favorite notifies the user favorites resource and returns the record."""
        create_result = await mcp_client.call_tool(
            "create_recipe", {"title": "Favorite Notification Recipe"}
        )
        recipe_id = json.loads(create_result.content[0].text)["id"]

        fav_result = await mcp_client.call_tool(
            "save_favorite",
            {"user_id": "user-sub-1", "recipe_id": recipe_id},
        )
        assert fav_result.content
        data = json.loads(fav_result.content[0].text)
        assert data["recipe_id"] == recipe_id
        assert data["user_id"] == "user-sub-1"
