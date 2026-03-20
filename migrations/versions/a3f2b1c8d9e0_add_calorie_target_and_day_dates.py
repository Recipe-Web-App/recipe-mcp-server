"""add calorie_target to user_profiles and day_dates to meal_plans

Revision ID: a3f2b1c8d9e0
Revises: 89c5e1acdef7
Create Date: 2026-03-20 05:57:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f2b1c8d9e0"
down_revision: str | None = "89c5e1acdef7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("calorie_target", sa.Integer(), nullable=True))
    op.add_column("meal_plans", sa.Column("day_dates", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("meal_plans", "day_dates")
    op.drop_column("user_profiles", "calorie_target")
