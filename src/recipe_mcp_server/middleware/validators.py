"""Input sanitization validators for tool parameters.

Validation functions are called at tool entry points.  Any failure raises
:class:`~recipe_mcp_server.exceptions.ValidationError`, which the
:class:`~recipe_mcp_server.middleware.error_handler.ErrorHandlerMiddleware`
maps to an ``InvalidParams`` MCP error.
"""

from __future__ import annotations

import re

from recipe_mcp_server.exceptions import ValidationError

MAX_STRING_LENGTH = 5000
MAX_QUERY_LENGTH = 200


def sanitize_string(value: str, field_name: str, max_length: int = MAX_STRING_LENGTH) -> str:
    """Strip and length-check a string parameter.

    Args:
        value: The input string.
        field_name: Field name for error messages.
        max_length: Maximum allowed length.

    Returns:
        The stripped string.

    Raises:
        ValidationError: If the string is empty or exceeds *max_length*.
    """
    value = value.strip()
    if not value:
        raise ValidationError(f"{field_name} must not be empty")
    if len(value) > max_length:
        raise ValidationError(f"{field_name} exceeds maximum length of {max_length}")
    return value


def sanitize_query(query: str) -> str:
    """Sanitize a search query: strip, length-check, remove control characters.

    Raises:
        ValidationError: If the query is empty or exceeds *MAX_QUERY_LENGTH*.
    """
    query = re.sub(r"[\x00-\x1f\x7f]", "", query.strip())
    if not query:
        raise ValidationError("Search query must not be empty")
    if len(query) > MAX_QUERY_LENGTH:
        raise ValidationError(f"Search query exceeds maximum length of {MAX_QUERY_LENGTH}")
    return query


def validate_positive_int(value: int, field_name: str) -> int:
    """Ensure an integer is positive.

    Raises:
        ValidationError: If *value* is not positive.
    """
    if value <= 0:
        raise ValidationError(f"{field_name} must be positive, got {value}")
    return value


def validate_rating(value: int | None) -> int | None:
    """Ensure rating is 1-5 if provided.

    Raises:
        ValidationError: If *value* is outside the 1-5 range.
    """
    if value is not None and not (1 <= value <= 5):
        raise ValidationError(f"Rating must be between 1 and 5, got {value}")
    return value
