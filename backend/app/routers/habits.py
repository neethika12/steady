import uuid
from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Ctx, get_ctx
from app.models import Habit
from app.schemas import (
    CheckinIn, HabitCreate, HabitOut, HabitUpdate, PauseIn, ResumeIn, ScheduleChange,
)
from app.services import habits as service

router = APIRouter(prefix="/api/habits", tags=["habits"])


@router.get("", response_model=list[HabitOut])
def list_habits(include_archived: bool = False, db: Session = Depends(get_db),
                ctx: Ctx = Depends(get_ctx)) -> list[HabitOut]:
    return [service.habit_out(h, ctx.today) for h in service._load(db, include_archived)]


@router.post("", response_model=HabitOut, status_code=201)
def create_habit(data: HabitCreate, response: Response, db: Session = Depends(get_db),
                 ctx: Ctx = Depends(get_ctx)) -> HabitOut:
    if data.id is not None and db.get(Habit, data.id) is not None:
        response.status_code = 200
    habit = service.create_habit(db, ctx, data)
    db.commit()
    return service.habit_out(service.get_habit(db, habit.id), ctx.today)


@router.get("/day")
def day(date: date, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    return service.day_view(db, ctx, date)


@router.get("/calendar")
def calendar(start: date, end: date, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> list[dict]:
    return service.calendar(db, ctx, start, end)


@router.patch("/{habit_id}", response_model=HabitOut)
def edit(habit_id: uuid.UUID, data: HabitUpdate, db: Session = Depends(get_db),
         ctx: Ctx = Depends(get_ctx)) -> HabitOut:
    habit = service.update_habit(db, service.get_habit(db, habit_id, lock=True), data)
    db.commit()
    return service.habit_out(habit, ctx.today)


@router.put("/{habit_id}/schedule", response_model=HabitOut)
def change_schedule(habit_id: uuid.UUID, data: ScheduleChange, db: Session = Depends(get_db),
                    ctx: Ctx = Depends(get_ctx)) -> HabitOut:
    habit = service.change_schedule(db, ctx, service.get_habit(db, habit_id, lock=True),
                                    data.schedule, data.effective_from)
    db.commit()
    return service.habit_out(habit, ctx.today)


@router.post("/{habit_id}/pause", response_model=HabitOut)
def pause(habit_id: uuid.UUID, data: PauseIn, db: Session = Depends(get_db),
          ctx: Ctx = Depends(get_ctx)) -> HabitOut:
    habit = service.pause(db, ctx, service.get_habit(db, habit_id, lock=True), data.start_date, data.end_date)
    db.commit()
    return service.habit_out(habit, ctx.today)


@router.post("/{habit_id}/resume", response_model=HabitOut)
def resume(habit_id: uuid.UUID, data: ResumeIn, db: Session = Depends(get_db),
           ctx: Ctx = Depends(get_ctx)) -> HabitOut:
    habit = service.resume(db, ctx, service.get_habit(db, habit_id, lock=True), data.date)
    db.commit()
    return service.habit_out(habit, ctx.today)


@router.post("/{habit_id}/archive", response_model=HabitOut)
def archive(habit_id: uuid.UUID, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> HabitOut:
    habit = service.archive(db, ctx, service.get_habit(db, habit_id, lock=True))
    db.commit()
    return service.habit_out(habit, ctx.today)


@router.post("/{habit_id}/unarchive", response_model=HabitOut)
def unarchive(habit_id: uuid.UUID, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> HabitOut:
    habit = service.unarchive(db, service.get_habit(db, habit_id, lock=True))
    db.commit()
    return service.habit_out(habit, ctx.today)


@router.put("/{habit_id}/checkins/{day}")
def set_checkin(habit_id: uuid.UUID, day: date, data: CheckinIn, db: Session = Depends(get_db),
                ctx: Ctx = Depends(get_ctx)) -> dict:
    value = service.set_checkin(db, ctx, service.get_habit(db, habit_id), day, data.value)
    db.commit()
    return {"habit_id": habit_id, "date": day, "value": value}


@router.delete("/{habit_id}/checkins/{day}", status_code=204)
def clear_checkin(habit_id: uuid.UUID, day: date, db: Session = Depends(get_db)) -> Response:
    service.clear_checkin(db, service.get_habit(db, habit_id), day)
    db.commit()
    return Response(status_code=204)
