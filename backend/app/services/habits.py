"""Habits: versioned schedules, pauses, dated check-ins, progress and streaks.

Day statuses (for one habit on one date):

* ``inactive``      before the habit's start date, on/after its archive date, or no schedule
* ``future``        a day that hasn't happened yet
* ``paused``        inside a pause: never a failure
* ``done``          check-in meets the target for that day
* ``pending``       scheduled today, not done yet (not a failure until the day ends)
* ``missed``        scheduled on a past day, not done
* ``not_scheduled`` daily/weekday habits on a day they aren't scheduled: never a failure
* ``extra``         check-in on a day that wasn't scheduled (shown, never required)
* ``open``          weekly-target habits: any non-done day. These habits are judged per
                    week against their target, never per day.

Each day is judged by the schedule *version* in force on that day, so changing a
schedule never rewrites how past days are interpreted.
"""

import math
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app import audit
from app.deps import Ctx
from app.errors import conflict, invalid, not_found
from app.models import Habit, HabitCheckin, HabitPause, HabitSchedule, utcnow
from app.schemas import HabitCreate, HabitOut, HabitUpdate, ScheduleIn, ScheduleOut, PauseOut
from app.timeutil import date_range, week_dates, week_start_of

SCHEDULED_STATUSES = ("done", "pending", "missed")


# ---------- pure schedule logic ----------

def schedule_for(habit: Habit, day: date) -> HabitSchedule | None:
    for s in habit.schedules:
        if s.effective_from <= day and (s.effective_to is None or day <= s.effective_to):
            return s
    return None


def is_active(habit: Habit, day: date) -> bool:
    return day >= habit.start_date and (habit.archived_on is None or day < habit.archived_on)


def is_paused(habit: Habit, day: date) -> bool:
    return any(p.start_date <= day and (p.end_date is None or day <= p.end_date) for p in habit.pauses)


def is_scheduled_day(schedule: HabitSchedule, day: date) -> bool:
    if schedule.schedule_type == "daily":
        return True
    if schedule.schedule_type == "weekdays":
        return day.weekday() in (schedule.weekdays or [])
    return False  # weekly_target habits have no fixed days


def meets_target(schedule: HabitSchedule | None, value: int | None) -> bool:
    return schedule is not None and value is not None and value >= schedule.target_value


def day_status(habit: Habit, day: date, today: date, checkins: dict[date, int]) -> str:
    schedule = schedule_for(habit, day)
    if schedule is None or not is_active(habit, day):
        return "extra" if day <= today and meets_target(schedule, checkins.get(day)) else "inactive"
    if day > today:
        return "future"
    if is_paused(habit, day):
        return "paused"
    done = meets_target(schedule, checkins.get(day))
    if schedule.schedule_type == "weekly_target":
        return "done" if done else "open"
    if is_scheduled_day(schedule, day):
        if done:
            return "done"
        return "pending" if day == today else "missed"
    return "extra" if done else "not_scheduled"


@dataclass
class WeekProgress:
    week_start: date
    week_end: date
    sessions: int
    target: int  # sessions per week from the schedule
    required: int  # target scaled down for partial weeks (start/pause/archive)
    available_days: int
    met: bool
    finished: bool  # the week is over


def week_progress(habit: Habit, any_day: date, today: date, week_start: int,
                  checkins: dict[date, int]) -> WeekProgress | None:
    """Progress of a weekly-target habit in the week containing ``any_day``.

    Only days governed by a weekly-target schedule version count. If some days of the
    week are unavailable (before start, paused, archived), the target is scaled:
    required = ceil(target * available_days / 7).
    """
    days = week_dates(any_day, week_start)
    weekly_days = []
    target = None
    for d in days:
        s = schedule_for(habit, d)
        if s is None or s.schedule_type != "weekly_target" or not is_active(habit, d):
            continue
        target = s.weekly_target or 1  # the last version in the week wins
        if not is_paused(habit, d):
            weekly_days.append((d, s))
    if target is None:
        return None
    sessions = sum(1 for d, s in weekly_days if d <= today and meets_target(s, checkins.get(d)))
    available = len(weekly_days)
    required = target if available >= 7 else math.ceil(target * available / 7)
    required = min(required, available)
    return WeekProgress(
        week_start=days[0], week_end=days[-1], sessions=sessions, target=target,
        required=required, available_days=available,
        met=required > 0 and sessions >= required, finished=days[-1] < today,
    )


