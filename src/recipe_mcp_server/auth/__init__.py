"""Authentication: OAuth 2.1 provider and JWT middleware."""

from recipe_mcp_server.auth.provider import create_auth_provider

__all__ = ["create_auth_provider"]
