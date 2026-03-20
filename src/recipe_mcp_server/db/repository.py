"""Repository classes providing async CRUD operations over ORM tables."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from recipe_mcp_server.db.engine import get_session
from recipe_mcp_server.db.tables import (
    AuditLogTable,
    FavoriteTable,
    MealPlanItemTable,
    MealPlanTable,
    RecipeIngredientTable,
    RecipeTable,
    UserProfileTable,
)
from recipe_mcp_server.models import (
    DietaryProfile,
    Favorite,
    Ingredient,
    MealPlan,
    MealPlanItem,
    PaginatedResponse,
    Recipe,
    RecipeCreate,
    RecipeSummary,
    RecipeUpdate,
    UserPreferences,
)
from recipe_mcp_server.models.common import MealType


def _json_dumps(value: list | dict | None) -> str | None:  # type: ignore[type-arg]
    if value is None:
        return None
    return json.dumps(value)


def _json_loads_list(value: str | None) -> list[str]:
    if not value:
        return []
    return json.loads(value)  # type: ignore[no-any-return]


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _recipe_from_row(row: RecipeTable) -> Recipe:
    return Recipe(
        id=row.id,
        title=row.title,
        description=row.description,
        instructions=_json_loads_list(row.instructions),
        category=row.category,
        area=row.area,
        image_url=row.image_url,
        source_url=row.source_url,
        source_api=row.source_api,
        source_id=row.source_id,
        prep_time_min=row.prep_time_min,
        cook_time_min=row.cook_time_min,
        servings=row.servings,
        difficulty=row.difficulty,
        tags=_json_loads_list(row.tags),
        created_at=_parse_datetime(row.created_at),
        updated_at=_parse_datetime(row.updated_at),
        created_by=row.created_by,
        is_deleted=bool(row.is_deleted),
        ingredients=[
            Ingredient(
                name=ing.name,
                quantity=ing.quantity,
                unit=ing.unit,
                notes=ing.notes,
                order_index=ing.order_index,
            )
            for ing in row.ingredients
        ],
    )


def _summary_from_row(row: RecipeTable) -> RecipeSummary:
    return RecipeSummary(
        id=row.id,
        title=row.title,
        category=row.category,
        area=row.area,
        image_url=row.image_url,
        source_api=row.source_api,
        difficulty=row.difficulty,
    )


class RecipeRepo:
    """Repository for recipe CRUD operations with soft delete."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def create(self, data: RecipeCreate) -> Recipe:
        async with get_session(self._factory) as session:
            row = RecipeTable(
                title=data.title,
                description=data.description,
                instructions=_json_dumps(data.instructions),
                category=data.category,
                area=data.area,
                image_url=data.image_url,
                source_url=data.source_url,
                source_api=data.source_api.value if data.source_api else None,
                source_id=data.source_id,
                prep_time_min=data.prep_time_min,
                cook_time_min=data.cook_time_min,
                servings=data.servings,
                difficulty=data.difficulty.value if data.difficulty else None,
                tags=_json_dumps(data.tags),
            )
            for i, ing in enumerate(data.ingredients):
                row.ingredients.append(
                    RecipeIngredientTable(
                        name=ing.name,
                        quantity=ing.quantity,
                        unit=ing.unit,
                        notes=ing.notes,
                        order_index=i,
                    )
                )
            session.add(row)
            await session.flush()
            # Build model from known data to avoid lazy-load issues
            return Recipe(
                id=row.id,
                title=data.title,
                description=data.description,
                instructions=data.instructions,
                category=data.category,
                area=data.area,
                image_url=data.image_url,
                source_url=data.source_url,
                source_api=data.source_api,
                source_id=data.source_id,
                prep_time_min=data.prep_time_min,
                cook_time_min=data.cook_time_min,
                servings=data.servings,
                difficulty=data.difficulty,
                tags=data.tags,
                created_at=_parse_datetime(row.created_at),
                updated_at=_parse_datetime(row.updated_at),
                ingredients=list(data.ingredients),
            )

    async def get(self, recipe_id: str) -> Recipe | None:
        async with get_session(self._factory) as session:
            stmt = (
                select(RecipeTable)
                .options(selectinload(RecipeTable.ingredients))
                .where(RecipeTable.id == recipe_id, RecipeTable.is_deleted == 0)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return _recipe_from_row(row)

    async def update(self, recipe_id: str, data: RecipeUpdate) -> Recipe | None:
        async with get_session(self._factory) as session:
            stmt = (
                select(RecipeTable)
                .options(selectinload(RecipeTable.ingredients))
                .where(RecipeTable.id == recipe_id, RecipeTable.is_deleted == 0)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None

            update_data = data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if field == "instructions" or field == "tags":
                    setattr(row, field, _json_dumps(value))
                elif field == "difficulty":
                    setattr(row, field, value.value if value else None)
                elif field == "ingredients":
                    # Replace all ingredients
                    row.ingredients.clear()
                    for i, ing_data in enumerate(value):
                        ing = (
                            ing_data if isinstance(ing_data, Ingredient) else Ingredient(**ing_data)
                        )
                        row.ingredients.append(
                            RecipeIngredientTable(
                                name=ing.name,
                                quantity=ing.quantity,
                                unit=ing.unit,
                                notes=ing.notes,
                                order_index=i,
                            )
                        )
                else:
                    setattr(row, field, value)

            row.updated_at = _utc_now()
            await session.flush()
            return _recipe_from_row(row)

    async def delete(self, recipe_id: str) -> bool:
        async with get_session(self._factory) as session:
            stmt = select(RecipeTable).where(
                RecipeTable.id == recipe_id, RecipeTable.is_deleted == 0
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return False
            row.is_deleted = 1
            row.updated_at = _utc_now()
            await session.flush()
            return True

    async def list_recipes(
        self, cursor: str | None = None, limit: int = 50
    ) -> PaginatedResponse[RecipeSummary]:
        async with get_session(self._factory) as session:
            stmt = (
                select(RecipeTable)
                .where(RecipeTable.is_deleted == 0)
                .order_by(RecipeTable.created_at.desc(), RecipeTable.id)
            )
            if cursor:
                stmt = stmt.where(RecipeTable.id > cursor)
            stmt = stmt.limit(limit + 1)

            rows = list((await session.execute(stmt)).scalars().all())
            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            # Get total count
            count_stmt = select(RecipeTable).where(RecipeTable.is_deleted == 0)
            total = len((await session.execute(count_stmt)).scalars().all())

            items = [_summary_from_row(r) for r in rows]
            next_cursor = rows[-1].id if has_more else None
            return PaginatedResponse(items=items, total=total, next_cursor=next_cursor)

    async def search(
        self, query: str, cuisine: str | None = None, limit: int = 20
    ) -> list[RecipeSummary]:
        async with get_session(self._factory) as session:
            stmt = select(RecipeTable).where(RecipeTable.is_deleted == 0)
            pattern = f"%{query}%"
            stmt = stmt.where(
                RecipeTable.title.ilike(pattern)
                | RecipeTable.category.ilike(pattern)
                | RecipeTable.tags.ilike(pattern)
            )
            if cuisine:
                stmt = stmt.where(RecipeTable.area.ilike(f"%{cuisine}%"))
            stmt = stmt.limit(limit)

            rows = (await session.execute(stmt)).scalars().all()
            return [_summary_from_row(r) for r in rows]


class UserRepo:
    """Repository for user profile operations."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def get_or_create(self, user_id: str) -> UserPreferences:
        async with get_session(self._factory) as session:
            stmt = select(UserProfileTable).where(UserProfileTable.user_id == user_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                row = UserProfileTable(user_id=user_id)
                session.add(row)
                await session.flush()
            return self._to_model(row)

    async def update(self, user_id: str, data: dict) -> UserPreferences | None:  # type: ignore[type-arg]
        async with get_session(self._factory) as session:
            stmt = select(UserProfileTable).where(UserProfileTable.user_id == user_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None

            for field, value in data.items():
                if field == "dietary_profile":
                    profile = (
                        value if isinstance(value, DietaryProfile) else DietaryProfile(**value)
                    )
                    row.dietary_restrictions = _json_dumps(profile.dietary_restrictions)
                    row.allergies = _json_dumps(profile.allergies)
                    row.preferred_cuisines = _json_dumps(profile.preferred_cuisines)
                elif field in ("dietary_restrictions", "allergies", "preferred_cuisines"):
                    setattr(row, field, _json_dumps(value))
                else:
                    setattr(row, field, value)

            row.updated_at = _utc_now()
            await session.flush()
            return self._to_model(row)

    @staticmethod
    def _to_model(row: UserProfileTable) -> UserPreferences:
        return UserPreferences(
            user_id=row.user_id,
            display_name=row.display_name,
            dietary_profile=DietaryProfile(
                dietary_restrictions=_json_loads_list(row.dietary_restrictions),
                allergies=_json_loads_list(row.allergies),
                preferred_cuisines=_json_loads_list(row.preferred_cuisines),
            ),
            default_servings=row.default_servings,
            unit_system=row.unit_system,
            created_at=_parse_datetime(row.created_at),
            updated_at=_parse_datetime(row.updated_at),
        )


class FavoriteRepo:
    """Repository for user favorites (saved recipes)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def save(
        self,
        user_id: str,
        recipe_id: str,
        rating: int | None = None,
        notes: str | None = None,
    ) -> Favorite:
        async with get_session(self._factory) as session:
            stmt = select(FavoriteTable).where(
                FavoriteTable.user_id == user_id, FavoriteTable.recipe_id == recipe_id
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                row = FavoriteTable(
                    user_id=user_id,
                    recipe_id=recipe_id,
                    rating=rating,
                    notes=notes,
                )
                session.add(row)
            else:
                if rating is not None:
                    row.rating = rating
                if notes is not None:
                    row.notes = notes
            await session.flush()
            return Favorite(
                user_id=row.user_id,
                recipe_id=row.recipe_id,
                notes=row.notes,
                rating=row.rating,
                saved_at=_parse_datetime(row.saved_at),
            )

    async def list_for_user(self, user_id: str) -> list[Favorite]:
        async with get_session(self._factory) as session:
            stmt = (
                select(FavoriteTable)
                .where(FavoriteTable.user_id == user_id)
                .order_by(FavoriteTable.saved_at.desc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                Favorite(
                    user_id=r.user_id,
                    recipe_id=r.recipe_id,
                    notes=r.notes,
                    rating=r.rating,
                    saved_at=_parse_datetime(r.saved_at),
                )
                for r in rows
            ]

    async def remove(self, user_id: str, recipe_id: str) -> bool:
        async with get_session(self._factory) as session:
            stmt = select(FavoriteTable).where(
                FavoriteTable.user_id == user_id, FavoriteTable.recipe_id == recipe_id
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.flush()
            return True


class MealPlanRepo:
    """Repository for meal plan operations."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def create(self, plan: MealPlan) -> MealPlan:
        async with get_session(self._factory) as session:
            row = MealPlanTable(
                user_id=plan.user_id,
                name=plan.name,
                start_date=plan.start_date,
                end_date=plan.end_date,
                preferences=_json_dumps(plan.preferences),
            )
            for day in plan.days:
                for meal in day.meals:
                    row.items.append(
                        MealPlanItemTable(
                            day_date=meal.day_date,
                            meal_type=meal.meal_type.value,
                            recipe_id=meal.recipe_id,
                            custom_meal=meal.custom_meal,
                            servings=meal.servings,
                        )
                    )
            session.add(row)
            await session.flush()
            # Build model from input data to avoid lazy-load issues
            return MealPlan(
                id=row.id,
                user_id=plan.user_id,
                name=plan.name,
                start_date=plan.start_date,
                end_date=plan.end_date,
                preferences=plan.preferences,
                days=plan.days,
                created_at=_parse_datetime(row.created_at),
            )

    async def get(self, plan_id: str) -> MealPlan | None:
        async with get_session(self._factory) as session:
            stmt = (
                select(MealPlanTable)
                .options(selectinload(MealPlanTable.items))
                .where(MealPlanTable.id == plan_id)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return self._to_model(row)

    async def list_for_user(self, user_id: str) -> list[MealPlan]:
        async with get_session(self._factory) as session:
            stmt = (
                select(MealPlanTable)
                .options(selectinload(MealPlanTable.items))
                .where(MealPlanTable.user_id == user_id)
                .order_by(MealPlanTable.created_at.desc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_model(r) for r in rows]

    @staticmethod
    def _to_model(row: MealPlanTable) -> MealPlan:
        items_by_date: dict[str, list[MealPlanItem]] = {}
        for item in row.items:
            meal = MealPlanItem(
                id=item.id,
                day_date=item.day_date,
                meal_type=MealType(item.meal_type),
                recipe_id=item.recipe_id,
                custom_meal=item.custom_meal,
                servings=item.servings,
            )
            items_by_date.setdefault(item.day_date, []).append(meal)

        from recipe_mcp_server.models.meal_plan import DayPlan

        days = [DayPlan(date=date, meals=meals) for date, meals in sorted(items_by_date.items())]

        prefs_raw = row.preferences
        preferences = json.loads(prefs_raw) if prefs_raw else None

        return MealPlan(
            id=row.id,
            user_id=row.user_id,
            name=row.name,
            start_date=row.start_date,
            end_date=row.end_date,
            preferences=preferences,
            days=days,
            created_at=_parse_datetime(row.created_at),
        )


class AuditRepo:
    """Repository for immutable audit log entries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        before_state: dict | None = None,  # type: ignore[type-arg]
        after_state: dict | None = None,  # type: ignore[type-arg]
        tool_name: str | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        async with get_session(self._factory) as session:
            row = AuditLogTable(
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before_state=_json_dumps(before_state),
                after_state=_json_dumps(after_state),
                tool_name=tool_name,
                request_id=request_id,
            )
            session.add(row)
            await session.flush()
