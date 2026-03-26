"""Integration tests for Redis cache hit/miss/expiry behavior."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from recipe_mcp_server.cache.decorators import cached


@pytest.mark.integration
class TestCacheBehavior:
    """Tests for cache hit, miss, and graceful degradation.

    The ``@cached`` decorator expects the Redis client as the first positional
    argument of the decorated function.
    """

    async def test_cache_miss_executes_function(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """On cache miss, the decorated function should execute."""
        call_count = 0

        @cached(ttl=60, key_func=lambda k: f"test:{k}")
        async def fetch_data(redis_client: object, key: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"value-{key}"

        result = await fetch_data(fake_redis, "abc")
        assert result == "value-abc"
        assert call_count == 1

    async def test_cache_hit_skips_function(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        """On cache hit, the decorated function should not re-execute."""
        call_count = 0

        @cached(ttl=60, key_func=lambda k: f"test:{k}")
        async def fetch_data(redis_client: object, key: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"value-{key}"

        await fetch_data(fake_redis, "abc")
        assert call_count == 1

        # Second call should be a cache hit
        result = await fetch_data(fake_redis, "abc")
        assert result == "value-abc"
        assert call_count == 1

    async def test_no_redis_executes_function(self) -> None:
        """When Redis client is None, the function executes without caching."""
        call_count = 0

        @cached(ttl=60, key_func=lambda k: f"test:{k}")
        async def fetch_data(redis_client: object, key: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"value-{key}"

        result = await fetch_data(None, "xyz")
        assert result == "value-xyz"
        assert call_count == 1

        # Without Redis, every call executes the function
        result = await fetch_data(None, "xyz")
        assert result == "value-xyz"
        assert call_count == 2
