"""Seed the database with sample recipes, users, meal plans, and nutrition data.

Idempotent: safe to run multiple times. Uses session.merge() with
deterministic primary keys so rows are inserted on first run and
updated (no-op if unchanged) on subsequent runs.

Usage:
    uv run python scripts/seed_db.py
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence

from recipe_mcp_server.config import get_settings
from recipe_mcp_server.db.engine import get_session_factory, init_engine
from recipe_mcp_server.db.tables import (
    Base,
    FavoriteTable,
    MealPlanItemTable,
    MealPlanTable,
    NutritionCacheTable,
    RecipeIngredientTable,
    RecipeTable,
    UserProfileTable,
)

# ---------------------------------------------------------------------------
# Seed data with deterministic IDs for idempotency
# ---------------------------------------------------------------------------

RECIPES = [
    RecipeTable(
        id="seed-recipe-001",
        title="Classic Margherita Pizza",
        description="Traditional Neapolitan pizza with fresh mozzarella and basil.",
        instructions=json.dumps(
            [
                "Preheat oven to 475F (245C) with pizza stone.",
                "Stretch dough into a 12-inch round.",
                "Spread crushed San Marzano tomatoes evenly.",
                "Tear fresh mozzarella and distribute over sauce.",
                "Bake 10-12 minutes until crust is charred.",
                "Top with fresh basil and drizzle with olive oil.",
            ]
        ),
        category="Vegetarian",
        area="Italian",
        source_api="seed",
        source_id="seed-001",
        prep_time_min=30,
        cook_time_min=12,
        servings=4,
        difficulty="Medium",
        tags=json.dumps(["vegetarian", "italian", "pizza"]),
        created_by="seed",
    ),
    RecipeTable(
        id="seed-recipe-002",
        title="Chicken Tikka Masala",
        description="Tender chicken in a creamy spiced tomato sauce.",
        instructions=json.dumps(
            [
                "Marinate chicken in yogurt and spices for 2 hours.",
                "Grill or broil chicken until charred.",
                "Saute onions, garlic, and ginger in oil.",
                "Add tomato puree, cream, and spices. Simmer 15 minutes.",
                "Add grilled chicken pieces to sauce.",
                "Garnish with cilantro and serve with basmati rice.",
            ]
        ),
        category="Main Course",
        area="Indian",
        source_api="seed",
        source_id="seed-002",
        prep_time_min=140,
        cook_time_min=30,
        servings=4,
        difficulty="Medium",
        tags=json.dumps(["indian", "chicken", "curry"]),
        created_by="seed",
    ),
    RecipeTable(
        id="seed-recipe-003",
        title="Caesar Salad",
        description="Crisp romaine with homemade Caesar dressing and croutons.",
        instructions=json.dumps(
            [
                "Whisk egg yolk, garlic, anchovy paste, lemon juice, and Dijon.",
                "Slowly drizzle in olive oil while whisking to emulsify.",
                "Stir in grated Parmesan and season with pepper.",
                "Toss chopped romaine with dressing.",
                "Top with croutons and shaved Parmesan.",
            ]
        ),
        category="Salad",
        area="American",
        source_api="seed",
        source_id="seed-003",
        prep_time_min=15,
        cook_time_min=0,
        servings=2,
        difficulty="Easy",
        tags=json.dumps(["salad", "american", "quick"]),
        created_by="seed",
    ),
    RecipeTable(
        id="seed-recipe-004",
        title="Chocolate Lava Cake",
        description="Individual cakes with a molten chocolate center.",
        instructions=json.dumps(
            [
                "Melt dark chocolate and butter together.",
                "Whisk eggs, egg yolks, and sugar until thick.",
                "Fold chocolate mixture into eggs. Sift in flour.",
                "Divide batter among greased ramekins.",
                "Bake at 425F (220C) for 12-14 minutes.",
                "Invert onto plates and serve immediately.",
            ]
        ),
        category="Dessert",
        area="French",
        source_api="seed",
        source_id="seed-004",
        prep_time_min=20,
        cook_time_min=14,
        servings=4,
        difficulty="Hard",
        tags=json.dumps(["dessert", "french", "chocolate"]),
        created_by="seed",
    ),
    RecipeTable(
        id="seed-recipe-005",
        title="Pad Thai",
        description="Stir-fried rice noodles with shrimp, tofu, peanuts, and lime.",
        instructions=json.dumps(
            [
                "Soak rice noodles in warm water for 30 minutes.",
                "Mix tamarind paste, fish sauce, sugar, and lime juice for sauce.",
                "Stir-fry shrimp and tofu in a hot wok.",
                "Add drained noodles and sauce. Toss until coated.",
                "Push noodles aside, scramble eggs in the wok.",
                "Toss everything together. Serve with peanuts, bean sprouts, and lime.",
            ]
        ),
        category="Main Course",
        area="Thai",
        source_api="seed",
        source_id="seed-005",
        prep_time_min=40,
        cook_time_min=10,
        servings=4,
        difficulty="Medium",
        tags=json.dumps(["thai", "noodles", "stir-fry"]),
        created_by="seed",
    ),
]

INGREDIENTS: list[RecipeIngredientTable] = [
    # Margherita Pizza
    RecipeIngredientTable(
        id="seed-ing-001",
        recipe_id="seed-recipe-001",
        name="pizza dough",
        quantity=1,
        unit="ball",
        order_index=0,
    ),
    RecipeIngredientTable(
        id="seed-ing-002",
        recipe_id="seed-recipe-001",
        name="San Marzano tomatoes",
        quantity=400,
        unit="g",
        order_index=1,
    ),
    RecipeIngredientTable(
        id="seed-ing-003",
        recipe_id="seed-recipe-001",
        name="fresh mozzarella",
        quantity=200,
        unit="g",
        order_index=2,
    ),
    RecipeIngredientTable(
        id="seed-ing-004",
        recipe_id="seed-recipe-001",
        name="fresh basil",
        quantity=10,
        unit="leaves",
        order_index=3,
    ),
    RecipeIngredientTable(
        id="seed-ing-005",
        recipe_id="seed-recipe-001",
        name="olive oil",
        quantity=2,
        unit="tbsp",
        order_index=4,
    ),
    # Chicken Tikka Masala
    RecipeIngredientTable(
        id="seed-ing-010",
        recipe_id="seed-recipe-002",
        name="chicken breast",
        quantity=600,
        unit="g",
        order_index=0,
    ),
    RecipeIngredientTable(
        id="seed-ing-011",
        recipe_id="seed-recipe-002",
        name="yogurt",
        quantity=200,
        unit="ml",
        order_index=1,
    ),
    RecipeIngredientTable(
        id="seed-ing-012",
        recipe_id="seed-recipe-002",
        name="heavy cream",
        quantity=200,
        unit="ml",
        order_index=2,
    ),
    RecipeIngredientTable(
        id="seed-ing-013",
        recipe_id="seed-recipe-002",
        name="tomato puree",
        quantity=400,
        unit="g",
        order_index=3,
    ),
    RecipeIngredientTable(
        id="seed-ing-014",
        recipe_id="seed-recipe-002",
        name="garam masala",
        quantity=2,
        unit="tsp",
        order_index=4,
    ),
    # Caesar Salad
    RecipeIngredientTable(
        id="seed-ing-020",
        recipe_id="seed-recipe-003",
        name="romaine lettuce",
        quantity=2,
        unit="heads",
        order_index=0,
    ),
    RecipeIngredientTable(
        id="seed-ing-021",
        recipe_id="seed-recipe-003",
        name="Parmesan cheese",
        quantity=50,
        unit="g",
        order_index=1,
    ),
    RecipeIngredientTable(
        id="seed-ing-022",
        recipe_id="seed-recipe-003",
        name="olive oil",
        quantity=120,
        unit="ml",
        order_index=2,
    ),
    RecipeIngredientTable(
        id="seed-ing-023",
        recipe_id="seed-recipe-003",
        name="anchovy paste",
        quantity=1,
        unit="tsp",
        order_index=3,
    ),
    # Chocolate Lava Cake
    RecipeIngredientTable(
        id="seed-ing-030",
        recipe_id="seed-recipe-004",
        name="dark chocolate",
        quantity=200,
        unit="g",
        order_index=0,
    ),
    RecipeIngredientTable(
        id="seed-ing-031",
        recipe_id="seed-recipe-004",
        name="unsalted butter",
        quantity=100,
        unit="g",
        order_index=1,
    ),
    RecipeIngredientTable(
        id="seed-ing-032",
        recipe_id="seed-recipe-004",
        name="eggs",
        quantity=3,
        unit="whole",
        order_index=2,
    ),
    RecipeIngredientTable(
        id="seed-ing-033",
        recipe_id="seed-recipe-004",
        name="sugar",
        quantity=100,
        unit="g",
        order_index=3,
    ),
    RecipeIngredientTable(
        id="seed-ing-034",
        recipe_id="seed-recipe-004",
        name="all-purpose flour",
        quantity=50,
        unit="g",
        order_index=4,
    ),
    # Pad Thai
    RecipeIngredientTable(
        id="seed-ing-040",
        recipe_id="seed-recipe-005",
        name="rice noodles",
        quantity=250,
        unit="g",
        order_index=0,
    ),
    RecipeIngredientTable(
        id="seed-ing-041",
        recipe_id="seed-recipe-005",
        name="shrimp",
        quantity=200,
        unit="g",
        order_index=1,
    ),
    RecipeIngredientTable(
        id="seed-ing-042",
        recipe_id="seed-recipe-005",
        name="firm tofu",
        quantity=150,
        unit="g",
        order_index=2,
    ),
    RecipeIngredientTable(
        id="seed-ing-043",
        recipe_id="seed-recipe-005",
        name="tamarind paste",
        quantity=3,
        unit="tbsp",
        order_index=3,
    ),
    RecipeIngredientTable(
        id="seed-ing-044",
        recipe_id="seed-recipe-005",
        name="roasted peanuts",
        quantity=50,
        unit="g",
        order_index=4,
    ),
]

USERS = [
    UserProfileTable(
        user_id="demo-user-1",
        display_name="Alex (Vegetarian)",
        dietary_restrictions=json.dumps(["vegetarian"]),
        allergies=json.dumps(["nuts"]),
        preferred_cuisines=json.dumps(["Italian", "American"]),
        default_servings=2,
        unit_system="metric",
    ),
    UserProfileTable(
        user_id="demo-user-2",
        display_name="Jordan",
        dietary_restrictions=json.dumps([]),
        allergies=json.dumps([]),
        preferred_cuisines=json.dumps(["Indian", "Thai"]),
        default_servings=4,
        unit_system="imperial",
    ),
    UserProfileTable(
        user_id="demo-user-3",
        display_name="Sam (Vegan)",
        dietary_restrictions=json.dumps(["vegan"]),
        allergies=json.dumps(["dairy"]),
        preferred_cuisines=json.dumps(["Italian", "Thai"]),
        default_servings=2,
        unit_system="metric",
    ),
]

FAVORITES = [
    FavoriteTable(
        user_id="demo-user-1",
        recipe_id="seed-recipe-001",
        notes="My go-to pizza recipe",
        rating=5,
    ),
    FavoriteTable(
        user_id="demo-user-1",
        recipe_id="seed-recipe-003",
        notes="Quick weeknight dinner",
        rating=4,
    ),
    FavoriteTable(
        user_id="demo-user-2",
        recipe_id="seed-recipe-002",
        notes="Best tikka masala",
        rating=5,
    ),
    FavoriteTable(
        user_id="demo-user-2",
        recipe_id="seed-recipe-005",
        notes="Great pad thai",
        rating=4,
    ),
]

MEAL_PLANS = [
    MealPlanTable(
        id="seed-plan-001",
        user_id="demo-user-1",
        name="Weeknight Dinners",
        start_date="2026-03-23",
        end_date="2026-03-27",
        preferences=json.dumps({"diet": "vegetarian", "servings": 2}),
    ),
]

MEAL_PLAN_ITEMS = [
    MealPlanItemTable(
        id="seed-planitem-001",
        plan_id="seed-plan-001",
        day_date="2026-03-23",
        meal_type="dinner",
        recipe_id="seed-recipe-001",
        servings=2,
    ),
    MealPlanItemTable(
        id="seed-planitem-002",
        plan_id="seed-plan-001",
        day_date="2026-03-24",
        meal_type="dinner",
        recipe_id="seed-recipe-003",
        servings=2,
    ),
    MealPlanItemTable(
        id="seed-planitem-003",
        plan_id="seed-plan-001",
        day_date="2026-03-25",
        meal_type="dinner",
        recipe_id="seed-recipe-001",
        servings=2,
    ),
    MealPlanItemTable(
        id="seed-planitem-004",
        plan_id="seed-plan-001",
        day_date="2026-03-26",
        meal_type="dinner",
        recipe_id="seed-recipe-004",
        servings=2,
    ),
    MealPlanItemTable(
        id="seed-planitem-005",
        plan_id="seed-plan-001",
        day_date="2026-03-27",
        meal_type="dinner",
        custom_meal="Leftover Caesar Salad",
        servings=2,
    ),
]

NUTRITION_CACHE = [
    NutritionCacheTable(
        food_name="chicken breast",
        fdc_id="171077",
        calories=165.0,
        protein_g=31.0,
        fat_g=3.6,
        carbs_g=0.0,
        fiber_g=0.0,
        sugar_g=0.0,
        sodium_mg=74.0,
        source="usda",
    ),
    NutritionCacheTable(
        food_name="olive oil",
        fdc_id="171413",
        calories=884.0,
        protein_g=0.0,
        fat_g=100.0,
        carbs_g=0.0,
        fiber_g=0.0,
        sugar_g=0.0,
        sodium_mg=2.0,
        source="usda",
    ),
    NutritionCacheTable(
        food_name="mozzarella cheese",
        fdc_id="170845",
        calories=280.0,
        protein_g=28.0,
        fat_g=17.0,
        carbs_g=3.1,
        fiber_g=0.0,
        sugar_g=1.0,
        sodium_mg=627.0,
        source="usda",
    ),
    NutritionCacheTable(
        food_name="dark chocolate",
        fdc_id="170272",
        calories=546.0,
        protein_g=5.0,
        fat_g=31.0,
        carbs_g=60.0,
        fiber_g=7.0,
        sugar_g=48.0,
        sodium_mg=24.0,
        source="usda",
    ),
]

ALL_SEED_DATA: Sequence[Sequence[Base]] = [
    RECIPES,
    INGREDIENTS,
    USERS,
    NUTRITION_CACHE,
    MEAL_PLANS,
    MEAL_PLAN_ITEMS,
    FAVORITES,
]


async def seed() -> None:
    """Seed the database with sample data."""
    settings = get_settings()
    engine = await init_engine(settings)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = get_session_factory(engine)

    async with session_factory() as session:
        for group in ALL_SEED_DATA:
            for record in group:
                await session.merge(record)
        await session.commit()

    await engine.dispose()

    total = sum(len(g) for g in ALL_SEED_DATA)
    print(f"Seeded {total} records across {len(ALL_SEED_DATA)} tables.")


def main() -> None:
    """Entry point for the seed script."""
    asyncio.run(seed())


if __name__ == "__main__":
    main()
