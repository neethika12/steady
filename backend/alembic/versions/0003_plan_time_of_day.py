"""Optional time of day for a planned task (NULL = anytime that day).

Non-destructive: adds one nullable column.

Revision ID: 0003_plan_time_of_day
Revises: 0002_inbox_items_become_tasks
Create Date: 2026-10-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_plan_time_of_day"
down_revision = "0002_inbox_items_become_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_plans", sa.Column("planned_time", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("task_plans", "planned_time")
