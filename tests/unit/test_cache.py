"""Unit tests for the cache layer: keys, client lifecycle, and @cached decorator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from pydantic import BaseModel, TypeAdapter
from redis.exceptions import RedisError

from recipe_mcp_server.cache.client import close_redis
from recipe_mcp_server.cache.decorators import cached
from recipe_mcp_server.cache.keys import (
    TTL_CATEGORIES,
    TTL_CUISINES,
    TTL_INGREDIENTS,
    TTL_NUTRITION,
    TTL_PRODUCT,
    TTL_RECIPE,
    TTL_SEARCH,
    TTL_SESSION,
    TTL_SUBSTITUTES,
    TTL_WINE_PAIRING,
    categories_key,
    cuisines_key,
    ingredients_key,
    nutrition_key,
    product_key,
    ratelimit_key,
    recipe_key,
    search_key,
    session_key,
    substitutes_key,
    wine_pairing_key,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Key builder tests
# ---------------------------------------------------------------------------


class TestKeyBuilders:
    def test_search_key_deterministic(self) -> None:
        k1 = search_key("pasta", "italian", "vegan")
        k2 = search_key("pasta", "italian", "vegan")
        assert k1 == k2

    def test_search_key_varies_with_input(self) -> None:
        k1 = search_key("pasta")
        k2 = search_key("pizza")
        assert k1 != k2

    def test_search_key_format(self) -> None:
        k = search_key("test")
        assert k.startswith("recipe_search:")
        # SHA-256 hex digest is 64 chars
        assert len(k.split(":")[1]) == 64

    def test_recipe_key_format(self) -> None:
        assert recipe_key("themealdb", "52772") == "recipe:themealdb:52772"

    def test_nutrition_key_normalizes(self) -> None:
        assert nutrition_key("  Chicken  ") == "nutrition:chicken"

    def test_wine_pairing_key_normalizes(self) -> None:
        assert wine_pairing_key("  Salmon ") == "wine_pairing:salmon"

    def test_substitutes_key_normalizes(self) -> None:
        assert substitutes_key(" Butter ") == "substitutes:butter"

    def test_categories_key(self) -> None:
        assert categories_key() == "categories:all"

    def test_cuisines_key(self) -> None:
        assert cuisines_key() == "cuisines:all"

    def test_ingredients_key(self) -> None:
        assert ingredients_key() == "ingredients:all"

    def test_product_key(self) -> None:
        assert product_key("5060292302201") == "product:5060292302201"

    def test_ratelimit_key(self) -> None:
        assert ratelimit_key("spoonacular", "60s") == "ratelimit:spoonacular:60s"

    def test_session_key(self) -> None:
        assert session_key("abc-123") == "session:abc-123"


# ---------------------------------------------------------------------------
# TTL constant tests
# ---------------------------------------------------------------------------


class TestTTLConstants:
    def test_search_ttl(self) -> None:
        assert TTL_SEARCH == 3600

    def test_recipe_ttl(self) -> None:
        assert TTL_RECIPE == 86400

    def test_nutrition_ttl(self) -> None:
        assert TTL_NUTRITION == 604800

    def test_categories_ttl(self) -> None:
        assert TTL_CATEGORIES == 86400

    def test_cuisines_ttl(self) -> None:
        assert TTL_CUISINES == 86400

    def test_ingredients_ttl(self) -> None:
        assert TTL_INGREDIENTS == 604800

    def test_wine_pairing_ttl(self) -> None:
        assert TTL_WINE_PAIRING == 86400

    def test_substitutes_ttl(self) -> None:
        assert TTL_SUBSTITUTES == 604800

    def test_product_ttl(self) -> None:
        assert TTL_PRODUCT == 604800

    def test_session_ttl(self) -> None:
        assert TTL_SESSION == 3600


# ---------------------------------------------------------------------------
# @cached decorator tests
# ---------------------------------------------------------------------------


class _SampleModel(BaseModel):
    name: str
    value: int


def _make_key(name: str) -> str:
    return f"test:{name}"


class TestCachedDecorator:
    @pytest.mark.asyncio
    async def test_cache_miss_calls_function(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        call_count = 0

        @cached(ttl=60, key_func=_make_key)
        async def fetch(redis_client: object, name: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"result-{name}"

        result = await fetch(fake_redis, "foo")
        assert result == "result-foo"
        assert call_count == 1

        # Value should now be in cache
        raw = await fake_redis.get("test:foo")
        assert raw == "result-foo"

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        call_count = 0

        @cached(ttl=60, key_func=_make_key)
        async def fetch(redis_client: object, name: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"result-{name}"

        await fetch(fake_redis, "bar")
        assert call_count == 1

        result = await fetch(fake_redis, "bar")
        assert result == "result-bar"
        assert call_count <= 1  # Not called again

    @pytest.mark.asyncio
    async def test_cache_stores_with_ttl(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        @cached(ttl=120, key_func=_make_key)
        async def fetch(redis_client: object, name: str) -> str:
            return "value"

        await fetch(fake_redis, "ttl-test")
        ttl = await fake_redis.ttl("test:ttl-test")
        assert 0 < ttl <= 120

    @pytest.mark.asyncio
    async def test_pydantic_model_round_trip(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        call_count = 0

        @cached(ttl=60, key_func=_make_key, response_model=_SampleModel)
        async def fetch(redis_client: object, name: str) -> _SampleModel:
            nonlocal call_count
            call_count += 1
            return _SampleModel(name=name, value=42)

        result1 = await fetch(fake_redis, "model")
        assert isinstance(result1, _SampleModel)
        assert result1.name == "model"
        assert result1.value == 42
        assert call_count == 1

        result2 = await fetch(fake_redis, "model")
        assert isinstance(result2, _SampleModel)
        assert result2.name == "model"
        assert result2.value == 42
        assert call_count <= 1  # Served from cache

    @pytest.mark.asyncio
    async def test_pydantic_type_adapter_round_trip(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        adapter = TypeAdapter(list[_SampleModel])
        call_count = 0

        @cached(ttl=60, key_func=_make_key, response_model=adapter)
        async def fetch(redis_client: object, name: str) -> list[_SampleModel]:
            nonlocal call_count
            call_count += 1
            return [_SampleModel(name=name, value=1), _SampleModel(name=name, value=2)]

        result1 = await fetch(fake_redis, "list")
        assert len(result1) == 2
        assert call_count == 1

        result2 = await fetch(fake_redis, "list")
        assert len(result2) == 2
        assert call_count <= 1

    @pytest.mark.asyncio
    async def test_redis_read_error_falls_through(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        call_count = 0

        @cached(ttl=60, key_func=_make_key)
        async def fetch(redis_client: object, name: str) -> str:
            nonlocal call_count
            call_count += 1
            return "fallback"

        with patch.object(fake_redis, "get", side_effect=RedisError("conn lost")):
            result = await fetch(fake_redis, "err")

        assert result == "fallback"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_redis_write_error_still_returns(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        @cached(ttl=60, key_func=_make_key)
        async def fetch(redis_client: object, name: str) -> str:
            return "ok"

        with patch.object(fake_redis, "set", side_effect=RedisError("write fail")):
            result = await fetch(fake_redis, "write-err")

        assert result == "ok"

    @pytest.mark.asyncio
    async def test_none_redis_client_skips_cache(self) -> None:
        call_count = 0

        @cached(ttl=60, key_func=_make_key)
        async def fetch(redis_client: object, name: str) -> str:
            nonlocal call_count
            call_count += 1
            return "direct"

        result = await fetch(None, "no-cache")
        assert result == "direct"
        assert call_count == 1


# ---------------------------------------------------------------------------
# Client lifecycle tests
# ---------------------------------------------------------------------------


class TestClientLifecycle:
    @pytest.mark.asyncio
    async def test_close_redis_no_error(self) -> None:
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        await close_redis(client)

    @pytest.mark.asyncio
    async def test_close_redis_swallows_error(self) -> None:
        client = AsyncMock()
        client.aclose.side_effect = RedisError("shutdown fail")
        await close_redis(client)  # Should not raise
