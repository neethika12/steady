"""JSON export and import.

Duplicate-handling policy for import (also in the README):

* Records are matched by their ``id``. A record whose id already exists is
  **skipped**; existing data is never overwritten or deleted by an import.
* Records that would break a uniqueness rule are skipped and reported as
  conflicts: a journal entry for a date that already has one, a habit check-in
  for a habit+date that already has one, a task plan for a task+date that exists.
* References must resolve (to the file or the database), otherwise the whole
  import is rejected and nothing is written.
* Settings in the file are reported but not applied.
* The import runs in one transaction: it is applied completely or not at all.
"""

from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AppSettings, AuditLog, FinanceAccount, FinanceCategory, FinanceRecurring, FinanceSplitwise, FinanceTransaction, Habit, HabitCheckin,
    HabitPause, HabitSchedule, InboxItem, JournalEntry, Task, TaskPlan, utcnow,
)
from app.errors import invalid
import uuid

FORMAT = "steady-export"
VERSION = 1


class _Base(BaseModel):
    model_config = {"extra": "forbid"}


class InboxRow(_Base):
    id: uuid.UUID
    text: str = Field(min_length=1, max_length=5000)
    status: Literal["open", "archived", "converted"]
    converted_to_type: Literal["task", "tasks", "habit", "journal"] | None = None
    converted_to_id: uuid.UUID | None = None
    converted_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TaskRow(_Base):
    id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    priority: Literal["low", "medium", "high"]
    category: str | None = Field(default=None, max_length=60)
    estimated_minutes: int | None = Field(default=None, ge=1)
    actual_minutes: int | None = Field(default=None, ge=0)
    deadline: date | None = None
    planned_date: date | None = None
    status: Literal["active", "completed", "cancelled", "split"]
    origin: Literal["inbox", "day"] = "inbox"
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    archived_at: datetime | None = None
    parent_task_id: uuid.UUID | None = None
    source_inbox_item_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class PlanRow(_Base):
    id: uuid.UUID
    task_id: uuid.UUID
    plan_date: date
    planned_time: time | None = None
    planned_end_time: time | None = None
    outcome: Literal["completed", "partial", "not_completed", "cancelled"] | None = None
    reason: Literal["not_enough_time", "too_large", "unclear_next_step", "waiting", "low_energy",
                    "priority_changed", "forgot_distracted", "other"] | None = None
    reason_note: str | None = None
    reviewed_at: datetime | None = None
    completed_at: datetime | None = None
    follow_up: Literal["rescheduled", "split", "unscheduled", "cancelled", "left"] | None = None
    carried_from_plan_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class HabitRow(_Base):
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    kind: Literal["boolean", "duration", "count"]
    unit: str | None = Field(default=None, max_length=30)
    start_date: date
    archived_on: date | None = None
    archived_at: datetime | None = None
    source_inbox_item_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class ScheduleRow(_Base):
    id: uuid.UUID
    habit_id: uuid.UUID
    effective_from: date
    effective_to: date | None = None
    schedule_type: Literal["daily", "weekdays", "weekly_target"]
    weekdays: list[int] = Field(default_factory=list)
    weekly_target: int | None = Field(default=None, ge=1, le=7)
    target_value: int = Field(ge=1)
    created_at: datetime


class PauseRow(_Base):
    id: uuid.UUID
    habit_id: uuid.UUID
    start_date: date
    end_date: date | None = None
    created_at: datetime


class CheckinRow(_Base):
    id: uuid.UUID
    habit_id: uuid.UUID
    checkin_date: date
    value: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class JournalRow(_Base):
    id: uuid.UUID
    entry_date: date
    body: str = ""
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    went_well: str = ""
    was_difficult: str = ""
    on_mind: str = ""
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class AuditRow(_Base):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    before: dict | None = None
    after: dict | None = None
    note: str | None = None
    created_at: datetime


