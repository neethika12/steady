"""Database tables.

Key idea: a *task* (what needs doing) is stored separately from its *task plans*
(one row per calendar day the task was planned for, with that day's outcome).
Carrying a task forward adds a new plan row and never edits the old one, so
Monday can stay "not completed" while Tuesday records the completion.
"""

import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import (
    text,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Time,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

PRIORITIES = ("low", "medium", "high")
TASK_STATUSES = ("active", "completed", "cancelled", "split")
PLAN_OUTCOMES = ("completed", "partial", "not_completed", "cancelled")
REVIEW_OUTCOMES = ("completed", "partial", "not_completed")
REASONS = (
    "not_enough_time",
    "too_large",
    "unclear_next_step",
    "waiting",
    "low_energy",
    "priority_changed",
    "forgot_distracted",
    "other",
)
REASON_LABELS = {
    "not_enough_time": "Not enough time",
    "too_large": "Task was too large",
    "unclear_next_step": "Unclear next step",
    "waiting": "Waiting on something",
    "low_energy": "Low energy",
    "priority_changed": "Priority changed",
    "forgot_distracted": "Forgot or got distracted",
    "other": "Other",
}
FOLLOW_UPS = ("rescheduled", "split", "unscheduled", "cancelled", "left")
TASK_ORIGINS = ("inbox", "day")
INBOX_STATUSES = ("open", "archived", "converted")
INBOX_TARGETS = ("task", "tasks", "habit", "journal")
HABIT_KINDS = ("boolean", "duration", "count")
SCHEDULE_TYPES = ("daily", "weekdays", "weekly_target")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# The signed-in user for the current transaction (set by app.db for every transaction). Every data
# row defaults to it, and row-level security (migration 0010) hides and refuses rows of other users.
CURRENT_USER = text("NULLIF(current_setting('app.user_id', true), '')::uuid")


class User(Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(254))  # stored lower-case; empty only for the placeholder owner
    name: Mapped[str | None] = mapped_column(String(80))  # empty for accounts made before names were asked
    password_hash: Mapped[str | None] = mapped_column(String(255))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Timestamps, Base):
    """A signed-in browser. Only a hash of the cookie value is stored."""

    __tablename__ = "auth_sessions"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthAttempt(Base):
    """One failed log-in (or any sign-up) attempt, for rate limiting. No passwords are stored."""

    __tablename__ = "auth_attempts"
    __table_args__ = (Index("ix_auth_attempts_key_created", "key", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Owned:
    """Every data row belongs to one user. Filled in by the database; never set by app code."""

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), server_default=CURRENT_USER, index=True)


class AppSettings(Timestamps, Base):
    """One row of preferences per user."""

    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("week_start BETWEEN 0 AND 6", name="ck_app_settings_week_start"),
        CheckConstraint("timeline_start <> timeline_end", name="ck_app_settings_timeline"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, server_default=CURRENT_USER)
    timezone: Mapped[str] = mapped_column(String(64))
    timezone_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    week_start: Mapped[int] = mapped_column(Integer, default=0)  # 0 = Monday ... 6 = Sunday
    # The hours shown on the Day timeline. If the end is earlier than the start (e.g. 11:00-02:00)
    # the user's day runs past midnight: until timeline_end it still counts as the previous day.
    timeline_start: Mapped[time] = mapped_column(Time, default=time(7, 0))
    timeline_end: Mapped[time] = mapped_column(Time, default=time(22, 0))
    currency: Mapped[str] = mapped_column(String(3), default="USD")  # ISO 4217 code, for display only


