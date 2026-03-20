"""SQLAlchemy ORM table definitions matching the SQLite schema."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


def _generate_id() -> str:
    return uuid4().hex


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class RecipeTable(Base):
    __tablename__ = "recipes"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_generate_id)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)  # JSON array
    category: Mapped[str | None] = mapped_column(Text)
    area: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_api: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(Text)
    prep_time_min: Mapped[int | None] = mapped_column(Integer)
    cook_time_min: Mapped[int | None] = mapped_column(Integer)
    servings: Mapped[int] = mapped_column(Integer, default=4)
    difficulty: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(Text)  # JSON array
    created_at: Mapped[str] = mapped_column(Text, default=_utc_now)
    updated_at: Mapped[str] = mapped_column(Text, default=_utc_now, onupdate=_utc_now)
    created_by: Mapped[str | None] = mapped_column(Text)
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    ingredients: Mapped[list[RecipeIngredientTable]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RecipeIngredientTable.order_index",
    )

    __table_args__ = (
        Index("idx_recipes_category", "category"),
        Index("idx_recipes_area", "area"),
        Index("idx_recipes_source", "source_api", "source_id"),
        Index("idx_recipes_deleted", "is_deleted"),
    )


class RecipeIngredientTable(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_generate_id)
    recipe_id: Mapped[str] = mapped_column(
        Text, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float | None] = mapped_column()
    unit: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    recipe: Mapped[RecipeTable] = relationship(back_populates="ingredients")

    __table_args__ = (Index("idx_recipe_ingredients_recipe", "recipe_id"),)


class NutritionCacheTable(Base):
    __tablename__ = "nutrition_cache"

    food_name: Mapped[str] = mapped_column(Text, primary_key=True)
    fdc_id: Mapped[str | None] = mapped_column(Text)
    calories: Mapped[float | None] = mapped_column()
    protein_g: Mapped[float | None] = mapped_column()
    fat_g: Mapped[float | None] = mapped_column()
    carbs_g: Mapped[float | None] = mapped_column()
    fiber_g: Mapped[float | None] = mapped_column()
    sugar_g: Mapped[float | None] = mapped_column()
    sodium_mg: Mapped[float | None] = mapped_column()
    full_nutrients: Mapped[str | None] = mapped_column(Text)  # JSON
    source: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[str] = mapped_column(Text, default=_utc_now)


class UserProfileTable(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    dietary_restrictions: Mapped[str | None] = mapped_column(Text)  # JSON array
    allergies: Mapped[str | None] = mapped_column(Text)  # JSON array
    preferred_cuisines: Mapped[str | None] = mapped_column(Text)  # JSON array
    calorie_target: Mapped[int | None] = mapped_column(Integer)
    default_servings: Mapped[int] = mapped_column(Integer, default=4)
    unit_system: Mapped[str] = mapped_column(
        Text, default="metric", server_default=text("'metric'")
    )
    created_at: Mapped[str] = mapped_column(Text, default=_utc_now)
    updated_at: Mapped[str] = mapped_column(Text, default=_utc_now, onupdate=_utc_now)


class FavoriteTable(Base):
    __tablename__ = "favorites"

    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    recipe_id: Mapped[str] = mapped_column(Text, ForeignKey("recipes.id"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer)
    saved_at: Mapped[str] = mapped_column(Text, default=_utc_now)

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "recipe_id"),
        Index("idx_favorites_user", "user_id"),
    )


class MealPlanTable(Base):
    __tablename__ = "meal_plans"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_generate_id)
    user_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[str] = mapped_column(Text, nullable=False)
    end_date: Mapped[str] = mapped_column(Text, nullable=False)
    preferences: Mapped[str | None] = mapped_column(Text)  # JSON
    day_dates: Mapped[str | None] = mapped_column(Text)  # JSON array of all day dates
    created_at: Mapped[str] = mapped_column(Text, default=_utc_now)

    items: Mapped[list[MealPlanItemTable]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by=lambda: [
            MealPlanItemTable.day_date,
            MealPlanItemTable.meal_type,
            MealPlanItemTable.id,
        ],
    )


class MealPlanItemTable(Base):
    __tablename__ = "meal_plan_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_generate_id)
    plan_id: Mapped[str] = mapped_column(
        Text, ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False
    )
    day_date: Mapped[str] = mapped_column(Text, nullable=False)
    meal_type: Mapped[str] = mapped_column(Text, nullable=False)
    recipe_id: Mapped[str | None] = mapped_column(Text, ForeignKey("recipes.id"))
    custom_meal: Mapped[str | None] = mapped_column(Text)
    servings: Mapped[int] = mapped_column(Integer, default=1)

    plan: Mapped[MealPlanTable] = relationship(back_populates="items")

    __table_args__ = (
        Index("idx_meal_plan_items_plan", "plan_id"),
        Index("idx_meal_plan_items_date", "day_date"),
    )


class AuditLogTable(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_generate_id)
    timestamp: Mapped[str] = mapped_column(Text, default=_utc_now)
    user_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text)
    before_state: Mapped[str | None] = mapped_column(Text)  # JSON
    after_state: Mapped[str | None] = mapped_column(Text)  # JSON
    tool_name: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("idx_audit_log_entity", "entity_type", "entity_id"),
        Index("idx_audit_log_timestamp", "timestamp"),
        Index("idx_audit_log_request", "request_id"),
    )
