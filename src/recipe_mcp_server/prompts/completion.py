"""Argument completion handlers for MCP prompts."""

from __future__ import annotations

import structlog
from fastmcp import FastMCP
from mcp import types as mcp_types

logger = structlog.get_logger(__name__)

# Well-known cuisines: TheMealDB areas + common world cuisines + cuisine styles.
CUISINES = [
    "Afghan",
    "Algerian",
    "American",
    "Argentinian",
    "Australian",
    "Brazilian",
    "British",
    "Cajun",
    "Canadian",
    "Caribbean",
    "Chinese",
    "Colombian",
    "Creole",
    "Croatian",
    "Cuban",
    "Dutch",
    "Egyptian",
    "Ethiopian",
    "Filipino",
    "French",
    "Fusion",
    "Georgian",
    "German",
    "Greek",
    "Hawaiian",
    "Indian",
    "Indonesian",
    "Irish",
    "Israeli",
    "Italian",
    "Jamaican",
    "Japanese",
    "Kenyan",
    "Korean",
    "Lebanese",
    "Malaysian",
    "Mediterranean",
    "Mexican",
    "Middle Eastern",
    "Moroccan",
    "Nepalese",
    "Nordic",
    "Norwegian",
    "Peruvian",
    "Polish",
    "Portuguese",
    "Russian",
    "Saudi Arabian",
    "Scandinavian",
    "Slovakian",
    "Southern",
    "Spanish",
    "Sri Lankan",
    "Syrian",
    "Taiwanese",
    "Tex-Mex",
    "Thai",
    "Tunisian",
    "Turkish",
    "Ukrainian",
    "Uruguayan",
    "Venezuelan",
    "Vietnamese",
    "West African",
]

DIETARY_RESTRICTIONS = [
    "dairy-free",
    "gluten-free",
    "halal",
    "keto",
    "kosher",
    "nut-free",
    "paleo",
    "vegan",
    "vegetarian",
]

MAX_COMPLETION_VALUES = 100


def _filter_by_prefix(values: list[str], prefix: str) -> mcp_types.Completion:
    """Return values whose name starts with the given prefix (case-insensitive)."""
    lowered = prefix.lower()
    matches = [v for v in values if v.lower().startswith(lowered)]
    return mcp_types.Completion(
        values=matches[:MAX_COMPLETION_VALUES],
        total=len(matches),
        hasMore=len(matches) > MAX_COMPLETION_VALUES,
    )


async def _handle_completion(
    ref: mcp_types.PromptReference | mcp_types.ResourceTemplateReference,
    argument: mcp_types.CompletionArgument,
    context: mcp_types.CompletionContext | None,
) -> mcp_types.Completion | None:
    """Dispatch completion requests to the appropriate handler."""
    if not isinstance(ref, mcp_types.PromptReference):
        return None

    if ref.name == "generate_recipe" and argument.name == "cuisine":
        return _filter_by_prefix(CUISINES, argument.value)

    if ref.name == "adapt_for_diet" and argument.name == "restrictions":
        return _filter_by_prefix(DIETARY_RESTRICTIONS, argument.value)

    return None


async def _completion_request_handler(
    req: mcp_types.CompleteRequest,
) -> mcp_types.ServerResult:
    """Low-level request handler that wraps the completion logic."""
    completion = await _handle_completion(req.params.ref, req.params.argument, req.params.context)
    return mcp_types.ServerResult(
        mcp_types.CompleteResult(
            completion=completion
            if completion is not None
            else mcp_types.Completion(values=[], total=None, hasMore=None),
        )
    )


def register_completion_handler(mcp: FastMCP) -> None:
    """Register the global completion handler for prompt argument completions.

    Registers directly on the low-level server's request_handlers dict since
    the high-level FastMCP API does not yet expose completion registration.
    """
    mcp._mcp_server.request_handlers[mcp_types.CompleteRequest] = _completion_request_handler
