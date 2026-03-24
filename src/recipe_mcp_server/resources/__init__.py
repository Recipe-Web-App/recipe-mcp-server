"""MCP resource registrations."""

from recipe_mcp_server.resources.blob_resources import register_blob_resources
from recipe_mcp_server.resources.dynamic_resources import register_dynamic_resources
from recipe_mcp_server.resources.static_resources import register_static_resources
from recipe_mcp_server.resources.ui_resources import register_ui_resources

__all__ = [
    "register_blob_resources",
    "register_dynamic_resources",
    "register_static_resources",
    "register_ui_resources",
]
