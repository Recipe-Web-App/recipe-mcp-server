"""Audit trail decorator for MCP tools.

The :func:`audited` decorator logs before/after state to the ``audit_log``
table via :class:`~recipe_mcp_server.db.repository.AuditRepo`.  It is
designed to be applied to tool handler functions that receive a
:class:`fastmcp.Context` as their first positional argument.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog
from fastmcp import Context

from recipe_mcp_server.db.repository import AuditRepo
from recipe_mcp_server.observability.logging import request_id_ctx

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _extract_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Context | None:
    """Return the :class:`Context` from the call arguments, if present."""
    if args and isinstance(args[0], Context):
        return args[0]
    return kwargs.get("ctx")  # type: ignore[return-value]


def _parse_result_state(result: Any) -> dict[str, Any] | None:
    """Attempt to parse a tool result into a dict for after_state."""
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def audited(
    action: str,
    entity_type: str,
    entity_id_param: str | None = None,
) -> Callable[[F], F]:
    """Decorator that logs tool mutations to the audit trail.

    Args:
        action: Action name (``"create"``, ``"update"``, ``"delete"``).
        entity_type: Entity being mutated (``"recipe"``, ``"meal_plan"``).
        entity_id_param: Name of the kwarg holding the entity ID.  Used to
            fetch ``before_state`` for update/delete operations.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = _extract_context(args, kwargs)
            if ctx is None:
                return await func(*args, **kwargs)

            audit_repo: AuditRepo = ctx.lifespan_context["audit_repo"]

            # Determine entity ID from kwargs
            entity_id: str | None = None
            if entity_id_param is not None:
                entity_id = kwargs.get(entity_id_param)
                if entity_id is None and len(args) > 1:
                    # Positional fallback: ctx is args[0], entity_id is often args[1]
                    import inspect

                    sig = inspect.signature(func)
                    params = list(sig.parameters.keys())
                    if entity_id_param in params:
                        idx = params.index(entity_id_param)
                        if idx < len(args):
                            entity_id = str(args[idx])

            # Execute the actual tool
            result = await func(*args, **kwargs)

            # Extract after_state from result
            after_state = _parse_result_state(result)

            # Extract entity_id from result for create operations
            if entity_id is None and after_state is not None:
                entity_id = after_state.get("id")

            # Write audit log (fire-and-forget — never fail the tool)
            try:
                await audit_repo.log(
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    after_state=after_state,
                    tool_name=func.__name__,
                    request_id=request_id_ctx.get(),
                )
            except Exception:
                logger.warning("audit_log_failed", tool=func.__name__, exc_info=True)

            return result

        return wrapper  # type: ignore[return-value]

    return decorator
