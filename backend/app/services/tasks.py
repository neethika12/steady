"""Task planning, carry-forward, end-of-day review and daily statistics.

History rules (see README "Daily history"):

* A task's dated plans are separate rows. Rescheduling a plan that is already in
  the past, or that already has an outcome, keeps the old row untouched and adds
  a new row linked by ``carried_from_plan_id``.
* A plan dated today or later that has no outcome yet is simply moved: the day
  has not finished, so nothing historical is lost. The move is written to the
  audit log.
* ``outcome IS NULL`` means "not reviewed", which is different from "not completed".
* Changing an outcome after it was recorded is a correction and is audited.
* Nothing is ever rescheduled, split or cancelled automatically.
"""

import uuid
from dataclasses import dataclass
from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import audit
from app.deps import Ctx
from app.errors import conflict, invalid, not_found
from app.models import AuditLog, Task, TaskPlan
from app.schemas import (
    DayOut,
    DayStats,
    PlanOut,
    StepIn,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)

UNFINISHED = ("partial", "not_completed")  # "partial" only exists in older history

KEEP = object()  # schedule_task: keep (or carry over) the current time of day

TimeRange = tuple["time | None", "time | None"]  # (start, end); (None, None) = anytime


# ---------- lookups ----------

def get_task(db: Session, task_id: uuid.UUID, lock: bool = False) -> Task:
    stmt = select(Task).where(Task.id == task_id)
    if lock:
        stmt = stmt.with_for_update()
    task = db.scalars(stmt).one_or_none()
    if task is None:
        raise not_found("Task")
    return task


def get_plan(db: Session, plan_id: uuid.UUID) -> TaskPlan:
    plan = db.scalars(
        select(TaskPlan).where(TaskPlan.id == plan_id).with_for_update()
    ).one_or_none()
    if plan is None:
        raise not_found("Planned task")
    return plan


def plan_on(db: Session, task_id: uuid.UUID, day: date) -> TaskPlan | None:
    return db.scalars(
        select(TaskPlan).where(TaskPlan.task_id == task_id, TaskPlan.plan_date == day)
    ).one_or_none()


def open_plan(db: Session, task: Task) -> TaskPlan | None:
    """The plan for ``task.planned_date`` (the day the task is currently planned for)."""
    if task.planned_date is None:
        return None
    return plan_on(db, task.id, task.planned_date)


def _latest_unfinished_before(db: Session, task: Task, day: date) -> TaskPlan | None:
    return db.scalars(
        select(TaskPlan)
        .where(
            TaskPlan.task_id == task.id,
            TaskPlan.plan_date < day,
            (TaskPlan.outcome.is_(None)) | (TaskPlan.outcome.in_(UNFINISHED)),
        )
        .order_by(TaskPlan.plan_date.desc())
        .limit(1)
    ).one_or_none()


def _remove_future_plan(db: Session, plan: TaskPlan, ctx: Ctx, why: str) -> bool:
    """Delete a plan that is not due yet and has no outcome. Returns True if removed."""
    if plan.outcome is None and plan.plan_date >= ctx.today:
        audit.record(db, "plan", plan.id, "plan_removed",
                     before=audit.snapshot(plan, audit.PLAN_FIELDS), note=why)
        db.delete(plan)
        db.flush()
        return True
    return False


def _require_active(task: Task) -> None:
    if task.archived_at is not None:
        raise conflict("task_archived", "This task is archived. Restore it first.")
    if task.status != "active":
        raise conflict("task_not_active", f"This task is {task.status} and can't be planned.")


# ---------- create / edit ----------

def create_task(db: Session, ctx: Ctx, data: TaskCreate, *,
                parent_task_id: uuid.UUID | None = None,
                source_inbox_item_id: uuid.UUID | None = None) -> tuple[Task, bool]:
    """Create a task. Returns (task, created). A repeated id returns the existing task."""
    if data.id is not None:
        existing = db.get(Task, data.id)
        if existing is not None:
            return existing, False
    task = Task(
        id=data.id or uuid.uuid4(),
        title=data.title,
        description=data.description,
        priority=data.priority,
        category=data.category,
        estimated_minutes=data.estimated_minutes,
        deadline=data.deadline,
        status="active",
        origin="day" if data.planned_date is not None else "inbox",
        parent_task_id=parent_task_id,
        source_inbox_item_id=source_inbox_item_id,
    )
    db.add(task)
    db.flush()
    if data.planned_date is not None:
        schedule_task(db, ctx, task, data.planned_date, (data.planned_time, data.planned_end_time))
    return task, True


