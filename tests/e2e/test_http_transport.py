"""End-to-end tests for OAuth 2.1 authentication components.

These tests verify the JWT verifier, auth provider factory, and the
interaction between auth middleware and tools. Since in-process transport
does not support auth, we test the auth components directly.
"""

from __future__ import annotations

import pytest
from fastmcp.server.auth import AccessToken, JWTVerifier, RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import RSAKeyPair

from recipe_mcp_server.auth.provider import create_auth_provider
from recipe_mcp_server.config import Settings

TEST_ISSUER = "https://auth.example.com"
TEST_AUDIENCE = "recipe-mcp-server"


@pytest.fixture
def rsa_keypair() -> RSAKeyPair:
    """Generate a test RSA key pair for signing JWTs."""
    return RSAKeyPair.generate()


@pytest.fixture
def jwt_verifier(rsa_keypair: RSAKeyPair) -> JWTVerifier:
    """Create a JWTVerifier using the test public key."""
    return JWTVerifier(
        public_key=rsa_keypair.public_key,
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
    )


@pytest.mark.e2e
class TestJWTVerification:
    """Tests for JWT token verification."""

    async def test_valid_token_accepted(
        self, jwt_verifier: JWTVerifier, rsa_keypair: RSAKeyPair
    ) -> None:
        """A valid JWT with correct claims should be accepted."""
        token = rsa_keypair.create_token(
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            scopes=["recipe:read"],
        )

        result = await jwt_verifier.verify_token(token)
        assert result is not None
        assert isinstance(result, AccessToken)
        assert "recipe:read" in result.scopes

    async def test_expired_token_rejected(
        self, jwt_verifier: JWTVerifier, rsa_keypair: RSAKeyPair
    ) -> None:
        """An expired JWT should be rejected."""
        token = rsa_keypair.create_token(
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            scopes=["recipe:read"],
            expires_in_seconds=-10,
        )

        result = await jwt_verifier.verify_token(token)
        assert result is None

    async def test_wrong_issuer_rejected(
        self, jwt_verifier: JWTVerifier, rsa_keypair: RSAKeyPair
    ) -> None:
        """A JWT with wrong issuer should be rejected."""
        token = rsa_keypair.create_token(
            issuer="https://wrong-issuer.com",
            audience=TEST_AUDIENCE,
            scopes=["recipe:read"],
        )

        result = await jwt_verifier.verify_token(token)
        assert result is None

    async def test_wrong_audience_rejected(
        self, jwt_verifier: JWTVerifier, rsa_keypair: RSAKeyPair
    ) -> None:
        """A JWT with wrong audience should be rejected."""
        token = rsa_keypair.create_token(
            issuer=TEST_ISSUER,
            audience="wrong-audience",
            scopes=["recipe:read"],
        )

        result = await jwt_verifier.verify_token(token)
        assert result is None

    async def test_missing_required_scopes_rejected(self, rsa_keypair: RSAKeyPair) -> None:
        """A JWT missing required scopes should be rejected."""
        verifier = JWTVerifier(
            public_key=rsa_keypair.public_key,
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            required_scopes=["admin:full"],
        )

        token = rsa_keypair.create_token(
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            scopes=["recipe:read"],
        )

        result = await verifier.verify_token(token)
        assert result is None

    async def test_token_with_multiple_scopes(
        self, jwt_verifier: JWTVerifier, rsa_keypair: RSAKeyPair
    ) -> None:
        """A JWT with multiple scopes should have all scopes extracted."""
        token = rsa_keypair.create_token(
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            scopes=["recipe:read", "recipe:write", "admin"],
        )

        result = await jwt_verifier.verify_token(token)
        assert result is not None
        assert "recipe:read" in result.scopes
        assert "recipe:write" in result.scopes
        assert "admin" in result.scopes


@pytest.mark.e2e
class TestAuthProviderFactory:
    """Tests for the auth provider factory function."""

    def test_no_auth_when_issuer_empty(self) -> None:
        """Auth should be disabled when oauth_issuer is not set."""
        settings = Settings(
            oauth_issuer="",
            oauth_audience="",
            oauth_jwks_url="",
        )
        result = create_auth_provider(settings)
        assert result is None

    def test_auth_enabled_with_jwks(self) -> None:
        """Auth provider should be created when oauth_issuer is configured."""
        settings = Settings(
            oauth_issuer="https://auth.example.com",
            oauth_audience="recipe-mcp-server",
            oauth_jwks_url="https://auth.example.com/.well-known/jwks.json",
        )
        result = create_auth_provider(settings)
        assert result is not None
        assert isinstance(result, RemoteAuthProvider)
