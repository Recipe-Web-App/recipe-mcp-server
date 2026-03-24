"""Meal planning prompts: weekly_meal_plan, holiday_menu."""

from __future__ import annotations

import structlog
from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message, PromptResult

logger = structlog.get_logger(__name__)


def register_meal_plan_prompts(mcp: FastMCP) -> None:
    """Register meal-planning prompts on the given FastMCP server."""

    @mcp.prompt(tags={"planning"})
    async def weekly_meal_plan(
        people_count: int,
        diet: str | None = None,
        budget: str | None = None,
        cooking_skill: str | None = None,
    ) -> PromptResult:
        """Generate a complete weekly meal plan with nutritional guidelines.

        Args:
            people_count: Number of people to plan for.
            diet: Dietary preference (e.g. "vegetarian", "keto", "mediterranean").
            budget: Budget level — "low", "medium", or "high".
            cooking_skill: Cook's skill level (e.g. "beginner", "intermediate", "advanced").
        """
        details: list[str] = [f"People: {people_count}"]
        if diet:
            details.append(f"Diet: {diet}")
        if budget:
            details.append(f"Budget: {budget}")
        if cooking_skill:
            details.append(f"Cooking skill: {cooking_skill}")

        system_msg = (
            "You are a certified nutritionist and meal planning expert. "
            "Create balanced weekly meal plans that meet nutritional guidelines, "
            "respect dietary preferences, and stay within budget. Include "
            "breakfast, lunch, dinner, and one snack for each day. Provide a "
            "consolidated shopping list at the end."
        )
        user_msg = (
            "Please create a weekly meal plan (Monday through Sunday) with these "
            "requirements:\n\n"
            + "\n".join(f"- {d}" for d in details)
            + "\n\nFor each meal, include the recipe name and a brief description. "
            "End with a consolidated shopping list and estimated nutritional summary."
        )

        return PromptResult(
            messages=[
                Message(system_msg, role="assistant"),
                Message(user_msg, role="user"),
            ],
            description=f"Weekly meal plan for {people_count} people",
        )

    @mcp.prompt(tags={"planning"})
    async def holiday_menu(
        occasion: str,
        guest_count: int,
        restrictions: list[str] | None = None,
    ) -> PromptResult:
        """Plan a complete multi-course holiday or occasion menu.

        Args:
            occasion: The holiday or occasion (e.g. "Thanksgiving", "Christmas", "birthday dinner").
            guest_count: Number of guests to serve.
            restrictions: Dietary restrictions to accommodate (e.g. ["nut-free", "vegetarian"]).
        """
        details: list[str] = [
            f"Occasion: {occasion}",
            f"Guests: {guest_count}",
        ]
        if restrictions:
            details.append(f"Dietary restrictions: {', '.join(restrictions)}")

        system_msg = (
            "You are a professional event chef specialising in holiday and "
            "special-occasion dining. Plan multi-course menus that are festive, "
            "cohesive, and practical. Consider timing so the host can enjoy the "
            "event too — include make-ahead suggestions."
        )
        user_msg = (
            "Please plan a complete multi-course menu with these details:\n\n"
            + "\n".join(f"- {d}" for d in details)
            + "\n\nInclude appetisers, main course, sides, and dessert. "
            "For each dish, provide a brief recipe overview and any "
            "make-ahead or timing tips."
        )

        return PromptResult(
            messages=[
                Message(system_msg, role="assistant"),
                Message(user_msg, role="user"),
            ],
            description=f"{occasion} menu for {guest_count} guests",
        )