def update_task(db: Session, task: Task, data: TaskUpdate) -> Task:
    changes = data.model_dump(exclude_unset=True)
    if "title" in changes and (changes["title"] is None or not changes["title"].strip()):
        raise invalid("title_required", "Title cannot be empty.")
    before = audit.snapshot(task, audit.TASK_FIELDS)
    for key, value in changes.items():
        if key == "title":
            value = value.strip()
        if key == "category" and value is not None:
            value = value.strip() or None
        if key == "description" and value is None:
            value = ""
        setattr(task, key, value)
    db.flush()
    after = audit.snapshot(task, audit.TASK_FIELDS)
    if before != after:
        audit.record(db, "task", task.id, "edited",
                     before={k: v for k, v in before.items() if after[k] != v},
                     after={k: v for k, v in after.items() if before[k] != v})
    return task


# ---------- scheduling ----------

def check_range(ctx: Ctx, start: "time | None", end: "time | None") -> None:
    """A range may run past midnight (end earlier than start) only when the user's day does."""
    if start is not None and end is not None and end < start and not ctx.past_midnight:
        raise invalid("time_range", "The end time must be after the start time. (A task can run past "
                                    "midnight only when your timeline does; change it in Settings.)")


def day_minutes(ctx: Ctx, t: time) -> int:
    """Minutes into the user's day: 00:30 comes after 23:00 when the day runs past midnight."""
    m = t.hour * 60 + t.minute
    return m + 1440 if ctx.past_midnight and t < ctx.timeline_end else m


def schedule_task(db: Session, ctx: Ctx, task: Task, new_date: date,
                  times: "TimeRange | object" = KEEP) -> TaskPlan:
    """Plan ``task`` for ``new_date``, optionally at a time or time range. Safe to repeat.

    ``times`` is (start, end); (None, None) means anytime; KEEP keeps / carries the current one.
    """
    _require_active(task)
    if times is not KEEP:
        check_range(ctx, *times)  # type: ignore[misc]
    current = open_plan(db, task)
    if task.planned_date == new_date and current is not None:
        if times is not KEEP and (current.planned_time, current.planned_end_time) != times:
            before = audit.snapshot(current, audit.PLAN_FIELDS)
            current.planned_time, current.planned_end_time = times  # type: ignore[misc]
            audit.record(db, "plan", current.id, "time_changed", before=before,
                         after=audit.snapshot(current, audit.PLAN_FIELDS))
            db.flush()
        return current
    existing = plan_on(db, task.id, new_date)
    if existing is not None:
        raise conflict(
            "plan_exists",
            f"This task already has a record on {new_date.isoformat()}. "
            "Choose another date or correct that day's review instead.",
        )

    if current is not None and current.outcome is None and current.plan_date >= ctx.today:
        # Not due yet and not reviewed: a plain move, nothing historical is lost.
        before = audit.snapshot(current, audit.PLAN_FIELDS)
        current.plan_date = new_date
        if times is not KEEP:
            current.planned_time, current.planned_end_time = times  # type: ignore[misc]
        plan = current
        audit.record(db, "plan", plan.id, "moved", before=before,
                     after=audit.snapshot(plan, audit.PLAN_FIELDS))
    else:
        # Keep any earlier record exactly as it is and continue on a new row.
        previous = current or _latest_unfinished_before(db, task, new_date)
        carried_from = previous if previous is not None and previous.plan_date < new_date else None
        if times is KEEP:
            start, end = (previous.planned_time, previous.planned_end_time) if previous is not None else (None, None)
        else:
            start, end = times  # type: ignore[misc]
        plan = TaskPlan(task_id=task.id, plan_date=new_date, planned_time=start, planned_end_time=end,
                        carried_from_plan_id=carried_from.id if carried_from else None)
        db.add(plan)
        if carried_from is not None and carried_from.outcome in UNFINISHED and carried_from.follow_up is None:
            carried_from.follow_up = "rescheduled"
        db.flush()
        audit.record(db, "plan", plan.id, "carried_forward" if carried_from else "scheduled",
                     after={"plan_date": new_date.isoformat(),
                            "carried_from_date": carried_from.plan_date.isoformat() if carried_from else None})
    task.planned_date = new_date
    db.flush()
    return plan


