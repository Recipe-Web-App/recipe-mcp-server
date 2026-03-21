"""Async Redis connection pool management."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import cast

import redis.asyncio as redis_async
import structlog

from recipe_mcp_server.config import Settings
from recipe_mcp_server.exceptions import CacheError

logger = structlog.get_logger(__name__)

MAX_CONNECTIONS = 20


async def init_redis(settings: Settings) -> redis_async.Redis:
    """Create and verify an async Redis connection pool.

    Args:
        settings: Application settings with redis_url and redis_password.

    Returns:
        A connected Redis client backed by a connection pool.

    Raises:
        CacheError: If the initial connection or ping fails.
    """
    kwargs: dict[str, object] = {
        "decode_responses": True,
        "max_connections": MAX_CONNECTIONS,
    }
    if settings.redis_password:
        kwargs["password"] = settings.redis_password

    client: redis_async.Redis = redis_async.from_url(settings.redis_url, **kwargs)

    try:
        await cast("Awaitable[bool]", client.ping())
        logger.info("redis_connected", url=settings.redis_url)
    except redis_async.RedisError as exc:
        await client.aclose()
        raise CacheError(f"Failed to connect to Redis: {exc}") from exc

    return client


async def close_redis(client: redis_async.Redis) -> None:
    """Gracefully close the Redis connection pool."""
    try:
        await client.aclose()
        logger.info("redis_disconnected")
    except redis_async.RedisError:
        logger.warning("redis_close_error", exc_info=True)
