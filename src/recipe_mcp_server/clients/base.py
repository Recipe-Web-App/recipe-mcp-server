"""BaseAPIClient: abstract async HTTP client with retry, circuit breaker, and caching."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, TypeVar

import httpx
import structlog
from pydantic import BaseModel
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from recipe_mcp_server.exceptions import (
    AuthenticationError,
    ExternalAPIError,
    RateLimitError,
    ServiceUnavailableError,
)

logger = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# Retry configuration (REQUIREMENTS 7.4)
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 0.5

# Circuit breaker configuration (REQUIREMENTS 7.4)
CB_FAILURE_THRESHOLD = 5
CB_WINDOW_SECONDS = 60
CB_RECOVERY_TIMEOUT_SECONDS = 30

# Request timeout (REQUIREMENTS 7.4)
REQUEST_TIMEOUT_SECONDS = 10.0


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-client circuit breaker.

    Opens after ``failure_threshold`` failures within ``window_seconds``,
    then transitions to half-open after ``recovery_timeout`` seconds.
    A single success in half-open closes the circuit; a failure re-opens it.
    """

    def __init__(
        self,
        failure_threshold: int = CB_FAILURE_THRESHOLD,
        window_seconds: float = CB_WINDOW_SECONDS,
        recovery_timeout: float = CB_RECOVERY_TIMEOUT_SECONDS,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failures: list[float] = []
        self._opened_at: float = 0.0

    @property
    def state(self) -> CircuitState:
        elapsed = time.monotonic() - self._opened_at
        if self._state is CircuitState.OPEN and elapsed >= self.recovery_timeout:
            self._state = CircuitState.HALF_OPEN
        return self._state

    def record_success(self) -> None:
        """Record a successful call — close the circuit."""
        self._state = CircuitState.CLOSED
        self._failures.clear()

    def record_failure(self) -> None:
        """Record a failure. Opens the circuit if threshold is exceeded."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        self._failures = [t for t in self._failures if t > cutoff]
        self._failures.append(now)

        if self._state is CircuitState.HALF_OPEN or len(self._failures) >= self.failure_threshold:
            self._open(now)

    def ensure_closed(self) -> None:
        """Raise ``ServiceUnavailableError`` if the circuit is open."""
        if self.state is CircuitState.OPEN:
            raise ServiceUnavailableError(
                "Circuit breaker is open — upstream service unavailable",
                api_name="",
            )

    def _open(self, now: float) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = now


def _is_retryable(exc: BaseException) -> bool:
    """Return True for exceptions that should trigger a retry."""
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, ServiceUnavailableError):
        return True
    return isinstance(exc, httpx.TimeoutException)


def _before_sleep_log(retry_state: RetryCallState) -> None:
    """Log each retry attempt."""
    logger.warning(
        "api_retry",
        attempt=retry_state.attempt_number,
        wait=retry_state.next_action.sleep if retry_state.next_action else 0,  # pyright: ignore[reportOptionalMemberAccess]
        error=str(retry_state.outcome.exception()) if retry_state.outcome else None,
    )


class BaseAPIClient(ABC):
    """Abstract base for all downstream API clients.

    Subclasses must implement :pyattr:`api_name` and :pyattr:`base_url`.
    They may override :meth:`_default_headers` for authentication headers.

    Usage::

        class TheMealDBClient(BaseAPIClient):
            api_name = "TheMealDB"
            base_url = "https://www.themealdb.com/api/json/v1/1"

            async def search(self, query: str) -> list[Recipe]:
                data = await self._get("/search.php", params={"s": query})
                return [Recipe.model_validate(m) for m in data.get("meals") or []]
    """

    api_name: str = ""
    base_url: str = ""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self._owns_http_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers=self._default_headers(),
        )
        self._redis = redis_client
        self._circuit = CircuitBreaker()

    def _default_headers(self) -> dict[str, str]:
        """Return default headers for every request. Override for auth."""
        return {"Accept": "application/json"}

    async def aclose(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_http_client:
            await self._http.aclose()

    # -- Public request helpers ------------------------------------------------

    async def _get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Perform a GET request with retry + circuit breaker."""
        return await self._request("GET", endpoint, params=params, headers=headers)

    async def _post(
        self,
        endpoint: str,
        *,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Perform a POST request with retry + circuit breaker."""
        return await self._request("POST", endpoint, json_body=json_body, headers=headers)

    async def _get_model(
        self,
        endpoint: str,
        model: type[T],
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> T:
        """GET and deserialize the response into a Pydantic model."""
        data = await self._get(endpoint, params=params, headers=headers)
        return model.model_validate(data)

    # -- Cache helpers ---------------------------------------------------------

    @abstractmethod
    def _build_cache_key(self, endpoint: str, params: dict[str, Any] | None) -> str:
        """Build a cache key for this request. Subclasses must implement."""

    async def _cache_get(self, key: str) -> str | None:
        """Read from cache, returning None on miss or error."""
        if self._redis is None:
            return None
        try:
            result: str | None = await self._redis.get(key)
            if result is not None:
                logger.debug("client_cache_hit", key=key, api=self.api_name)
            return result
        except Exception:
            logger.warning("client_cache_read_error", key=key, exc_info=True)
            return None

    async def _cache_set(self, key: str, value: str, ttl: int) -> None:
        """Write to cache, ignoring errors (non-fatal per REQUIREMENTS 8.2)."""
        if self._redis is None:
            return
        try:
            await self._redis.set(key, value, ex=ttl)
            logger.debug("client_cache_set", key=key, ttl=ttl, api=self.api_name)
        except Exception:
            logger.warning("client_cache_write_error", key=key, exc_info=True)

    # -- Core request engine ---------------------------------------------------

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=INITIAL_BACKOFF_SECONDS, min=INITIAL_BACKOFF_SECONDS),
        before_sleep=_before_sleep_log,
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Execute an HTTP request with circuit breaker, retry, and error mapping."""
        self._circuit.ensure_closed()

        try:
            response = await self._http.request(
                method,
                endpoint,
                params=params,
                json=json_body,
                headers=headers,
            )
        except httpx.TimeoutException:
            self._circuit.record_failure()
            raise ServiceUnavailableError(
                f"{self.api_name}: request timed out",
                api_name=self.api_name,
            ) from None
        except httpx.HTTPError as exc:
            self._circuit.record_failure()
            raise ServiceUnavailableError(
                f"{self.api_name}: connection error: {exc}",
                api_name=self.api_name,
            ) from exc

        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> Any:
        """Map HTTP status codes to domain exceptions and return parsed JSON."""
        status = response.status_code

        if 200 <= status < 300:
            self._circuit.record_success()
            return response.json()

        # Error paths — record failure for circuit breaker
        self._circuit.record_failure()

        if status == 401:
            raise AuthenticationError(
                f"{self.api_name}: authentication failed",
                api_name=self.api_name,
            )

        if status == 429:
            retry_after_header = response.headers.get("Retry-After")
            retry_after = float(retry_after_header) if retry_after_header else None
            raise RateLimitError(
                f"{self.api_name}: rate limited (429)",
                api_name=self.api_name,
                retry_after=retry_after,
            )

        if status >= 500:
            raise ServiceUnavailableError(
                f"{self.api_name}: server error ({status})",
                api_name=self.api_name,
                status_code=status,
            )

        # Other client errors (400, 403, 404, etc.) — not retryable
        raise ExternalAPIError(
            f"{self.api_name}: HTTP {status}",
            api_name=self.api_name,
            status_code=status,
        )