def unschedule_task(db: Session, ctx: Ctx, task: Task) -> None:
    """Move the task to the Inbox. Past days keep their (unreviewed) record."""
    current = open_plan(db, task)
    if current is not None:
        _remove_future_plan(db, current, ctx, "unscheduled")
    task.planned_date = None
    task.origin = "inbox"  # explicitly put in the Inbox: it belongs there now
    db.flush()


def batch_schedule(db: Session, ctx: Ctx, day: date, task_ids: list[uuid.UUID]) -> list[TaskPlan]:
    """Schedule several tasks in one transaction (used when accepting a daily plan)."""
    plans = []
    for task_id in dict.fromkeys(task_ids):  # de-duplicate, keep order
        task = get_task(db, task_id, lock=True)
        plans.append(schedule_task(db, ctx, task, day))
    return plans


# ---------- review ----------

def review_plan(db: Session, ctx: Ctx, plan: TaskPlan, outcome: str | None, reason: str | None,
                reason_note: str | None, correction_note: str | None = None) -> TaskPlan:
    if plan.plan_date > ctx.today:
        raise conflict("future_review", "You can only review days that have started.")
    if plan.outcome == "cancelled":
        raise conflict("plan_cancelled", "This task was cancelled for that day. Reopen the task to change it.")
    task = get_task(db, plan.task_id, lock=True)

    if outcome not in UNFINISHED:
        reason, reason_note = None, None
    reason_note = (reason_note or "").strip() or None
    if outcome == "not_completed" and reason_note is None:
        raise invalid("reason_required", "Please write a short reason why it wasn't done.")
    if (plan.outcome, plan.reason, plan.reason_note) == (outcome, reason, reason_note):
        return plan  # repeated submission: nothing to do

    if outcome == "completed" and task.status in ("cancelled", "split"):
        raise conflict("task_closed", f"This task was {task.status}; it can't be marked completed.")

    was_reviewed = plan.outcome is not None
    before = audit.snapshot(plan, audit.PLAN_FIELDS)

    if plan.outcome == "completed" and outcome != "completed" and task.status == "completed":
        other_completed = db.scalar(
            select(func.count()).select_from(TaskPlan).where(
                TaskPlan.task_id == task.id, TaskPlan.id != plan.id, TaskPlan.outcome == "completed"
            )
        )
        if not other_completed:
            task.status = "active"
            task.completed_at = None

    plan.outcome = outcome
    plan.reason = reason
    plan.reason_note = reason_note
    plan.reviewed_at = ctx.now if outcome else None
    if outcome == "completed":
        if plan.completed_at is None:
            plan.completed_at = ctx.now
    else:
        plan.completed_at = None

    if outcome == "completed":
        if task.status != "completed":
            task.status = "completed"
            task.completed_at = ctx.now
        if task.planned_date is not None and task.planned_date != plan.plan_date:
            later = open_plan(db, task)
            if later is not None:
                _remove_future_plan(db, later, ctx, "task completed on an earlier day")
        task.planned_date = None
    elif outcome in UNFINISHED:
        if task.planned_date == plan.plan_date:
            task.planned_date = None
    else:  # cleared back to "not reviewed"
        has_successor = db.scalar(
            select(func.count()).select_from(TaskPlan).where(TaskPlan.carried_from_plan_id == plan.id)
        )
        if task.status == "active" and task.planned_date is None and not has_successor:
            task.planned_date = plan.plan_date
        if not has_successor:
            plan.follow_up = None

    db.flush()
    audit.record(db, "plan", plan.id, "correction" if was_reviewed else "review",
                 before=before, after=audit.snapshot(plan, audit.PLAN_FIELDS), note=correction_note)
    return plan


