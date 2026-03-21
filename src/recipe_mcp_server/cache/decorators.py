"""Cache decorator for transparently caching async function results in Redis."""

from __future__ import annotations

import functools
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

import redis.asyncio as redis_async
import structlog
from pydantic import BaseModel, TypeAdapter

logger = structlog.get_logger(__name__)

R = TypeVar("R")

# Types accepted as response_model for deserialization
ResponseModelType = type[BaseModel] | TypeAdapter[Any]


def cached(
    ttl: int,
    key_func: Callable[..., str],
    response_model: ResponseModelType | None = None,
) -> Callable[
    [Callable[..., Awaitable[R]]],
    Callable[..., Awaitable[R]],
]:
    """Decorator that caches async function results in Redis.

    The decorated function's first positional argument must be a
    ``redis.asyncio.Redis`` client (or ``None`` to skip caching).

    Args:
        ttl: Time-to-live in seconds for the cached value.
        key_func: Receives the same arguments as the decorated function
            *minus* the Redis client and returns the cache key string.
        response_model: Pydantic ``BaseModel`` subclass or ``TypeAdapter``
            used for deserialization on cache hit. If ``None``, the raw
            cached string is returned.

    Cache errors are always caught and logged; the original function
    executes on any Redis failure.
    """

    def decorator(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> R:
            redis_client: redis_async.Redis | None = args[0] if args else kwargs.get("redis")
            if redis_client is None:
                return await func(*args, **kwargs)

            remaining_args = args[1:]
            cache_key = key_func(*remaining_args, **kwargs)

            # Try cache read
            try:
                raw: str | None = await redis_client.get(cache_key)
                if raw is not None:
                    logger.debug("cache_hit", key=cache_key)
                    return cast(R, _deserialize(raw, response_model))
            except redis_async.RedisError:
                logger.warning("cache_read_error", key=cache_key, exc_info=True)

            # Cache miss or read error — call the original function
            result: R = await func(*args, **kwargs)

            # Try cache write
            try:
                serialized = _serialize(result, response_model)
                await redis_client.set(cache_key, serialized, ex=ttl)
                logger.debug("cache_set", key=cache_key, ttl=ttl)
            except redis_async.RedisError:
                logger.warning("cache_write_error", key=cache_key, exc_info=True)

            return result

        return wrapper

    return decorator


def _serialize(value: Any, response_model: ResponseModelType | None = None) -> str:
    """Serialize a value to a JSON string for cache storage."""
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    if isinstance(response_model, TypeAdapter):
        return response_model.dump_json(value).decode()
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def _deserialize(raw: str, response_model: ResponseModelType | None) -> Any:
    """Deserialize a cached JSON string back to the expected type."""
    if response_model is None:
        return raw
    if isinstance(response_model, TypeAdapter):
        return response_model.validate_json(raw)
    return response_model.model_validate_json(raw)
