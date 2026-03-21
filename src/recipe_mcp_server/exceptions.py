"""Domain exception hierarchy for the Recipe MCP Server."""

from __future__ import annotations


class RecipeMCPError(Exception):
    """Base exception for all recipe MCP server errors."""


class CacheError(RecipeMCPError):
    """Non-fatal cache operation error. Log and proceed without cache."""
