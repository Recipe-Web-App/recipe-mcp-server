"""Resource subscription notification helpers.

These functions emit MCP notifications to inform subscribed clients
about resource changes (updated content or changed resource lists).
"""

from __future__ import annotations

import structlog
from fastmcp import Context
from mcp.types import (
    ResourceListChangedNotification,
    ResourceUpdatedNotification,
    ResourceUpdatedNotificationParams,
)

logger = structlog.get_logger(__name__)


async def notify_resource_updated(ctx: Context, uri: str) -> None:
    """Emit ``notifications/resources/updated`` for a specific resource URI.

    Subscribed clients will re-read the resource to get fresh data.
    """
    await ctx.send_notification(
        ResourceUpdatedNotification(
            params=ResourceUpdatedNotificationParams(uri=uri),
        )
    )
    logger.debug("resource_updated_notification", uri=uri)


async def notify_resource_list_changed(ctx: Context) -> None:
    """Emit ``notifications/resources/list_changed``.

    Tells clients that the set of available resource URIs has changed
    (e.g. a new recipe was created or one was deleted).
    """
    await ctx.send_notification(ResourceListChangedNotification())
    logger.debug("resource_list_changed_notification")
