"""Middleware enforcing ``recipe:write`` scope on mutating tools.

Per-tool ``auth=require_scopes(...)`` causes FastMCP to hide tools from
unauthenticated clients (e.g. stdio transport), so scope enforcement for
writes is handled at the middleware level instead.
"""

from __future__ import annotations

from typing import Any

import mcp.types as mt
import structlog
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp import McpError
from mcp.types import ErrorData

logger = structlog.get_logger(__name__)

WRITE_SCOPE = "recipe:write"

# Tools that mutate state and require the write scope.
_MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "create_recipe",
        "update_recipe",
        "delete_recipe",
        "save_favorite",
        "generate_meal_plan",
    }
)

FORBIDDEN_CODE = -32600


class WriteScopeMiddleware(Middleware):
    """Require ``recipe:write`` scope for mutating tool calls.

    Read-only tools pass through without additional checks.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> Any:
        tool_name = context.message.name if context.message else None
        if tool_name not in _MUTATING_TOOLS:
            return await call_next(context)

        # Check if the caller has recipe:write scope
        fastmcp_ctx = context.fastmcp_context
        if fastmcp_ctx is not None:
            auth_info = getattr(fastmcp_ctx, "access_token", None)
            if auth_info is not None:
                scopes = getattr(auth_info, "scopes", []) or []
                if WRITE_SCOPE not in scopes:
                    logger.warning(
                        "write_scope_denied",
                        tool=tool_name,
                        scopes=scopes,
                    )
                    raise McpError(
                        ErrorData(
                            code=FORBIDDEN_CODE,
                            message=f"Scope '{WRITE_SCOPE}' required for {tool_name}",
                        )
                    )

        return await call_next(context)