def follow_up(db: Session, ctx: Ctx, plan: TaskPlan, action: str, new_date: date | None,
              steps: list[StepIn] | None) -> TaskPlan:
    """What to do with an unfinished task after its review. Always an explicit user choice."""
    if plan.outcome not in UNFINISHED:
        raise conflict("not_unfinished", "Follow-up actions are for tasks reviewed as partly or not completed.")
    task = get_task(db, plan.task_id, lock=True)
    if action == "reschedule":
        assert new_date is not None
        schedule_task(db, ctx, task, new_date)
        plan.follow_up = "rescheduled"
    elif action == "split":
        split_task(db, ctx, task, steps or [])
        plan.follow_up = "split"
    elif action == "unscheduled":
        if task.planned_date is not None and task.planned_date > plan.plan_date:
            unschedule_task(db, ctx, task)
        task.origin = "inbox"
        plan.follow_up = "unscheduled"
    elif action == "leave":
        plan.follow_up = "left"  # stays "not completed" on its day; not added to the Inbox
    elif action == "cancel":
        cancel_task(db, ctx, task)
        plan.follow_up = "cancelled"
    db.flush()
    return plan


def split_task(db: Session, ctx: Ctx, task: Task, steps: list[StepIn]) -> list[Task]:
    """Replace a task with smaller tasks. Repeating the request returns the same children."""
    if task.status == "split":
        return children_of(db, task.id)
    _require_active(task)
    if not steps:
        raise invalid("steps_required", "Add at least one smaller task.")
    current = open_plan(db, task)
    if current is not None:
        _remove_future_plan(db, current, ctx, "task split")
    task.planned_date = None
    task.status = "split"
    children = []
    for step in steps:
        child, _ = create_task(
            db, ctx,
            TaskCreate(title=step.title, priority=task.priority, category=task.category,
                       estimated_minutes=step.estimated_minutes, deadline=task.deadline,
                       planned_date=step.planned_date),
            parent_task_id=task.id,
        )
        children.append(child)
    audit.record(db, "task", task.id, "split", after={"children": [str(c.id) for c in children]})
    db.flush()
    return children


def children_of(db: Session, task_id: uuid.UUID) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.parent_task_id == task_id).order_by(Task.created_at)))


def cancel_task(db: Session, ctx: Ctx, task: Task) -> Task:
    """Cancel a task. Its plan for today or a past day is marked 'cancelled' (excluded from
    that day's completion denominator and shown separately); a future plan is removed."""
    if task.status == "cancelled":
        return task
    if task.status != "active":
        raise conflict("task_not_active", f"This task is {task.status} and can't be cancelled.")
    current = open_plan(db, task)
    if current is not None and current.outcome is None:
        if current.plan_date > ctx.today:
            _remove_future_plan(db, current, ctx, "task cancelled")
        else:
            before = audit.snapshot(current, audit.PLAN_FIELDS)
            current.outcome = "cancelled"
            current.reviewed_at = ctx.now
            audit.record(db, "plan", current.id, "cancelled", before=before,
                         after=audit.snapshot(current, audit.PLAN_FIELDS))
    task.status = "cancelled"
    task.cancelled_at = ctx.now
    task.planned_date = None
    audit.record(db, "task", task.id, "cancelled")
    db.flush()
    return task


def restore_task(db: Session, ctx: Ctx, task: Task) -> Task:
    """Undo a cancellation. Safe to repeat.

    If the task was cancelled while planned for a day, it goes back to that same day
    (same time of day), ready to be marked again; the undo is audited. If it was
    cancelled from the Inbox, it goes back to the Inbox. Older cancellations stay in history.
    """
    if task.status not in ("active", "cancelled"):
        raise conflict("task_closed", f"This task is {task.status}; it can't be restored.")
    if task.status == "active" and task.archived_at is None:
        return task
    latest = db.scalars(select(TaskPlan).where(TaskPlan.task_id == task.id)
                        .order_by(TaskPlan.plan_date.desc()).limit(1)).one_or_none()
    task.status = "active"
    task.cancelled_at = None
    task.archived_at = None
    if latest is not None and latest.outcome == "cancelled":
        before = audit.snapshot(latest, audit.PLAN_FIELDS)
        latest.outcome = None
        latest.reviewed_at = None
        task.planned_date = latest.plan_date
        audit.record(db, "plan", latest.id, "cancellation_undone", before=before,
                     after=audit.snapshot(latest, audit.PLAN_FIELDS))
    elif latest is not None and latest.follow_up == "cancelled":
        latest.follow_up = None  # cancelled after "not completed": back to the Inbox, still marked
    audit.record(db, "task", task.id, "restored",
                 after={"planned_date": task.planned_date.isoformat() if task.planned_date else None})
    db.flush()
    return task


