"""MCP tool registrations."""

from recipe_mcp_server.tools.meal_plan_tools import register_meal_plan_tools
from recipe_mcp_server.tools.nutrition_tools import register_nutrition_tools
from recipe_mcp_server.tools.recipe_tools import register_recipe_tools
from recipe_mcp_server.tools.utility_tools import register_utility_tools

__all__ = [
    "register_meal_plan_tools",
    "register_nutrition_tools",
    "register_recipe_tools",
    "register_utility_tools",
]
