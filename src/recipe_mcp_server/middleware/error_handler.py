"""Unified error handling middleware mapping domain exceptions to MCP responses.

This middleware catches domain exceptions raised by tool handlers and maps
them to appropriate MCP protocol responses per the requirements:

- ``NotFoundError``      -> structured "not found" content (not a protocol error)
- ``ValidationError``    -> ``InvalidParams`` MCP error (-32602)
- ``RateLimitError``     -> tool error content with retry_after guidance
- ``ExternalAPIError``   -> tool error content with API name
- ``CacheError``         -> silent degradation (log warning only)
- ``DatabaseError``      -> ``InternalError`` MCP error (-32603)
"""

from __future__ import annotations

import json
from typing import Any

import mcp.types as mt
import structlog
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp import McpError
from mcp.types import ErrorData

from recipe_mcp_server.exceptions import (
    CacheError,
    DatabaseError,
    ExternalAPIError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

logger = structlog.get_logger(__name__)

INVALID_PARAMS_CODE = -32602
INTERNAL_ERROR_CODE = -32603


class ErrorHandlerMiddleware(Middleware):
    """Wraps tool calls to map domain exceptions to proper MCP responses."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> Any:
        try:
            return await call_next(context)
        except NotFoundError as exc:
            logger.info("tool_not_found", error=str(exc))
            return [mt.TextContent(type="text", text=f"Not found: {exc}")]
        except ValidationError as exc:
            logger.info("tool_validation_error", error=str(exc))
            raise McpError(ErrorData(code=INVALID_PARAMS_CODE, message=str(exc))) from exc
        except RateLimitError as exc:
            logger.warning(
                "tool_rate_limited",
                api=exc.api_name,
                retry_after=exc.retry_after,
            )
            return [
                mt.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": "rate_limited",
                            "detail": str(exc),
                            "retry_after": exc.retry_after,
                        }
                    ),
                )
            ]
        except ExternalAPIError as exc:
            logger.warning("tool_external_api_error", api=exc.api_name, error=str(exc))
            return [
                mt.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": "external_api_error",
                            "api": exc.api_name,
                            "detail": str(exc),
                        }
                    ),
                )
            ]
        except CacheError as exc:
            logger.warning("tool_cache_error", error=str(exc), exc_info=True)
            return [
                mt.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": "cache_unavailable",
                            "detail": "Non-critical cache failure; results may be degraded.",
                        }
                    ),
                )
            ]
        except DatabaseError as exc:
            logger.error("tool_database_error", error=str(exc))
            raise McpError(
                ErrorData(code=INTERNAL_ERROR_CODE, message=f"Database error: {exc}")
            ) from exc
