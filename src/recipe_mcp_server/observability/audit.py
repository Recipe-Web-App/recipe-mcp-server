"""Audit trail decorator for MCP tools.

The :func:`audited` decorator logs tool results (after-state) to the
``audit_log`` table via :class:`~recipe_mcp_server.db.repository.AuditRepo`.
It is designed to be applied to tool handler functions that receive a
:class:`fastmcp.Context` as their first positional argument.
"""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog
from fastmcp import Context

from recipe_mcp_server.observability.logging import request_id_ctx

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _extract_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Context | None:
    """Return the :class:`Context` from the call arguments, if present."""
    if args and isinstance(args[0], Context):
        return args[0]
    ctx = kwargs.get("ctx")
    if isinstance(ctx, Context):
        return ctx
    return None


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
            logger.debug("audit_parse_result_not_json", result_type=type(result).__name__)
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
            identify the entity for update/delete operations.
    """

    def decorator(func: F) -> F:
        # Pre-compute positional index for entity_id_param (once at decoration time)
        _entity_id_positional_idx: int | None = None
        if entity_id_param is not None:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if entity_id_param in params:
                _entity_id_positional_idx = params.index(entity_id_param)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = _extract_context(args, kwargs)
            if ctx is None:
                return await func(*args, **kwargs)

            audit_repo = ctx.lifespan_context.get("audit_repo")
            if audit_repo is None:
                logger.warning("audit_repo_not_available", tool=func.__name__)
                return await func(*args, **kwargs)

            # Determine entity ID from kwargs or positional args
            entity_id: str | None = None
            if entity_id_param is not None:
                raw_id = kwargs.get(entity_id_param)
                if (
                    raw_id is None
                    and _entity_id_positional_idx is not None
                    and _entity_id_positional_idx < len(args)
                ):
                    raw_id = args[_entity_id_positional_idx]
                if raw_id is not None:
                    entity_id = str(raw_id)

            # Execute the actual tool
            result = await func(*args, **kwargs)

            # Extract after_state from result
            after_state = _parse_result_state(result)

            # Extract entity_id from result for create operations
            if entity_id is None and after_state is not None:
                raw_id = after_state.get("id")
                if raw_id is not None:
                    entity_id = str(raw_id)

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
