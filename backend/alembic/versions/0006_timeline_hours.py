"""Personal timeline hours (e.g. 11:00 to 02:00 for night owls).

Adds the user's timeline start/end to settings (defaults 07:00-22:00, same as before).
When the end is earlier than the start the day runs past midnight, so a planned time
range may also run past midnight: the time-range check now only requires end != start;
the app checks the rest against the user's timeline. Non-destructive.

Revision ID: 0006_timeline_hours
Revises: 0005_plan_end_time
Create Date: 2026-10-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_timeline_hours"
down_revision = "0005_plan_end_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("timeline_start", sa.Time(), nullable=False, server_default="07:00"))
    op.add_column("app_settings", sa.Column("timeline_end", sa.Time(), nullable=False, server_default="22:00"))
    op.alter_column("app_settings", "timeline_start", server_default=None)
    op.alter_column("app_settings", "timeline_end", server_default=None)
    op.create_check_constraint("ck_app_settings_timeline", "app_settings", "timeline_start <> timeline_end")
    op.drop_constraint("ck_task_plans_time_range", "task_plans", type_="check")
    op.create_check_constraint(
        "ck_task_plans_time_range", "task_plans",
        "planned_end_time IS NULL OR (planned_time IS NOT NULL AND planned_end_time <> planned_time)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_task_plans_time_range", "task_plans", type_="check")
    op.execute("UPDATE task_plans SET planned_end_time = NULL WHERE planned_end_time < planned_time")
    op.create_check_constraint(
        "ck_task_plans_time_range", "task_plans",
        "planned_end_time IS NULL OR (planned_time IS NOT NULL AND planned_end_time > planned_time)",
    )
    op.drop_constraint("ck_app_settings_timeline", "app_settings", type_="check")
    op.drop_column("app_settings", "timeline_end")
    op.drop_column("app_settings", "timeline_start")
