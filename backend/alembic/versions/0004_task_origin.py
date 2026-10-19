"""Remember where a task was created: in the Inbox or directly on a day.

Unfinished Inbox tasks go back to the Inbox automatically; unfinished day tasks stay
on their day and the user chooses what happens. Also allows the follow-up "left"
("leave it on that day"). Non-destructive.

Backfill: a task whose first day record was created together with the task (within
5 seconds) was created on a day; everything else (including tasks made from old
Inbox items) came from the Inbox.

Revision ID: 0004_task_origin
Revises: 0003_plan_time_of_day
Create Date: 2026-10-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_task_origin"
down_revision = "0003_plan_time_of_day"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("origin", sa.String(8), nullable=False, server_default="inbox"))
    op.execute("""
        UPDATE tasks t SET origin = 'day'
        WHERE t.source_inbox_item_id IS NULL
          AND EXISTS (SELECT 1 FROM task_plans p
                      WHERE p.task_id = t.id AND p.created_at <= t.created_at + interval '5 seconds')
    """)
    op.alter_column("tasks", "origin", server_default=None)
    op.create_check_constraint("ck_tasks_origin", "tasks", "origin IN ('inbox', 'day')")
    op.drop_constraint("ck_task_plans_follow_up", "task_plans", type_="check")
    op.create_check_constraint(
        "ck_task_plans_follow_up", "task_plans",
        "follow_up IS NULL OR follow_up IN ('rescheduled', 'split', 'unscheduled', 'cancelled', 'left')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_task_plans_follow_up", "task_plans", type_="check")
    op.execute("UPDATE task_plans SET follow_up = 'unscheduled' WHERE follow_up = 'left'")
    op.create_check_constraint(
        "ck_task_plans_follow_up", "task_plans",
        "follow_up IS NULL OR follow_up IN ('rescheduled', 'split', 'unscheduled', 'cancelled')",
    )
    op.drop_constraint("ck_tasks_origin", "tasks", type_="check")
    op.drop_column("tasks", "origin")
