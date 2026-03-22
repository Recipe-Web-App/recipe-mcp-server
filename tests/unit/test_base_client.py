"""Tests for BaseAPIClient: retry, circuit breaker, deserialization, error wrapping."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx
from pydantic import BaseModel

from recipe_mcp_server.clients.base import (
    CB_FAILURE_THRESHOLD,
    BaseAPIClient,
    CircuitBreaker,
    CircuitState,
)
from recipe_mcp_server.exceptions import (
    AuthenticationError,
    ExternalAPIError,
    RateLimitError,
    ServiceUnavailableError,
)

# -- Test fixtures ------------------------------------------------------------

BASE_URL = "https://api.example.com"


class DummyResponse(BaseModel):
    name: str
    value: int


class ConcreteClient(BaseAPIClient):
    """Minimal concrete subclass for testing."""

    api_name = "TestAPI"
    base_url = BASE_URL

    def _build_cache_key(self, endpoint: str, params: dict[str, Any] | None) -> str:
        return f"test:{endpoint}:{params}"


@pytest.fixture
def client() -> ConcreteClient:
    http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
    return ConcreteClient(http_client=http)


# -- Successful requests ------------------------------------------------------


@respx.mock
async def test_get_returns_json(client: ConcreteClient) -> None:
    respx.get(f"{BASE_URL}/items").mock(
        return_value=httpx.Response(200, json={"name": "test", "value": 42})
    )
    result = await client._get("/items")
    assert result == {"name": "test", "value": 42}


@respx.mock
async def test_get_model_deserializes(client: ConcreteClient) -> None:
    respx.get(f"{BASE_URL}/items/1").mock(
        return_value=httpx.Response(200, json={"name": "widget", "value": 99})
    )
    model = await client._get_model("/items/1", DummyResponse)
    assert isinstance(model, DummyResponse)
    assert model.name == "widget"
    assert model.value == 99


@respx.mock
async def test_post_sends_json(client: ConcreteClient) -> None:
    route = respx.post(f"{BASE_URL}/items").mock(
        return_value=httpx.Response(201, json={"id": "abc"})
    )
    result = await client._post("/items", json_body={"name": "new"})
    assert result == {"id": "abc"}
    assert route.called


# -- Error mapping ------------------------------------------------------------


@respx.mock
async def test_401_raises_authentication_error(client: ConcreteClient) -> None:
    respx.get(f"{BASE_URL}/secret").mock(return_value=httpx.Response(401))
    with pytest.raises(AuthenticationError, match="authentication failed"):
        await client._get("/secret")


@respx.mock
async def test_429_raises_rate_limit_error(client: ConcreteClient) -> None:
    respx.get(f"{BASE_URL}/limited").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "30"})
    )
    with pytest.raises(RateLimitError) as exc_info:
        await client._get("/limited")
    assert exc_info.value.retry_after == 30.0
    assert exc_info.value.status_code == 429


@respx.mock
async def test_500_raises_service_unavailable(client: ConcreteClient) -> None:
    respx.get(f"{BASE_URL}/broken").mock(return_value=httpx.Response(500))
    with pytest.raises(ServiceUnavailableError, match="server error"):
        await client._get("/broken")


@respx.mock
async def test_404_raises_external_api_error(client: ConcreteClient) -> None:
    respx.get(f"{BASE_URL}/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(ExternalAPIError) as exc_info:
        await client._get("/missing")
    assert exc_info.value.status_code == 404


# -- Retry behavior -----------------------------------------------------------


@respx.mock
async def test_retries_on_429_then_succeeds(client: ConcreteClient) -> None:
    route = respx.get(f"{BASE_URL}/flaky").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    result = await client._get("/flaky")
    assert result == {"ok": True}
    assert route.call_count == 2


@respx.mock
async def test_retries_on_500_then_succeeds(client: ConcreteClient) -> None:
    route = respx.get(f"{BASE_URL}/flaky").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    result = await client._get("/flaky")
    assert result == {"ok": True}
    assert route.call_count == 2


@respx.mock
async def test_exhausts_retries_on_repeated_500(client: ConcreteClient) -> None:
    respx.get(f"{BASE_URL}/down").mock(return_value=httpx.Response(500))
    with pytest.raises(ServiceUnavailableError):
        await client._get("/down")


@respx.mock
async def test_no_retry_on_400(client: ConcreteClient) -> None:
    route = respx.get(f"{BASE_URL}/bad").mock(return_value=httpx.Response(400))
    with pytest.raises(ExternalAPIError):
        await client._get("/bad")
    assert route.call_count == 1


# -- Circuit breaker ----------------------------------------------------------


class TestCircuitBreaker:
    def test_starts_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state is CircuitState.CLOSED

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, window_seconds=60)
        for _ in range(3):
            cb.record_failure()
        assert cb.state is CircuitState.OPEN

    def test_stays_closed_below_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, window_seconds=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitState.CLOSED

    def test_transitions_to_half_open(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=999)
        cb.record_failure()
        assert cb.state is CircuitState.OPEN
        # Simulate recovery timeout elapsed
        cb._opened_at = time.monotonic() - 1000
        assert cb.state is CircuitState.HALF_OPEN

    def test_success_in_half_open_closes(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.0)
        cb.record_failure()
        _ = cb.state  # trigger half-open transition
        cb.record_success()
        assert cb.state is CircuitState.CLOSED

    def test_failure_in_half_open_reopens(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=999)
        cb.record_failure()
        assert cb.state is CircuitState.OPEN
        # Simulate recovery timeout elapsed -> half-open
        cb._opened_at = time.monotonic() - 1000
        assert cb.state is CircuitState.HALF_OPEN
        cb.record_failure()
        # Should re-open with a fresh opened_at
        assert cb._state is CircuitState.OPEN

    def test_old_failures_expire(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, window_seconds=0.0)
        cb.record_failure()
        cb.record_failure()
        # Failures are outside window (window=0), so new failure alone isn't enough
        # Actually with window=0, all past failures get pruned. Let's use a real scenario.
        cb2 = CircuitBreaker(failure_threshold=3, window_seconds=60)
        now = time.monotonic()
        # Manually inject old failures outside the window
        cb2._failures = [now - 120, now - 90]
        cb2.record_failure()  # This prunes old ones, adds 1 new
        assert cb2.state is CircuitState.CLOSED

    def test_ensure_closed_raises_when_open(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=999)
        cb.record_failure()
        with pytest.raises(ServiceUnavailableError, match="circuit breaker is open"):
            cb.ensure_closed()

    def test_ensure_closed_allows_when_closed(self) -> None:
        cb = CircuitBreaker()
        cb.ensure_closed()  # Should not raise


@respx.mock
async def test_circuit_breaker_blocks_requests(client: ConcreteClient) -> None:
    """After enough failures, the circuit opens and blocks further requests."""
    respx.get(f"{BASE_URL}/down").mock(return_value=httpx.Response(500))

    # Exhaust retries to accumulate failures
    for _ in range(CB_FAILURE_THRESHOLD):
        with pytest.raises(ServiceUnavailableError):
            await client._get("/down")

    # Now the circuit should be open — next call fails immediately
    with pytest.raises(ServiceUnavailableError, match="circuit breaker is open"):
        await client._get("/down")


@respx.mock
async def test_circuit_breaker_recovers_on_half_open_success(
    client: ConcreteClient,
) -> None:
    """After recovery timeout, a successful probe closes the circuit."""
    respx.get(f"{BASE_URL}/recovering").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    # Open the circuit
    with patch.object(client._circuit, "recovery_timeout", 0.0):
        with pytest.raises(ServiceUnavailableError):
            await client._get("/recovering")

        # After recovery timeout (0s), should allow a probe
        result = await client._get("/recovering")
        assert result == {"ok": True}
        assert client._circuit.state is CircuitState.CLOSED


# -- Timeout handling ---------------------------------------------------------


@respx.mock
async def test_timeout_raises_service_unavailable(client: ConcreteClient) -> None:
    respx.get(f"{BASE_URL}/slow").mock(side_effect=httpx.ReadTimeout("timed out"))
    with pytest.raises(ServiceUnavailableError, match="timed out"):
        await client._get("/slow")


@respx.mock
async def test_connection_error_raises_service_unavailable(
    client: ConcreteClient,
) -> None:
    respx.get(f"{BASE_URL}/offline").mock(side_effect=httpx.ConnectError("connection refused"))
    with pytest.raises(ServiceUnavailableError, match="connection error"):
        await client._get("/offline")


# -- Cache integration --------------------------------------------------------


@respx.mock
async def test_cache_get_returns_none_without_redis(client: ConcreteClient) -> None:
    result = await client._cache_get("some_key")
    assert result is None


@respx.mock
async def test_cache_set_noop_without_redis(client: ConcreteClient) -> None:
    await client._cache_set("key", "value", 60)  # Should not raise


# -- Lifecycle ----------------------------------------------------------------


async def test_aclose_owned_client() -> None:
    c = ConcreteClient()
    await c.aclose()  # Should not raise


async def test_aclose_borrowed_client() -> None:
    http = httpx.AsyncClient(base_url=BASE_URL)
    c = ConcreteClient(http_client=http)
    await c.aclose()  # Should NOT close the borrowed client
    # The borrowed client should still be usable
    assert not http.is_closed
    await http.aclose()
