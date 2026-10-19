from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Ctx, get_ctx, load_settings
from app.errors import invalid
from app.schemas import SettingsOut, SettingsUpdate
from app.timeutil import is_valid_timezone, logical_today

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> SettingsOut:
    s = load_settings(db)
    return _out(s, ctx)


def _out(s, ctx: Ctx) -> SettingsOut:
    return SettingsOut(timezone=s.timezone, timezone_confirmed=s.timezone_confirmed, week_start=s.week_start,
                       timeline_start=s.timeline_start, timeline_end=s.timeline_end, currency=s.currency,
                       today=logical_today(ctx.now, s.timezone, s.timeline_start, s.timeline_end), now=ctx.now)


@router.put("", response_model=SettingsOut)
def update_settings(data: SettingsUpdate, db: Session = Depends(get_db),
                    ctx: Ctx = Depends(get_ctx)) -> SettingsOut:
    s = load_settings(db)
    if data.timezone is not None:
        if not is_valid_timezone(data.timezone):
            raise invalid("timezone", f"'{data.timezone}' is not a recognised timezone (e.g. Europe/London).")
        s.timezone = data.timezone
        s.timezone_confirmed = True
    if data.timezone_confirmed is not None:
        s.timezone_confirmed = data.timezone_confirmed
    if data.week_start is not None:
        s.week_start = data.week_start
    if data.currency is not None:
        s.currency = data.currency
    start = data.timeline_start or s.timeline_start
    end = data.timeline_end or s.timeline_end
    if start.replace(second=0, microsecond=0) == end.replace(second=0, microsecond=0):
        raise invalid("timeline", "The timeline must start and end at different times.")
    s.timeline_start, s.timeline_end = start.replace(second=0, microsecond=0), end.replace(second=0, microsecond=0)
    db.commit()
    return _out(s, ctx)
