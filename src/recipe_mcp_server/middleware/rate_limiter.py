"""Rate limiter factory using FastMCP's built-in middleware.

Uses :class:`~fastmcp.server.middleware.rate_limiting.RateLimitingMiddleware`
with a token-bucket algorithm for per-client rate limiting.
"""

from __future__ import annotations

from fastmcp.server.middleware.middleware import Middleware
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware

DEFAULT_MAX_REQUESTS_PER_SECOND = 10.0
DEFAULT_BURST_CAPACITY = 20


def create_rate_limiter(
    max_requests_per_second: float = DEFAULT_MAX_REQUESTS_PER_SECOND,
    burst_capacity: int = DEFAULT_BURST_CAPACITY,
) -> Middleware:
    """Create a configured rate limiter middleware.

    Args:
        max_requests_per_second: Sustained request rate allowed per client.
        burst_capacity: Maximum burst capacity before throttling.

    Returns:
        A configured :class:`RateLimitingMiddleware` instance.
    """
    return RateLimitingMiddleware(
        max_requests_per_second=max_requests_per_second,
        burst_capacity=burst_capacity,
    )