def current_streak(habit: Habit, today: date, week_start: int,
                   checkins: dict[date, int]) -> dict | None:
    """Schedule-aware streak.

    Daily / weekday habits: consecutive scheduled days done, counting back from today.
    Today not done yet doesn't break it; paused and unscheduled days are skipped.
    Weekly-target habits: consecutive weeks meeting the (scaled) target; the current
    week counts once met and never breaks the streak while still in progress.
    A streak stops where the schedule type changes.
    """
    schedule = schedule_for(habit, min(today, habit.archived_on - timedelta(days=1))
                            if habit.archived_on else today)
    if schedule is None:
        return None
    if schedule.schedule_type == "weekly_target":
        count, week = 0, week_start_of(today, week_start)
        for _ in range(520):
            if week + timedelta(days=6) < habit.start_date:
                break
            progress = week_progress(habit, week, today, week_start, checkins)
            if progress is None:
                break
            if progress.met:
                count += 1
            elif progress.finished and progress.required > 0:
                break
            week -= timedelta(days=7)
        return {"unit": "weeks", "value": count}

    count, day = 0, today
    for _ in range(3660):
        if day < habit.start_date:
            break
        s = schedule_for(habit, day)
        if s is None or s.schedule_type == "weekly_target":
            break
        status = day_status(habit, day, today, checkins)
        if status == "done":
            count += 1
        elif status == "missed":
            break
        day -= timedelta(days=1)
    return {"unit": "days", "value": count}


# ---------- loading ----------

def _load(db: Session, include_archived: bool = True) -> list[Habit]:
    stmt = (select(Habit)
            .options(selectinload(Habit.schedules), selectinload(Habit.pauses))
            .order_by(Habit.created_at))
    if not include_archived:
        stmt = stmt.where(Habit.archived_on.is_(None))
    return list(db.scalars(stmt))


def get_habit(db: Session, habit_id: uuid.UUID, lock: bool = False) -> Habit:
    stmt = select(Habit).where(Habit.id == habit_id).options(
        selectinload(Habit.schedules), selectinload(Habit.pauses))
    if lock:
        stmt = stmt.with_for_update()
    habit = db.scalars(stmt).one_or_none()
    if habit is None:
        raise not_found("Habit")
    return habit


def checkin_map(db: Session, habit_ids: list[uuid.UUID], start: date, end: date) -> dict[uuid.UUID, dict[date, int]]:
    result: dict[uuid.UUID, dict[date, int]] = {h: {} for h in habit_ids}
    if not habit_ids:
        return result
    rows = db.execute(
        select(HabitCheckin.habit_id, HabitCheckin.checkin_date, HabitCheckin.value)
        .where(HabitCheckin.habit_id.in_(habit_ids),
               HabitCheckin.checkin_date >= start, HabitCheckin.checkin_date <= end)
    ).all()
    for habit_id, d, v in rows:
        result[habit_id][d] = v
    return result


def habit_out(habit: Habit, today: date) -> HabitOut:
    return HabitOut(
        id=habit.id, name=habit.name, description=habit.description, kind=habit.kind,
        unit=habit.unit, start_date=habit.start_date, archived_on=habit.archived_on,
        source_inbox_item_id=habit.source_inbox_item_id,
        current_schedule=(ScheduleOut.model_validate(s) if (s := schedule_for(habit, today))
                          else (ScheduleOut.model_validate(habit.schedules[-1]) if habit.schedules else None)),
        schedules=[ScheduleOut.model_validate(s) for s in habit.schedules],
        pauses=[PauseOut.model_validate(p) for p in habit.pauses],
        paused_today=is_paused(habit, today),
        created_at=habit.created_at,
    )


