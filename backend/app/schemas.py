"""Request and response shapes (validated by Pydantic)."""

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DateT = date  # alias for fields that are themselves named "date"

Priority = Literal["low", "medium", "high"]
ReviewOutcome = Literal["completed", "not_completed"]  # what a review can record today
Reason = Literal[
    "not_enough_time", "too_large", "unclear_next_step", "waiting",
    "low_energy", "priority_changed", "forgot_distracted", "other",
]
HabitKind = Literal["boolean", "duration", "count"]
ScheduleType = Literal["daily", "weekdays", "weekly_target"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def check_time_range(start: time | None, end: time | None) -> None:
    if end is not None and start is None:
        raise ValueError("Choose a start time before an end time")
    if end is not None and start is not None and end == start:
        raise ValueError("The end time must be different from the start time")
    # An end earlier than the start (running past midnight) is checked against the
    # user's timeline by the service.


def _strip(v: str | None) -> str | None:
    return v.strip() if isinstance(v, str) else v


# ---------- Settings ----------

class SettingsOut(BaseModel):
    timezone: str
    timezone_confirmed: bool
    week_start: int
    timeline_start: time
    timeline_end: time
    currency: str
    today: date
    now: datetime


class SettingsUpdate(BaseModel):
    timezone: str | None = None
    timezone_confirmed: bool | None = None
    week_start: int | None = Field(default=None, ge=0, le=6)
    timeline_start: time | None = None
    timeline_end: time | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


# ---------- Shared ----------

class StepIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    planned_date: date | None = None

    @field_validator("title")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Step title cannot be empty")
        return v.strip()


class ScheduleIn(BaseModel):
    schedule_type: ScheduleType
    weekdays: list[int] = Field(default_factory=list)
    weekly_target: int | None = Field(default=None, ge=1, le=7)
    target_value: int = Field(default=1, ge=1, le=1440)

    @model_validator(mode="after")
    def check(self) -> "ScheduleIn":
        if self.schedule_type == "weekdays":
            days = sorted(set(self.weekdays))
            if not days or any(d < 0 or d > 6 for d in days):
                raise ValueError("Choose at least one weekday (0 = Monday ... 6 = Sunday)")
            self.weekdays = days
        else:
            self.weekdays = []
        if self.schedule_type == "weekly_target":
            if self.weekly_target is None:
                raise ValueError("Weekly habits need a sessions-per-week target")
        else:
            self.weekly_target = None
        return self


class HabitCreate(BaseModel):
    id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    kind: HabitKind = "boolean"
    unit: str | None = Field(default=None, max_length=30)
    start_date: date | None = None
    schedule: ScheduleIn

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


# ---------- Tasks ----------

class TaskCreate(BaseModel):
    id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    priority: Priority = "medium"
    category: str | None = Field(default=None, max_length=60)
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    deadline: date | None = None
    planned_date: date | None = None
    planned_time: time | None = None  # None = anytime that day
    planned_end_time: time | None = None  # optional end of a time range

    @model_validator(mode="after")
    def valid_range(self) -> "TaskCreate":
        check_time_range(self.planned_time, self.planned_end_time)
        return self

    @field_validator("title")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()

    @field_validator("category")
    @classmethod
    def blank_category(cls, v: str | None) -> str | None:
        return (v.strip() or None) if v is not None else None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: Priority | None = None
    category: str | None = Field(default=None, max_length=60)
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    actual_minutes: int | None = Field(default=None, ge=0, le=10000)
    deadline: date | None = None


class TaskOut(ORM):
    id: uuid.UUID
    title: str
    description: str
    priority: str
    category: str | None
    estimated_minutes: int | None
    actual_minutes: int | None
    deadline: date | None
    planned_date: date | None
    status: str
    origin: str
    completed_at: datetime | None
    cancelled_at: datetime | None
    archived_at: datetime | None
    parent_task_id: uuid.UUID | None
    source_inbox_item_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ScheduleTask(BaseModel):
    planned_date: date | None  # None = back to the Inbox (no day)
    # Leave both out to keep the current time; send planned_time null for "anytime".
    planned_time: time | None = None
    planned_end_time: time | None = None

    @model_validator(mode="after")
    def valid_range(self) -> "ScheduleTask":
        check_time_range(self.planned_time, self.planned_end_time)
        return self


class PlanOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    plan_date: date
    planned_time: time | None
    planned_end_time: time | None
    outcome: str | None
    state: str  # completed | partial | not_completed | cancelled | awaiting_review | planned
    reason: str | None
    reason_note: str | None
    reviewed_at: datetime | None
    completed_at: datetime | None
    follow_up: str | None
    carried_from_plan_id: uuid.UUID | None
    carried_from_date: date | None
    carried_to_date: date | None
    times_carried: int
    task: TaskOut


class DayStats(BaseModel):
    date: DateT
    planned: int  # every plan on the day, including cancelled
    counted: int  # planned minus cancelled: the completion denominator
    completed: int
    partial: int
    not_completed: int
    awaiting_review: int  # past day, no outcome recorded yet
    open: int  # today or future, no outcome yet
    cancelled: int
    carried_in: int
    completion_pct: int | None  # None when nothing counted ("No tasks planned")
    estimated_minutes_planned: int
    estimated_minutes_completed: int
    effort_pct: int | None
    plans_without_estimate: int


class DayOut(BaseModel):
    date: DateT
    today: date
    stats: DayStats
    plans: list[PlanOut]


class WeekOut(BaseModel):
    start: date
    end: date
    today: date
    days: list[DayOut]


class ReviewIn(BaseModel):
    outcome: ReviewOutcome | None  # None clears the review (back to "not reviewed")
    reason: Reason | None = None  # optional tag
    reason_note: str | None = Field(default=None, max_length=2000)  # required when not completed
    correction_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def reason_required(self) -> "ReviewIn":
        if self.outcome == "not_completed" and len((self.reason_note or "").strip()) < 3:
            raise ValueError("Please write a short reason why it wasn't done")
        return self


class FollowUpIn(BaseModel):
    # unscheduled = put it in the Inbox; leave = leave it (not completed) on its day
    action: Literal["reschedule", "split", "unscheduled", "leave", "cancel"]
    date: DateT | None = None
    steps: list[StepIn] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def check(self) -> "FollowUpIn":
        if self.action == "reschedule" and self.date is None:
            raise ValueError("Choose a date to reschedule to")
        if self.action == "split" and not self.steps:
            raise ValueError("Add at least one smaller task")
        return self


class SplitIn(BaseModel):
    steps: list[StepIn] = Field(min_length=1, max_length=20)


class BatchSchedule(BaseModel):
    date: DateT
    task_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class AuditOut(ORM):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    before: dict | None
    after: dict | None
    note: str | None
    created_at: datetime


class TaskHistoryOut(BaseModel):
    task: TaskOut
    plans: list[PlanOut]
    audit: list[AuditOut]
    children: list[TaskOut]


class PendingReviewDay(BaseModel):
    date: DateT
    unreviewed: int


# ---------- Habits ----------

class HabitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    unit: str | None = Field(default=None, max_length=30)
    # How it's measured; only while nothing has been logged, so no past day changes meaning.
    kind: HabitKind | None = None
    target_value: int | None = Field(default=None, ge=1, le=1440)


class ScheduleChange(BaseModel):
    schedule: ScheduleIn
    effective_from: date | None = None  # default: today


class PauseIn(BaseModel):
    start_date: date | None = None
    end_date: date | None = None


class ResumeIn(BaseModel):
    date: DateT | None = None


class CheckinIn(BaseModel):
    value: int = Field(ge=0, le=100000)


class ScheduleOut(ORM):
    id: uuid.UUID
    effective_from: date
    effective_to: date | None
    schedule_type: str
    weekdays: list[int]
    weekly_target: int | None
    target_value: int


class PauseOut(ORM):
    id: uuid.UUID
    start_date: date
    end_date: date | None


class HabitOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    kind: str
    unit: str | None
    start_date: date
    archived_on: date | None
    source_inbox_item_id: uuid.UUID | None
    current_schedule: ScheduleOut | None
    schedules: list[ScheduleOut]
    pauses: list[PauseOut]
    paused_today: bool
    has_checkins: bool  # once true, how it's measured can't change
    created_at: datetime


# ---------- Journal ----------

class JournalFields(BaseModel):
    body: str = Field(default="", max_length=100_000)
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    went_well: str = Field(default="", max_length=10_000)
    was_difficult: str = Field(default="", max_length=10_000)
    on_mind: str = Field(default="", max_length=10_000)


class JournalSave(JournalFields):
    base_version: int = Field(ge=0)  # the version the client started editing; 0 = new entry


class JournalOut(JournalFields):
    entry_date: date
    exists: bool
    version: int
    updated_at: datetime | None


class JournalListItem(BaseModel):
    entry_date: date
    snippet: str
    word_count: int
    mood: int | None
    energy: int | None
    updated_at: datetime
