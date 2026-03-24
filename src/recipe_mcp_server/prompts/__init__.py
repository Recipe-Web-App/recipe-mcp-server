"""MCP prompt registrations."""

from recipe_mcp_server.prompts.cooking_prompts import register_cooking_prompts
from recipe_mcp_server.prompts.dietary_prompts import register_dietary_prompts
from recipe_mcp_server.prompts.meal_plan_prompts import register_meal_plan_prompts
from recipe_mcp_server.prompts.recipe_prompts import register_recipe_prompts

__all__ = [
    "register_cooking_prompts",
    "register_dietary_prompts",
    "register_meal_plan_prompts",
    "register_recipe_prompts",
]