# ---------- changes ----------

def _schedule_row(habit_id: uuid.UUID, kind: str, schedule: ScheduleIn, start: date) -> HabitSchedule:
    return HabitSchedule(
        habit_id=habit_id, effective_from=start, effective_to=None,
        schedule_type=schedule.schedule_type, weekdays=schedule.weekdays,
        weekly_target=schedule.weekly_target,
        target_value=1 if kind == "boolean" else schedule.target_value,
    )


def create_habit(db: Session, ctx: Ctx, data: HabitCreate,
                 source_inbox_item_id: uuid.UUID | None = None) -> Habit:
    if data.id is not None:
        existing = db.get(Habit, data.id)
        if existing is not None:
            return existing
    start = data.start_date or ctx.today
    habit = Habit(id=data.id or uuid.uuid4(), name=data.name.strip(),
                  description=data.description.strip(), kind=data.kind,
                  unit=(data.unit or "").strip() or None, start_date=start,
                  source_inbox_item_id=source_inbox_item_id)
    db.add(habit)
    db.flush()
    db.add(_schedule_row(habit.id, habit.kind, data.schedule, start))
    db.flush()
    db.refresh(habit)
    return habit


def update_habit(db: Session, habit: Habit, data: HabitUpdate) -> Habit:
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        if not changes["name"] or not changes["name"].strip():
            raise invalid("name_required", "Name cannot be empty.")
        habit.name = changes["name"].strip()
    if "description" in changes:
        habit.description = (changes["description"] or "").strip()
    if "unit" in changes:
        habit.unit = (changes["unit"] or "").strip() or None
    db.flush()
    return habit


def change_schedule(db: Session, ctx: Ctx, habit: Habit, schedule: ScheduleIn,
                    effective_from: date | None) -> Habit:
    """Start a new schedule version. Days before ``effective_from`` keep the old rules."""
    start = effective_from or ctx.today
    versions = sorted(habit.schedules, key=lambda s: s.effective_from)
    latest = versions[-1] if versions else None
    if latest is not None and start < latest.effective_from:
        raise invalid("schedule_date",
                      f"Schedule changes can start on {latest.effective_from.isoformat()} or later, "
                      "so earlier days keep the schedule they had.")
    if start < habit.start_date:
        raise invalid("schedule_date", "A schedule can't start before the habit does.")
    before = None
    if latest is not None:
        before = {"schedule_type": latest.schedule_type, "weekdays": latest.weekdays,
                  "weekly_target": latest.weekly_target, "target_value": latest.target_value,
                  "effective_from": latest.effective_from.isoformat()}
    if latest is not None and latest.effective_from == start:
        # Same start day: edit that version in place.
        latest.schedule_type = schedule.schedule_type
        latest.weekdays = schedule.weekdays
        latest.weekly_target = schedule.weekly_target
        latest.target_value = 1 if habit.kind == "boolean" else schedule.target_value
    else:
        if latest is not None:
            latest.effective_to = start - timedelta(days=1)
        db.add(_schedule_row(habit.id, habit.kind, schedule, start))
    audit.record(db, "habit", habit.id, "schedule_changed", before=before,
                 after={**schedule.model_dump(), "effective_from": start.isoformat()})
    db.flush()
    db.refresh(habit)
    return habit


def pause(db: Session, ctx: Ctx, habit: Habit, start: date | None, end: date | None) -> Habit:
    start = start or ctx.today
    if end is not None and end < start:
        raise invalid("pause_dates", "A pause must end on or after its start date.")
    for p in habit.pauses:
        p_end = p.end_date or date.max
        new_end = end or date.max
        if p.start_date <= new_end and start <= p_end:
            raise conflict("pause_overlap", "This overlaps an existing pause.")
    db.add(HabitPause(habit_id=habit.id, start_date=start, end_date=end))
    audit.record(db, "habit", habit.id, "paused",
                 after={"start_date": start.isoformat(), "end_date": end.isoformat() if end else None})
    db.flush()
    db.refresh(habit)
    return habit


