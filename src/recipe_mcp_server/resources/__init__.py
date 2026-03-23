"""MCP resource registrations."""

from recipe_mcp_server.resources.dynamic_resources import register_dynamic_resources
from recipe_mcp_server.resources.static_resources import register_static_resources

__all__ = [
    "register_dynamic_resources",
    "register_static_resources",
]