def delete_task(db: Session, task: Task) -> int:
    """Permanently delete a task and all its dated records. Returns how many day records went.

    Only on explicit request (the UI asks for confirmation). Smaller tasks split from it
    are kept and simply lose their link. The task's audit entries are removed too, and one
    content-free entry records that a deletion happened.
    """
    plans = list(db.scalars(select(TaskPlan).where(TaskPlan.task_id == task.id)))
    plan_ids = [p.id for p in plans]
    for child in db.scalars(select(Task).where(Task.parent_task_id == task.id)):
        child.parent_task_id = None
    for p in plans:
        p.carried_from_plan_id = None
    db.flush()
    for p in plans:
        db.delete(p)
    db.execute(AuditLog.__table__.delete().where(AuditLog.entity_id.in_([task.id, *plan_ids])))
    db.flush()
    db.delete(task)
    audit.record(db, "task", task.id, "deleted", after={"day_records_removed": len(plans)})
    db.flush()
    return len(plans)


def reopen_task(db: Session, task: Task) -> Task:
    if task.status != "cancelled":
        raise conflict("task_not_cancelled", "Only cancelled tasks can be reopened.")
    task.status = "active"
    task.cancelled_at = None
    audit.record(db, "task", task.id, "reopened")
    db.flush()
    return task


def archive_task(db: Session, ctx: Ctx, task: Task) -> Task:
    if task.archived_at is not None:
        return task
    current = open_plan(db, task)
    if current is not None:
        _remove_future_plan(db, current, ctx, "task archived")
    task.planned_date = None
    task.archived_at = ctx.now
    audit.record(db, "task", task.id, "archived")
    db.flush()
    return task


def unarchive_task(db: Session, task: Task) -> Task:
    if task.archived_at is None:
        return task
    task.archived_at = None
    audit.record(db, "task", task.id, "unarchived")
    db.flush()
    return task


# ---------- reading days ----------

def plan_state(plan: TaskPlan, today: date) -> str:
    if plan.outcome is not None:
        return plan.outcome
    return "awaiting_review" if plan.plan_date < today else "planned"


def plans_out(db: Session, plans: list[TaskPlan], today: date) -> list[PlanOut]:
    """Serialize plans with their carry-forward links."""
    if not plans:
        return []
    task_ids = {p.task_id for p in plans}
    all_plans = list(db.scalars(select(TaskPlan).where(TaskPlan.task_id.in_(task_ids))))
    by_id = {p.id: p for p in all_plans}
    successor = {p.carried_from_plan_id: p for p in all_plans if p.carried_from_plan_id}

    def times_carried(p: TaskPlan) -> int:
        n, seen = 0, set()
        while p.carried_from_plan_id and p.carried_from_plan_id in by_id and p.id not in seen:
            seen.add(p.id)
            n += 1
            p = by_id[p.carried_from_plan_id]
        return n

    out = []
    for p in plans:
        prev = by_id.get(p.carried_from_plan_id) if p.carried_from_plan_id else None
        nxt = successor.get(p.id)
        out.append(PlanOut(
            id=p.id, task_id=p.task_id, plan_date=p.plan_date, planned_time=p.planned_time,
            planned_end_time=p.planned_end_time, outcome=p.outcome,
            state=plan_state(p, today), reason=p.reason, reason_note=p.reason_note,
            reviewed_at=p.reviewed_at, completed_at=p.completed_at, follow_up=p.follow_up,
            carried_from_plan_id=p.carried_from_plan_id,
            carried_from_date=prev.plan_date if prev else None,
            carried_to_date=nxt.plan_date if nxt else None,
            times_carried=times_carried(p),
            task=TaskOut.model_validate(p.task),
        ))
    return out