def resume(db: Session, ctx: Ctx, habit: Habit, on: date | None) -> Habit:
    """End the pause that covers ``on`` (default today) so that day is active again."""
    on = on or ctx.today
    current = next((p for p in habit.pauses
                    if p.start_date <= on and (p.end_date is None or on <= p.end_date)), None)
    if current is None:
        current = next((p for p in habit.pauses if p.end_date is None), None)
    if current is None:
        return habit
    if current.start_date >= on:
        db.delete(current)  # resumed before the pause took effect
    else:
        current.end_date = on - timedelta(days=1)
    audit.record(db, "habit", habit.id, "resumed", after={"date": on.isoformat()})
    db.flush()
    db.refresh(habit)
    return habit


def archive(db: Session, ctx: Ctx, habit: Habit) -> Habit:
    if habit.archived_on is None:
        habit.archived_on = ctx.today + timedelta(days=1)  # today still counts as it was
        habit.archived_at = ctx.now
        audit.record(db, "habit", habit.id, "archived")
        db.flush()
    return habit


def unarchive(db: Session, habit: Habit) -> Habit:
    if habit.archived_on is not None:
        habit.archived_on = None
        habit.archived_at = None
        audit.record(db, "habit", habit.id, "unarchived")
        db.flush()
    return habit


def set_checkin(db: Session, ctx: Ctx, habit: Habit, day: date, value: int) -> int:
    """Record the check-in for a day. Upsert: repeating it can never double-count."""
    if day > ctx.today:
        raise invalid("future_date", "You can't check in for a future day.")
    if day < habit.start_date:
        raise invalid("before_start", "This habit hadn't started on that day.")
    if habit.kind == "boolean" and value != 1:
        raise invalid("boolean_value", "Yes/no habits are checked in with value 1. Remove the check-in to undo.")
    now = utcnow()
    db.execute(
        insert(HabitCheckin)
        .values(id=uuid.uuid4(), habit_id=habit.id, checkin_date=day, value=value,
                created_at=now, updated_at=now)
        .on_conflict_do_update(constraint="uq_habit_checkins_habit_date",
                               set_={"value": value, "updated_at": now})
    )
    db.flush()
    return value


def clear_checkin(db: Session, habit: Habit, day: date) -> None:
    row = db.scalars(select(HabitCheckin).where(
        HabitCheckin.habit_id == habit.id, HabitCheckin.checkin_date == day)).one_or_none()
    if row is not None:
        db.delete(row)
        db.flush()


# ---------- views ----------

