"""Tests for the /health endpoint used by Docker healthcheck."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastmcp import FastMCP
from httpx import ASGITransport


@pytest.mark.e2e
class TestHealthEndpoint:
    """Verify the /health route returns 200 with status ok."""

    async def test_health_returns_ok(self, mcp_server: FastMCP) -> None:
        app = mcp_server.http_app(transport="streamable-http")
        transport = ASGITransport(app=app)
        async with respx.mock:
            respx.route().mock(return_value=httpx.Response(200, json={}))
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")
                assert resp.status_code == 200
                assert resp.json() == {"status": "ok"}