class FinanceAccountRow(_Base):
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=60)
    type: Literal["debit", "credit"]
    opening_balance_cents: int
    opened_on: date
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FinanceCategoryRow(_Base):
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["expense", "income"]
    sort_order: int = 0
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FinanceRecurringRow(_Base):
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["expense", "income", "payment"]
    amount_cents: int = Field(gt=0)
    account_id: uuid.UUID
    to_account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    frequency: Literal["weekly", "monthly", "yearly"]
    interval: int = Field(ge=1, le=12)
    anchor_on: date
    posted_count: int = Field(ge=0)
    paused_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FinanceTransactionRow(_Base):
    id: uuid.UUID
    occurred_on: date
    kind: Literal["expense", "income", "payment"]
    amount_cents: int = Field(gt=0)
    account_id: uuid.UUID
    to_account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    note: str = ""
    recurring_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class ExportFile(_Base):
    format: Literal["steady-export"]
    version: Literal[1]
    exported_at: datetime
    settings: dict[str, Any] | None = None
    inbox_items: list[InboxRow] = Field(default_factory=list)
    tasks: list[TaskRow] = Field(default_factory=list)
    task_plans: list[PlanRow] = Field(default_factory=list)
    habits: list[HabitRow] = Field(default_factory=list)
    habit_schedules: list[ScheduleRow] = Field(default_factory=list)
    habit_pauses: list[PauseRow] = Field(default_factory=list)
    habit_checkins: list[CheckinRow] = Field(default_factory=list)
    journal_entries: list[JournalRow] = Field(default_factory=list)
    audit_log: list[AuditRow] = Field(default_factory=list)
    finance_accounts: list[FinanceAccountRow] = Field(default_factory=list)
    finance_categories: list[FinanceCategoryRow] = Field(default_factory=list)
    finance_recurring: list[FinanceRecurringRow] = Field(default_factory=list)
    finance_transactions: list[FinanceTransactionRow] = Field(default_factory=list)
    finance_splitwise: dict[str, int] | None = None  # {"get_cents": ..., "pay_cents": ...}


# Order matters: parents before children.
COLLECTIONS: list[tuple[str, type, type]] = [
    ("inbox_items", InboxItem, InboxRow),
    ("tasks", Task, TaskRow),
    ("task_plans", TaskPlan, PlanRow),
    ("habits", Habit, HabitRow),
    ("habit_schedules", HabitSchedule, ScheduleRow),
    ("habit_pauses", HabitPause, PauseRow),
    ("habit_checkins", HabitCheckin, CheckinRow),
    ("journal_entries", JournalEntry, JournalRow),
    ("audit_log", AuditLog, AuditRow),
    ("finance_accounts", FinanceAccount, FinanceAccountRow),
    ("finance_categories", FinanceCategory, FinanceCategoryRow),
    ("finance_recurring", FinanceRecurring, FinanceRecurringRow),
    ("finance_transactions", FinanceTransaction, FinanceTransactionRow),
]


def export_all(db: Session) -> dict:
    settings = db.scalars(select(AppSettings)).first()  # the signed-in user's
    out: dict[str, Any] = {
        "format": FORMAT, "version": VERSION, "exported_at": utcnow(),
        "settings": ({"timezone": settings.timezone, "week_start": settings.week_start,
                      "timeline_start": settings.timeline_start.isoformat(timespec="minutes"),
                      "timeline_end": settings.timeline_end.isoformat(timespec="minutes"),
                      "currency": settings.currency}
                     if settings else None),
    }
    for name, model, row_type in COLLECTIONS:
        rows = db.scalars(select(model)).all()
        fields = row_type.model_fields.keys()
        out[name] = [row_type(**{f: getattr(r, f) for f in fields}).model_dump(mode="json")
                     for r in rows]
    sw = db.scalars(select(FinanceSplitwise)).first()
    out["finance_splitwise"] = {"get_cents": sw.get_cents, "pay_cents": sw.pay_cents} if sw else None
    return ExportFile.model_validate(out).model_dump(mode="json")