def day_view(db: Session, ctx: Ctx, day: date) -> dict:
    # Habits that existed on that day (archived habits still show on their past days).
    habits = [h for h in _load(db)
              if h.start_date <= day and (h.archived_on is None or day < h.archived_on)]
    lookback = min([day] + [h.start_date for h in habits]) if habits else day
    lookback = max(lookback, ctx.today - timedelta(days=3660))
    week = week_dates(day, ctx.week_start)
    cmap = checkin_map(db, [h.id for h in habits], min(lookback, week[0]), max(ctx.today, week[-1]))
    scheduled, weekly, other = [], [], []
    for h in habits:
        checkins = cmap[h.id]
        status = day_status(h, day, ctx.today, checkins)
        schedule = schedule_for(h, day)
        item = {
            "habit": habit_out(h, ctx.today),
            "status": status,
            "value": checkins.get(day),
            "target_value": schedule.target_value if schedule else None,
            "schedule_type": schedule.schedule_type if schedule else None,
            "streak": current_streak(h, ctx.today, ctx.week_start, checkins),
            "week": None,
        }
        if schedule and schedule.schedule_type == "weekly_target" and status != "paused":
            wp = week_progress(h, day, ctx.today, ctx.week_start, checkins)
            item["week"] = wp.__dict__ if wp else None
            weekly.append(item)
        elif status in SCHEDULED_STATUSES:
            scheduled.append(item)
        else:
            other.append(item)
    done = sum(1 for i in scheduled if i["status"] == "done")
    return {
        "date": day,
        "today": ctx.today,
        "scheduled": scheduled,
        "weekly": weekly,
        "other": other,
        "progress": {"done": done, "scheduled": len(scheduled),
                     "pct": (200 * done + len(scheduled)) // (2 * len(scheduled)) if scheduled else None},
    }


def calendar(db: Session, ctx: Ctx, start: date, end: date) -> list[dict]:
    if end < start or (end - start).days > 123:
        raise invalid("range", "Choose a range of up to about four months.")
    habits = _load(db)
    cmap = checkin_map(db, [h.id for h in habits], start, end)
    out = []
    for h in habits:
        if h.start_date > end or (h.archived_on is not None and h.archived_on <= start):
            continue
        days = [{"date": d, "status": day_status(h, d, ctx.today, cmap[h.id]),
                 "value": cmap[h.id].get(d)} for d in date_range(start, end)]
        out.append({"habit": habit_out(h, ctx.today), "days": days})
    return out


def insights(db: Session, ctx: Ctx, start: date, end: date) -> dict:
    """Consistency over [start, end]. Today counts only once done (it isn't over yet)."""
    end_eval = min(end, ctx.today)
    habits = _load(db)
    cmap = checkin_map(db, [h.id for h in habits], start, end_eval) if end_eval >= start else {}
    rows = []
    totals = {"scheduled": 0, "completed": 0}
    for h in habits:
        if end_eval < start or h.start_date > end_eval or (h.archived_on and h.archived_on <= start):
            continue
        checkins = cmap.get(h.id, {})
        counts = {k: 0 for k in ("done", "weekly_done", "missed", "pending", "paused", "extra",
                                 "open", "not_scheduled", "inactive", "future")}
        for d in date_range(start, end_eval):
            status = day_status(h, d, ctx.today, checkins)
            version = schedule_for(h, d)
            if status == "done" and version is not None and version.schedule_type == "weekly_target":
                status = "weekly_done"  # weekly habits are judged per week, below
            counts[status] += 1
        weekly = None
        weekly_schedule_seen = any(s.schedule_type == "weekly_target" for s in h.schedules)
        if weekly_schedule_seen:
            weeks_met = weeks_evaluated = sessions = 0
            week = week_start_of(start, ctx.week_start)
            if week < start:
                week += timedelta(days=7)  # only whole weeks inside the range
            while week + timedelta(days=6) <= end_eval and week + timedelta(days=6) < ctx.today:
                wp = week_progress(h, week, ctx.today, ctx.week_start, checkins)
                if wp is not None and wp.required > 0:
                    weeks_evaluated += 1
                    weeks_met += 1 if wp.met else 0
                    sessions += wp.sessions
                week += timedelta(days=7)
            weekly = {"weeks_evaluated": weeks_evaluated, "weeks_met": weeks_met, "sessions": sessions}
        # Scheduled days that are finished: done + missed. Today's pending check-in is left out.
        scheduled_days = counts["done"] + counts["missed"]
        completed_days = counts["done"]
        totals["scheduled"] += scheduled_days
        totals["completed"] += completed_days
        rows.append({
            "habit_id": h.id, "name": h.name, "archived": h.archived_on is not None,
            "scheduled_days": scheduled_days, "completed_days": completed_days,
            "missed_days": counts["missed"], "pending_today": counts["pending"],
            "paused_days": counts["paused"], "extra_checkins": counts["extra"],
            "consistency_pct": (200 * completed_days + scheduled_days) // (2 * scheduled_days) if scheduled_days else None,
            "weekly": weekly,
        })
    return {"start": start, "end": end, "evaluated_through": end_eval, "habits": rows,
            "totals": {**totals, "pct": (200 * totals["completed"] + totals["scheduled"]) // (2 * totals["scheduled"])
                       if totals["scheduled"] else None}}

