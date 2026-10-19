"""Optional end time, so a planned task can cover a time range (e.g. 09:00-10:30).

Non-destructive: adds one nullable column and a check that an end time needs a start
time and comes after it (same day).

Revision ID: 0005_plan_end_time
Revises: 0004_task_origin
Create Date: 2026-10-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_plan_end_time"
down_revision = "0004_task_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_plans", sa.Column("planned_end_time", sa.Time(), nullable=True))
    op.create_check_constraint(
        "ck_task_plans_time_range", "task_plans",
        "planned_end_time IS NULL OR (planned_time IS NOT NULL AND planned_end_time > planned_time)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_task_plans_time_range", "task_plans", type_="check")
    op.drop_column("task_plans", "planned_end_time")