class InboxItem(Owned, Timestamps, Base):
    __tablename__ = "inbox_items"
    __table_args__ = (
        CheckConstraint(_in("status", INBOX_STATUSES), name="ck_inbox_items_status"),
        CheckConstraint(
            "converted_to_type IS NULL OR " + _in("converted_to_type", INBOX_TARGETS),
            name="ck_inbox_items_converted_to_type",
        ),
        Index("ix_inbox_items_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    # What the item was turned into. The original text above is never changed by a conversion.
    converted_to_type: Mapped[str | None] = mapped_column(String(16))
    converted_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Task(Owned, Timestamps, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(_in("priority", PRIORITIES), name="ck_tasks_priority"),
        CheckConstraint(_in("status", TASK_STATUSES), name="ck_tasks_status"),
        CheckConstraint(_in("origin", TASK_ORIGINS), name="ck_tasks_origin"),
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0", name="ck_tasks_estimated_minutes"
        ),
        CheckConstraint(
            "actual_minutes IS NULL OR actual_minutes >= 0", name="ck_tasks_actual_minutes"
        ),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_planned_date", "planned_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(8), default="medium")
    category: Mapped[str | None] = mapped_column(String(60))
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    deadline: Mapped[date | None] = mapped_column(Date)
    # The day the task is currently planned for (it has an open plan row on that day),
    # or NULL when the task is unscheduled.
    planned_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="active")
    # Where the task was created (or explicitly moved): "inbox" or directly on a "day".
    # Unfinished Inbox tasks return to the Inbox; unfinished day tasks stay on their day.
    origin: Mapped[str] = mapped_column(String(8), default="inbox")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"))
    source_inbox_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inbox_items.id"))

    plans: Mapped[list["TaskPlan"]] = relationship(
        back_populates="task", order_by="TaskPlan.plan_date"
    )


class TaskPlan(Owned, Timestamps, Base):
    """One task planned for one calendar day, plus what happened on that day."""

    __tablename__ = "task_plans"
    __table_args__ = (
        UniqueConstraint("task_id", "plan_date", name="uq_task_plans_task_date"),
        CheckConstraint(
            "outcome IS NULL OR " + _in("outcome", PLAN_OUTCOMES), name="ck_task_plans_outcome"
        ),
        CheckConstraint(
            "reason IS NULL OR " + _in("reason", REASONS), name="ck_task_plans_reason"
        ),
        CheckConstraint(
            "follow_up IS NULL OR " + _in("follow_up", FOLLOW_UPS), name="ck_task_plans_follow_up"
        ),
        CheckConstraint(
            "planned_end_time IS NULL OR (planned_time IS NOT NULL AND planned_end_time <> planned_time)",
            name="ck_task_plans_time_range",
        ),
        Index("ix_task_plans_plan_date", "plan_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"))
    plan_date: Mapped[date] = mapped_column(Date)
    # Local time of day the task is planned for; NULL = anytime that day.
    planned_time: Mapped[time | None] = mapped_column(Time)
    # Optional end of a time range (same day, after planned_time); NULL = no end given.
    planned_end_time: Mapped[time | None] = mapped_column(Time)
    # NULL = not reviewed yet. This is deliberately different from 'not_completed'.
    outcome: Mapped[str | None] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(24))
    reason_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The real moment the task was marked completed (may be later than plan_date).
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What the user chose to do after an unfinished review.
    follow_up: Mapped[str | None] = mapped_column(String(16))
    # The earlier plan this one continues. Set when a task is carried forward.
    carried_from_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("task_plans.id"))

    task: Mapped[Task] = relationship(back_populates="plans")


