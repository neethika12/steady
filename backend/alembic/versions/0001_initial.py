"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("timezone_confirmed", sa.Boolean(), nullable=False),
        sa.Column("week_start", sa.Integer(), nullable=False),
        *_ts(),
        sa.CheckConstraint("id = 1", name="ck_app_settings_single_row"),
        sa.CheckConstraint("week_start BETWEEN 0 AND 6", name="ck_app_settings_week_start"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "inbox_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("converted_to_type", sa.String(16), nullable=True),
        sa.Column("converted_to_id", sa.Uuid(), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_ts(),
        sa.CheckConstraint("status IN ('open', 'archived', 'converted')", name="ck_inbox_items_status"),
        sa.CheckConstraint(
            "converted_to_type IS NULL OR converted_to_type IN ('task', 'tasks', 'habit', 'journal')",
            name="ck_inbox_items_converted_to_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbox_items_status", "inbox_items", ["status"])
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(8), nullable=False),
        sa.Column("category", sa.String(60), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("actual_minutes", sa.Integer(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_task_id", sa.Uuid(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("source_inbox_item_id", sa.Uuid(), sa.ForeignKey("inbox_items.id"), nullable=True),
        *_ts(),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high')", name="ck_tasks_priority"),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled', 'split')", name="ck_tasks_status"
        ),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0", name="ck_tasks_estimated_minutes"
        ),
        sa.CheckConstraint("actual_minutes IS NULL OR actual_minutes >= 0", name="ck_tasks_actual_minutes"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_planned_date", "tasks", ["planned_date"])
    op.create_table(
        "task_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("reason", sa.String(24), nullable=True),
        sa.Column("reason_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up", sa.String(16), nullable=True),
        sa.Column("carried_from_plan_id", sa.Uuid(), sa.ForeignKey("task_plans.id"), nullable=True),
        *_ts(),
        sa.UniqueConstraint("task_id", "plan_date", name="uq_task_plans_task_date"),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('completed', 'partial', 'not_completed', 'cancelled')",
            name="ck_task_plans_outcome",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ('not_enough_time', 'too_large', 'unclear_next_step', "
            "'waiting', 'low_energy', 'priority_changed', 'forgot_distracted', 'other')",
            name="ck_task_plans_reason",
        ),
        sa.CheckConstraint(
            "follow_up IS NULL OR follow_up IN ('rescheduled', 'split', 'unscheduled', 'cancelled')",
            name="ck_task_plans_follow_up",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_plans_plan_date", "task_plans", ["plan_date"])
    op.create_table(
        "habits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("archived_on", sa.Date(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_inbox_item_id", sa.Uuid(), sa.ForeignKey("inbox_items.id"), nullable=True),
        *_ts(),
        sa.CheckConstraint("kind IN ('boolean', 'duration', 'count')", name="ck_habits_kind"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "habit_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("habit_id", sa.Uuid(), sa.ForeignKey("habits.id"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("schedule_type", sa.String(16), nullable=False),
        sa.Column("weekdays", sa.JSON(), nullable=False),
        sa.Column("weekly_target", sa.Integer(), nullable=True),
        sa.Column("target_value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("habit_id", "effective_from", name="uq_habit_schedules_habit_from"),
        sa.CheckConstraint(
            "schedule_type IN ('daily', 'weekdays', 'weekly_target')", name="ck_habit_schedules_type"
        ),
        sa.CheckConstraint("target_value >= 1", name="ck_habit_schedules_target_value"),
        sa.CheckConstraint(
            "weekly_target IS NULL OR weekly_target BETWEEN 1 AND 7",
            name="ck_habit_schedules_weekly_target",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "habit_pauses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("habit_id", sa.Uuid(), sa.ForeignKey("habits.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "habit_checkins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("habit_id", sa.Uuid(), sa.ForeignKey("habits.id"), nullable=False),
        sa.Column("checkin_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        *_ts(),
        sa.UniqueConstraint("habit_id", "checkin_date", name="uq_habit_checkins_habit_date"),
        sa.CheckConstraint("value >= 0", name="ck_habit_checkins_value"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("mood", sa.Integer(), nullable=True),
        sa.Column("energy", sa.Integer(), nullable=True),
        sa.Column("went_well", sa.Text(), nullable=False),
        sa.Column("was_difficult", sa.Text(), nullable=False),
        sa.Column("on_mind", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_ts(),
        sa.UniqueConstraint("entry_date", name="uq_journal_entries_entry_date"),
        sa.CheckConstraint("mood IS NULL OR mood BETWEEN 1 AND 5", name="ck_journal_entries_mood"),
        sa.CheckConstraint("energy IS NULL OR energy BETWEEN 1 AND 5", name="ck_journal_entries_energy"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(24), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])


def downgrade() -> None:
    # Destructive: drops every table and all personal data. Never run automatically.
    for table in (
        "audit_log",
        "journal_entries",
        "habit_checkins",
        "habit_pauses",
        "habit_schedules",
        "habits",
        "task_plans",
        "tasks",
        "inbox_items",
        "app_settings",
    ):
        op.drop_table(table)