def _ids(db: Session, model: type, ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not ids:
        return set()
    return set(db.scalars(select(model.id).where(model.id.in_(ids))))


def import_all(db: Session, data: ExportFile, dry_run: bool) -> dict:
    report: dict[str, dict[str, int]] = {}
    to_insert: dict[str, list] = {}

    existing_ids = {name: _ids(db, model, {r.id for r in getattr(data, name)})
                    for name, model, _ in COLLECTIONS}

    def known(name: str, model: type, ref: uuid.UUID | None) -> bool:
        if ref is None:
            return True
        if any(r.id == ref for r in getattr(data, name)):
            return True
        return db.get(model, ref) is not None

    # Reference checks: reject the whole file if anything points nowhere.
    problems = []
    for t in data.tasks:
        if not known("tasks", Task, t.parent_task_id) or not known("inbox_items", InboxItem, t.source_inbox_item_id):
            problems.append(f"task {t.id}")
    for p in data.task_plans:
        if not known("tasks", Task, p.task_id) or not known("task_plans", TaskPlan, p.carried_from_plan_id):
            problems.append(f"task plan {p.id}")
    for h in data.habits:
        if not known("inbox_items", InboxItem, h.source_inbox_item_id):
            problems.append(f"habit {h.id}")
    for t in data.finance_transactions:
        if (not known("finance_accounts", FinanceAccount, t.account_id)
                or not known("finance_accounts", FinanceAccount, t.to_account_id)
                or not known("finance_categories", FinanceCategory, t.category_id)):
            problems.append(f"money entry {t.id}")
        elif not known("finance_recurring", FinanceRecurring, t.recurring_id):
            problems.append(f"money entry {t.id}")
    for r in data.finance_recurring:
        if (not known("finance_accounts", FinanceAccount, r.account_id)
                or not known("finance_accounts", FinanceAccount, r.to_account_id)
                or not known("finance_categories", FinanceCategory, r.category_id)):
            problems.append(f"repeating entry {r.id}")
    for name in ("habit_schedules", "habit_pauses", "habit_checkins"):
        for r in getattr(data, name):
            if not known("habits", Habit, r.habit_id):
                problems.append(f"{name} {r.id}")
    if problems:
        raise invalid("bad_references",
                      "Import rejected: these records refer to missing records: " + ", ".join(problems[:10]))

    # Natural-key conflicts with what is already stored.
    journal_dates = set(db.scalars(select(JournalEntry.entry_date)))
    checkin_keys = set(db.execute(select(HabitCheckin.habit_id, HabitCheckin.checkin_date)).tuples())
    plan_keys = set(db.execute(select(TaskPlan.task_id, TaskPlan.plan_date)).tuples())
    recurring_keys = set(db.execute(select(FinanceTransaction.recurring_id, FinanceTransaction.occurred_on)
                                    .where(FinanceTransaction.recurring_id.is_not(None))).tuples())

    for name, model, _ in COLLECTIONS:
        rows = getattr(data, name)
        counts = {"in_file": len(rows), "imported": 0, "skipped_existing": 0, "conflicts": 0}
        accepted = []
        for r in rows:
            if r.id in existing_ids[name]:
                counts["skipped_existing"] += 1
                continue
            key = None
            if name == "journal_entries":
                key, keyset = r.entry_date, journal_dates
            elif name == "habit_checkins":
                key, keyset = (r.habit_id, r.checkin_date), checkin_keys
            elif name == "task_plans":
                key, keyset = (r.task_id, r.plan_date), plan_keys
            elif name == "finance_transactions" and r.recurring_id is not None:
                key, keyset = (r.recurring_id, r.occurred_on), recurring_keys
            if key is not None:
                if key in keyset:
                    counts["conflicts"] += 1
                    continue
                keyset.add(key)
            accepted.append(r)
            counts["imported"] += 1
        report[name] = counts
        to_insert[name] = accepted

    if not dry_run:
        # Self-references (task parents, plan carry links) are set in a second pass.
        deferred = []
        for name, model, _ in COLLECTIONS:
            for r in to_insert[name]:
                values = r.model_dump()
                if name == "tasks" and values.get("parent_task_id"):
                    deferred.append((Task, r.id, "parent_task_id", values.pop("parent_task_id")))
                if name == "task_plans" and values.get("carried_from_plan_id"):
                    deferred.append((TaskPlan, r.id, "carried_from_plan_id", values.pop("carried_from_plan_id")))
                db.add(model(**values))
            db.flush()
        for model, row_id, field, ref in deferred:
            setattr(db.get(model, row_id), field, ref)
        db.flush()
        sw = data.finance_splitwise
        if sw and db.scalars(select(FinanceSplitwise)).first() is None:  # never overwrite totals you already have
            db.add(FinanceSplitwise(get_cents=max(0, sw.get("get_cents", 0)), pay_cents=max(0, sw.get("pay_cents", 0))))
            db.flush()

    return {"dry_run": dry_run, "collections": report,
            "settings_in_file": data.settings, "settings_applied": False}