class Habit(Owned, Timestamps, Base):
    __tablename__ = "habits"
    __table_args__ = (CheckConstraint(_in("kind", HABIT_KINDS), name="ck_habits_kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(12))  # boolean | duration (minutes) | count
    unit: Mapped[str | None] = mapped_column(String(30))  # label for count habits, e.g. "glasses"
    start_date: Mapped[date] = mapped_column(Date)  # days before this are never "missed"
    archived_on: Mapped[date | None] = mapped_column(Date)  # local date; days from here on are inactive
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_inbox_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inbox_items.id"))

    schedules: Mapped[list["HabitSchedule"]] = relationship(
        back_populates="habit", order_by="HabitSchedule.effective_from"
    )
    pauses: Mapped[list["HabitPause"]] = relationship(
        back_populates="habit", order_by="HabitPause.start_date"
    )
    checkins: Mapped[list["HabitCheckin"]] = relationship(back_populates="habit")


class HabitSchedule(Owned, Base):
    """A version of a habit's schedule, valid for a date range.

    Changing a schedule closes the current version and adds a new one, so past
    days keep being judged by the schedule that applied at the time.
    """

    __tablename__ = "habit_schedules"
    __table_args__ = (
        UniqueConstraint("habit_id", "effective_from", name="uq_habit_schedules_habit_from"),
        CheckConstraint(_in("schedule_type", SCHEDULE_TYPES), name="ck_habit_schedules_type"),
        CheckConstraint("target_value >= 1", name="ck_habit_schedules_target_value"),
        CheckConstraint(
            "weekly_target IS NULL OR weekly_target BETWEEN 1 AND 7",
            name="ck_habit_schedules_weekly_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    habit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("habits.id"))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)  # inclusive; NULL = still current
    schedule_type: Mapped[str] = mapped_column(String(16))
    weekdays: Mapped[list[int]] = mapped_column(JSON, default=list)  # 0 = Monday ... 6 = Sunday
    weekly_target: Mapped[int | None] = mapped_column(Integer)  # sessions per week
    target_value: Mapped[int] = mapped_column(Integer, default=1)  # minutes or count per day
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    habit: Mapped[Habit] = relationship(back_populates="schedules")


class HabitPause(Owned, Base):
    __tablename__ = "habit_pauses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    habit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("habits.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)  # inclusive; NULL = paused until resumed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    habit: Mapped[Habit] = relationship(back_populates="pauses")


class HabitCheckin(Owned, Timestamps, Base):
    __tablename__ = "habit_checkins"
    __table_args__ = (
        # One check-in per habit per day: repeated submissions update, never double-count.
        UniqueConstraint("habit_id", "checkin_date", name="uq_habit_checkins_habit_date"),
        CheckConstraint("value >= 0", name="ck_habit_checkins_value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    habit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("habits.id"))
    checkin_date: Mapped[date] = mapped_column(Date)
    value: Mapped[int] = mapped_column(Integer)  # 1 for yes/no, else minutes or count

    habit: Mapped[Habit] = relationship(back_populates="checkins")


class JournalEntry(Owned, Timestamps, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "entry_date", name="uq_journal_entries_user_date"),
        CheckConstraint("mood IS NULL OR mood BETWEEN 1 AND 5", name="ck_journal_entries_mood"),
        CheckConstraint(
            "energy IS NULL OR energy BETWEEN 1 AND 5", name="ck_journal_entries_energy"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entry_date: Mapped[date] = mapped_column(Date)
    body: Mapped[str] = mapped_column(Text, default="")
    mood: Mapped[int | None] = mapped_column(Integer)
    energy: Mapped[int | None] = mapped_column(Integer)
    went_well: Mapped[str] = mapped_column(Text, default="")
    was_difficult: Mapped[str] = mapped_column(Text, default="")
    on_mind: Mapped[str] = mapped_column(Text, default="")
    # Increases by one on every save; used to detect conflicting edits.
    version: Mapped[int] = mapped_column(Integer, default=1)


class AuditLog(Owned, Base):
    """Append-only record of changes to history (reviews, corrections, moves)."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(24))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(32))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- money

class FinanceAccount(Owned, Timestamps, Base):
    """A debit account (money you have) or a credit card (money you owe).

    The balance is never stored: it is the opening balance plus every transaction on or
    after ``opened_on``, so it can't drift out of step with the transaction list.
    """

    __tablename__ = "finance_accounts"
    __table_args__ = (CheckConstraint("type IN ('debit', 'credit')", name="ck_finance_accounts_type"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(60))
    type: Mapped[str] = mapped_column(String(8))
    # debit: money in the account; credit: amount owed. As of ``opened_on``.
    opening_balance_cents: Mapped[int] = mapped_column(BigInteger)
    opened_on: Mapped[date] = mapped_column(Date)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FinanceCategory(Owned, Timestamps, Base):
    __tablename__ = "finance_categories"
    __table_args__ = (CheckConstraint("kind IN ('expense', 'income')", name="ck_finance_categories_kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(8))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FinanceTransaction(Owned, Timestamps, Base):
    """expense: money spent from an account (debit balance down / credit owed up)
    income:  money into a debit account
    payment: paying a credit card from a debit account (both balances go down)"""

    __tablename__ = "finance_transactions"
    __table_args__ = (
        CheckConstraint("kind IN ('expense', 'income', 'payment')", name="ck_finance_transactions_kind"),
        CheckConstraint("amount_cents > 0", name="ck_finance_transactions_amount"),
        CheckConstraint(
            "(kind = 'payment' AND to_account_id IS NOT NULL AND category_id IS NULL) OR "
            "(kind <> 'payment' AND to_account_id IS NULL AND category_id IS NOT NULL)",
            name="ck_finance_transactions_shape",
        ),
        Index("ix_finance_transactions_occurred_on", "occurred_on"),
        UniqueConstraint("recurring_id", "occurred_on", name="uq_finance_transactions_recurring_day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    occurred_on: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(8))
    amount_cents: Mapped[int] = mapped_column(BigInteger)  # always positive; whole cents, never floats
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("finance_accounts.id"))
    to_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("finance_accounts.id"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("finance_categories.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    # Set when a repeating rule added this entry; one entry per rule per day.
    recurring_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("finance_recurring.id", ondelete="SET NULL"))


class FinanceRecurring(Owned, Timestamps, Base):
    """A repeating entry: a bill, subscription, salary or card payment that happens on a schedule.

    Occurrence n (from 0) falls on ``anchor_on`` + n * interval weeks/months/years; a monthly
    rule anchored on the 31st lands on the last day of shorter months. ``posted_count`` is how
    many occurrences have been added as entries, so deleting an added entry never brings it back.
    Changing the schedule re-anchors it (``anchor_on`` = the next date, ``posted_count`` = 0).
    """

    __tablename__ = "finance_recurring"
    __table_args__ = (
        CheckConstraint("kind IN ('expense', 'income', 'payment')", name="ck_finance_recurring_kind"),
        CheckConstraint("amount_cents > 0", name="ck_finance_recurring_amount"),
        CheckConstraint("frequency IN ('weekly', 'monthly', 'yearly')", name="ck_finance_recurring_frequency"),
        CheckConstraint("interval BETWEEN 1 AND 12", name="ck_finance_recurring_interval"),
        CheckConstraint("posted_count >= 0", name="ck_finance_recurring_posted"),
        CheckConstraint(
            "(kind = 'payment' AND to_account_id IS NOT NULL AND category_id IS NULL) OR "
            "(kind <> 'payment' AND to_account_id IS NULL AND category_id IS NOT NULL)",
            name="ck_finance_recurring_shape",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(8))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("finance_accounts.id"))
    to_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("finance_accounts.id"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("finance_categories.id"))
    frequency: Mapped[str] = mapped_column(String(8))
    interval: Mapped[int] = mapped_column(Integer, default=1)
    anchor_on: Mapped[date] = mapped_column(Date)
    posted_count: Mapped[int] = mapped_column(Integer, default=0)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))



class FinanceSplitwise(Timestamps, Base):
    """Your Splitwise totals, copied by hand from the Splitwise app. One row per user."""

    __tablename__ = "finance_splitwise"
    __table_args__ = (CheckConstraint("get_cents >= 0 AND pay_cents >= 0", name="ck_finance_splitwise_amounts"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, server_default=CURRENT_USER)
    get_cents: Mapped[int] = mapped_column(BigInteger, default=0)  # you should get (others owe you)
    pay_cents: Mapped[int] = mapped_column(BigInteger, default=0)  # you should pay (you owe others)
