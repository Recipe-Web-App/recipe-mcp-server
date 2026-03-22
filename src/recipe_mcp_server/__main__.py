"""Entry point for ``python -m recipe_mcp_server``."""

from __future__ import annotations

from recipe_mcp_server.config import get_settings
from recipe_mcp_server.server import mcp


def main() -> None:
    """Run the MCP server with the configured transport."""
    settings = get_settings()
    if settings.transport == "http":
        mcp.run(transport="streamable-http", host=settings.host, port=settings.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
