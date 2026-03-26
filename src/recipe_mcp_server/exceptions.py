"""Domain exception hierarchy for the Recipe MCP Server."""

from __future__ import annotations


class RecipeMCPError(Exception):
    """Base exception for all recipe MCP server errors."""


class NotFoundError(RecipeMCPError):
    """Recipe, food, or meal plan not found."""


class CacheError(RecipeMCPError):
    """Non-fatal cache operation error. Log and proceed without cache."""


class ExternalAPIError(RecipeMCPError):
    """Upstream API failure.

    Attributes:
        api_name: Name of the failing API (e.g. "TheMealDB").
        status_code: HTTP status code, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        api_name: str = "",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.api_name = api_name
        self.status_code = status_code


class RateLimitError(ExternalAPIError):
    """429 from upstream. Includes retry-after when available.

    Attributes:
        retry_after: Seconds to wait before retrying, if the API provided it.
    """

    def __init__(
        self,
        message: str,
        *,
        api_name: str = "",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, api_name=api_name, status_code=429)
        self.retry_after = retry_after


class ServiceUnavailableError(ExternalAPIError):
    """5xx or connection timeout from upstream."""


class AuthenticationError(ExternalAPIError):
    """API key invalid or expired."""


class ValidationError(RecipeMCPError):
    """Invalid input parameters (caught by Pydantic or manual validation)."""


class DuplicateError(RecipeMCPError):
    """Attempted to create a duplicate resource."""


class DatabaseError(RecipeMCPError):
    """Unrecoverable database operation failure."""


class AuthorizationError(RecipeMCPError):
    """Caller lacks permission for the requested operation (OAuth/scope failure)."""
