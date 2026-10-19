"""Opt-in demo data. Never runs automatically.

    docker compose exec backend python -m scripts.seed_demo you@example.com

Adds demo records to that (existing) account. It refuses if the account already contains any
tasks, habits, inbox items or journal entries, so demo records can never be mixed into personal data. Every demo
record is labelled "[demo]". To get rid of demo data, see "Removing demo data" in the README.
"""

import sys
from datetime import timedelta

from sqlalchemy import func, select

from app.db import SessionLocal
from app.deps import Ctx, load_settings
from app.models import Habit, InboxItem, JournalEntry, Task, User
from app.schemas import HabitCreate, JournalSave, ReviewIn, ScheduleIn, TaskCreate
from app.services import auth, habits, journal, tasks
from app.timeutil import local_date_of, utc_now


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.seed_demo you@example.com   (the account to add demo data to)")
        return 2
    with SessionLocal() as db:
        user = db.scalars(select(User).where(User.email == sys.argv[1].strip().lower())).first()
        if user is None:
            print("No account with that email. Create it in the app first.")
            return 1
        auth.act_as(db, user.id)
        existing = sum(db.scalar(select(func.count()).select_from(m)) for m in (Task, Habit, InboxItem, JournalEntry))
        if existing:
            print(f"Refusing: that account already has {existing} records. Demo data is only added to an empty account.")
            return 1
        s = load_settings(db)
        now = utc_now()
        today = local_date_of(now, s.timezone)
        ctx = Ctx(now=now, today=today, timezone=s.timezone, week_start=s.week_start)
        yesterday = today - timedelta(days=1)

        # Undated tasks: these appear in the To-Do Inbox panel.
        tasks.create_task(db, ctx, TaskCreate(title="[demo] Look into a cheaper phone plan"))
        tasks.create_task(db, ctx, TaskCreate(title="[demo] Set up a weekly review on Sunday evenings"))
        t1, _ = tasks.create_task(db, ctx, TaskCreate(title="[demo] Update resume", priority="high",
                                                      estimated_minutes=60, planned_date=yesterday))
        tasks.create_task(db, ctx, TaskCreate(title="[demo] Book dentist appointment", estimated_minutes=10, planned_date=today))
        tasks.create_task(db, ctx, TaskCreate(title="[demo] Plan weekend trip", priority="low", estimated_minutes=45))
        plan = tasks.plan_on(db, t1.id, yesterday)
        r = ReviewIn(outcome="not_completed", reason="not_enough_time", reason_note="[demo] The slides took all afternoon")
        tasks.review_plan(db, ctx, plan, r.outcome, r.reason, r.reason_note)
        tasks.follow_up(db, ctx, plan, "reschedule", today, None)
        h = habits.create_habit(db, ctx, HabitCreate(name="[demo] Read", kind="duration", start_date=today - timedelta(days=6),
                                                     schedule=ScheduleIn(schedule_type="daily", target_value=20)))
        for d in (6, 5, 3, 1):
            habits.set_checkin(db, ctx, h, today - timedelta(days=d), 25)
        habits.create_habit(db, ctx, HabitCreate(name="[demo] Run", start_date=today - timedelta(days=6),
                                                 schedule=ScheduleIn(schedule_type="weekly_target", weekly_target=3)))
        journal.save_entry(db, ctx, yesterday, JournalSave(base_version=0, mood=4, energy=3,
                           body="[demo] A steady day. Finished the slides, ran out of time for the resume."))
        db.commit()
    print("Demo data added (all labelled [demo]).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
