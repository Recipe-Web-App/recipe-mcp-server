"""Auth provider factory for the Recipe MCP Server.

When OAuth settings are configured (``RECIPE_MCP_OAUTH_ISSUER`` is non-empty),
this module creates a :class:`~fastmcp.server.auth.RemoteAuthProvider` backed
by FastMCP's built-in :class:`~fastmcp.server.auth.JWTVerifier`.  When the
issuer is empty (stdio transport, development mode), authentication is disabled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from recipe_mcp_server.config import Settings

if TYPE_CHECKING:
    from fastmcp.server.auth import AuthProvider

logger = structlog.get_logger(__name__)


def create_auth_provider(settings: Settings) -> AuthProvider | None:
    """Create an auth provider if OAuth settings are configured.

    Returns ``None`` when ``oauth_issuer`` is empty, which disables
    authentication (suitable for stdio transport and local development).
    """
    if not settings.oauth_issuer:
        logger.debug("auth_disabled", reason="oauth_issuer not configured")
        return None

    if not settings.oauth_jwks_url:
        logger.warning(
            "auth_disabled",
            reason="oauth_issuer is set but oauth_jwks_url is empty",
        )
        return None

    from fastmcp.server.auth import JWTVerifier, RemoteAuthProvider
    from pydantic import AnyHttpUrl

    verifier = JWTVerifier(
        jwks_uri=settings.oauth_jwks_url,
        issuer=settings.oauth_issuer,
        audience=settings.oauth_audience or None,
    )

    base_url = f"http://{settings.host}:{settings.port}"

    provider = RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[AnyHttpUrl(settings.oauth_issuer)],
        base_url=base_url,
        scopes_supported=["recipe:read", "recipe:write"],
        resource_name=settings.server_name,
    )

    logger.info(
        "auth_enabled",
        issuer=settings.oauth_issuer,
        audience=settings.oauth_audience,
    )
    return provider
