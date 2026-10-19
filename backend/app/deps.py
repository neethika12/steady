"""Request context: the current instant and the user's local "today"."""

from dataclasses import dataclass
from datetime import date, datetime, time

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_config
from app.db import get_db
from app.models import AppSettings
from app.timeutil import is_valid_timezone, logical_today, runs_past_midnight, utc_now


def get_now() -> datetime:
    """The current UTC instant. Tests override this dependency to freeze time."""
    return utc_now()


def load_settings(db: Session) -> AppSettings:
    """Return the signed-in user's settings row, creating it on first use.

    ``ON CONFLICT DO NOTHING`` makes simultaneous first requests safe. The row's user_id is
    filled in by the database (row-level security only shows the user's own row).
    """
    row = db.scalars(select(AppSettings)).first()
    if row is None:
        tz = get_config().default_timezone
        if not is_valid_timezone(tz):
            tz = "UTC"
        db.execute(
            insert(AppSettings)
            .values(timezone=tz, timezone_confirmed=False, week_start=0,
                    timeline_start=time(7, 0), timeline_end=time(22, 0), currency="USD",
                    created_at=utc_now(), updated_at=utc_now())
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        db.commit()
        row = db.scalars(select(AppSettings)).one()
    return row


@dataclass
class Ctx:
    now: datetime
    today: date
    timezone: str
    week_start: int
    timeline_start: time = time(7, 0)
    timeline_end: time = time(22, 0)

    @property
    def past_midnight(self) -> bool:
        """True when the user's day (timeline) runs past midnight."""
        return runs_past_midnight(self.timeline_start, self.timeline_end)


def get_ctx(db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> Ctx:
    settings = load_settings(db)
    return Ctx(
        now=now,
        today=logical_today(now, settings.timezone, settings.timeline_start, settings.timeline_end),
        timezone=settings.timezone,
        week_start=settings.week_start,
        timeline_start=settings.timeline_start,
        timeline_end=settings.timeline_end,
    )
