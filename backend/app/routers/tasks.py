import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Ctx, get_ctx
from app.models import Task, TaskPlan
from app.schemas import (
    BatchSchedule, DayOut, FollowUpIn, PendingReviewDay, PlanOut, ReviewIn, ScheduleTask,
    SplitIn, TaskCreate, TaskHistoryOut, TaskOut, TaskUpdate, WeekOut,
)
from app.services import tasks as service
from app.timeutil import week_dates

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(view: Literal["inbox", "unscheduled", "needs_decision", "archived", "all_active"] = "unscheduled",
               db: Session = Depends(get_db)) -> list[Task]:
    stmt = select(Task).order_by(Task.created_at.desc())
    if view == "archived":
        stmt = stmt.where(Task.archived_at.is_not(None))
    else:
        stmt = stmt.where(Task.archived_at.is_(None), Task.status == "active")
        if view in ("inbox", "unscheduled", "needs_decision"):
            stmt = stmt.where(Task.planned_date.is_(None))
        if view == "inbox":  # tasks without a day that belong to the Inbox
            stmt = stmt.where(Task.origin == "inbox")
    tasks = list(db.scalars(stmt.limit(500)))
    if view == "needs_decision":
        # Reviewed as unfinished, and the user hasn't chosen what to do next yet.
        waiting = set(db.scalars(select(TaskPlan.task_id).where(
            TaskPlan.outcome.in_(service.UNFINISHED), TaskPlan.follow_up.is_(None))))
        tasks = [t for t in tasks if t.id in waiting]
    return tasks


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(data: TaskCreate, response: Response, db: Session = Depends(get_db),
                ctx: Ctx = Depends(get_ctx)) -> Task:
    try:
        task, created = service.create_task(db, ctx, data)
        db.commit()
    except IntegrityError:
        # The same request (same client id) was saved by a simultaneous submission.
        db.rollback()
        existing = db.get(Task, data.id) if data.id else None
        if existing is None:
            raise
        task, created = existing, False
    if not created:
        response.status_code = 200
    return task


@router.get("/tasks/{task_id}", response_model=TaskHistoryOut)
def task_history(task_id: uuid.UUID, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    return service.task_history(db, ctx, service.get_task(db, task_id))


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def edit_task(task_id: uuid.UUID, data: TaskUpdate, db: Session = Depends(get_db)) -> Task:
    task = service.update_task(db, service.get_task(db, task_id, lock=True), data)
    db.commit()
    return task


@router.delete("/tasks/{task_id}", status_code=204)
def delete(task_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """Permanently delete a task and its records on every day. Repeating it is harmless."""
    task = db.get(Task, task_id)
    if task is not None:
        service.delete_task(db, task)
        db.commit()
    return Response(status_code=204)


@router.put("/tasks/{task_id}/schedule", response_model=TaskOut)
def schedule(task_id: uuid.UUID, data: ScheduleTask, db: Session = Depends(get_db),
             ctx: Ctx = Depends(get_ctx)) -> Task:
    task = service.get_task(db, task_id, lock=True)
    if data.planned_date is None:
        service.unschedule_task(db, ctx, task)
    else:
        given = {"planned_time", "planned_end_time"} & data.model_fields_set
        times = (data.planned_time, data.planned_end_time) if given else service.KEEP
        service.schedule_task(db, ctx, task, data.planned_date, times)
    db.commit()
    return task


@router.post("/tasks/{task_id}/split", response_model=list[TaskOut])
def split(task_id: uuid.UUID, data: SplitIn, db: Session = Depends(get_db),
          ctx: Ctx = Depends(get_ctx)) -> list[Task]:
    children = service.split_task(db, ctx, service.get_task(db, task_id, lock=True), data.steps)
    db.commit()
    return children


@router.post("/tasks/{task_id}/{action}", response_model=TaskOut)
def task_action(task_id: uuid.UUID, action: Literal["cancel", "restore", "reopen", "archive", "unarchive"],
                db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> Task:
    task = service.get_task(db, task_id, lock=True)
    if action == "cancel":
        service.cancel_task(db, ctx, task)
    elif action == "restore":
        service.restore_task(db, ctx, task)
    elif action == "reopen":
        service.reopen_task(db, task)
    elif action == "archive":
        service.archive_task(db, ctx, task)
    else:
        service.unarchive_task(db, task)
    db.commit()
    return task


@router.get("/plans/day", response_model=DayOut)
def day(date: date, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> DayOut:
    return service.build_days(db, ctx, [date])[0]


@router.get("/plans/week", response_model=WeekOut)
def week(date: date, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> WeekOut:
    days = week_dates(date, ctx.week_start)
    return WeekOut(start=days[0], end=days[-1], today=ctx.today, days=service.build_days(db, ctx, days))


@router.get("/plans/pending-reviews", response_model=list[PendingReviewDay])
def pending_reviews(db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> list[PendingReviewDay]:
    return [PendingReviewDay(date=d, unreviewed=n) for d, n in service.pending_review_days(db, ctx)]


@router.get("/plans/needs-decision", response_model=list[PlanOut])
def needs_decision(db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> list[PlanOut]:
    """Plans reviewed as unfinished whose task is still active, unscheduled and has no next step chosen."""
    plans = list(db.scalars(
        select(TaskPlan).join(Task)
        .where(TaskPlan.outcome.in_(service.UNFINISHED), TaskPlan.follow_up.is_(None),
               Task.status == "active", Task.planned_date.is_(None), Task.archived_at.is_(None))
        .order_by(TaskPlan.plan_date.desc()).limit(100)
    ))
    return service.plans_out(db, plans, ctx.today)


@router.post("/plans/batch", response_model=list[PlanOut])
def batch(data: BatchSchedule, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> list[PlanOut]:
    plans = service.batch_schedule(db, ctx, data.date, data.task_ids)
    db.commit()
    return service.plans_out(db, plans, ctx.today)


@router.put("/plans/{plan_id}/review", response_model=PlanOut)
def review(plan_id: uuid.UUID, data: ReviewIn, db: Session = Depends(get_db),
           ctx: Ctx = Depends(get_ctx)) -> PlanOut:
    plan = service.review_plan(db, ctx, service.get_plan(db, plan_id), data.outcome, data.reason,
                               data.reason_note, data.correction_note)
    db.commit()
    return service.plans_out(db, [plan], ctx.today)[0]


@router.post("/plans/{plan_id}/follow-up", response_model=PlanOut)
def follow_up(plan_id: uuid.UUID, data: FollowUpIn, db: Session = Depends(get_db),
              ctx: Ctx = Depends(get_ctx)) -> PlanOut:
    plan = service.follow_up(db, ctx, service.get_plan(db, plan_id), data.action, data.date, data.steps)
    db.commit()
    return service.plans_out(db, [plan], ctx.today)[0]