def _pct(part: int, whole: int) -> int | None:
    """Whole-number percentage, rounded half up. None when there is nothing to divide by."""
    if whole <= 0:
        return None
    return (200 * part + whole) // (2 * whole)


@dataclass
class _PlanFacts:
    plan_date: date
    outcome: str | None
    carried: bool
    estimated_minutes: int | None


def compute_day_stats(day: date, today: date, plans: list[_PlanFacts]) -> DayStats:
    """Completion statistics for one day. Pure function; see README "Completion calculations".

    completion_pct = completed / (planned - cancelled). Partial, not completed and
    not-yet-reviewed plans all stay in the denominator: unreviewed work is never
    silently dropped from a past day.
    """
    cancelled = sum(1 for p in plans if p.outcome == "cancelled")
    counted = [p for p in plans if p.outcome != "cancelled"]
    completed = [p for p in counted if p.outcome == "completed"]
    unreviewed = [p for p in counted if p.outcome is None]
    est_planned = sum(p.estimated_minutes or 0 for p in counted)
    est_completed = sum(p.estimated_minutes or 0 for p in completed)
    return DayStats(
        date=day,
        planned=len(plans),
        counted=len(counted),
        completed=len(completed),
        partial=sum(1 for p in counted if p.outcome == "partial"),
        not_completed=sum(1 for p in counted if p.outcome == "not_completed"),
        awaiting_review=len(unreviewed) if day < today else 0,
        open=len(unreviewed) if day >= today else 0,
        cancelled=cancelled,
        carried_in=sum(1 for p in plans if p.carried),
        completion_pct=_pct(len(completed), len(counted)),
        estimated_minutes_planned=est_planned,
        estimated_minutes_completed=est_completed,
        effort_pct=_pct(est_completed, est_planned),
        plans_without_estimate=sum(1 for p in counted if not p.estimated_minutes),
    )


def plans_between(db: Session, start: date, end: date) -> list[TaskPlan]:
    return list(db.scalars(
        select(TaskPlan)
        .options(selectinload(TaskPlan.task))
        .where(TaskPlan.plan_date >= start, TaskPlan.plan_date <= end)
        .order_by(TaskPlan.plan_date, TaskPlan.created_at)
    ))


_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_days(db: Session, ctx: Ctx, days: list[date]) -> list[DayOut]:
    plans = plans_between(db, days[0], days[-1])
    serialized = plans_out(db, plans, ctx.today)
    result = []
    for d in days:
        todays = [p for p in serialized if p.plan_date == d]
        # Timed tasks first, in time order; then "anytime" tasks by priority.
        todays.sort(key=lambda p: (p.planned_time is None, day_minutes(ctx, p.planned_time) if p.planned_time else 0,
                                   _PRIORITY_ORDER.get(p.task.priority, 9), p.task.title.lower()))
        facts = [_PlanFacts(p.plan_date, p.outcome, p.carried_from_plan_id is not None,
                            p.task.estimated_minutes) for p in todays]
        result.append(DayOut(date=d, today=ctx.today,
                             stats=compute_day_stats(d, ctx.today, facts), plans=todays))
    return result


def pending_review_days(db: Session, ctx: Ctx, limit: int = 30) -> list[tuple[date, int]]:
    rows = db.execute(
        select(TaskPlan.plan_date, func.count())
        .where(TaskPlan.outcome.is_(None), TaskPlan.plan_date < ctx.today)
        .group_by(TaskPlan.plan_date)
        .order_by(TaskPlan.plan_date.desc())
        .limit(limit)
    ).all()
    return [(r[0], r[1]) for r in rows]


def task_history(db: Session, ctx: Ctx, task: Task) -> dict:
    plans = list(db.scalars(select(TaskPlan).where(TaskPlan.task_id == task.id)
                            .order_by(TaskPlan.plan_date)))
    ids = [task.id] + [p.id for p in plans]
    entries = list(db.scalars(select(AuditLog).where(AuditLog.entity_id.in_(ids))
                              .order_by(AuditLog.created_at)))
    return {"task": task, "plans": plans_out(db, plans, ctx.today), "audit": entries,
            "children": children_of(db, task.id)}
