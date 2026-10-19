"""Calendar-day helpers.

Rules used everywhere in the app:

* Instants (created_at, completed_at, ...) are stored in UTC.
* "Which day is it?" is always answered in the user's configured timezone.
* Day arithmetic is done on ``date`` values, never by adding 24 hours to an
  instant, so 23-hour and 25-hour daylight-saving days are handled correctly.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones


def is_valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return name in available_timezones()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_date_of(instant: datetime, tz_name: str) -> date:
    """The local calendar date on which a UTC instant falls."""
    if instant.tzinfo is None:
        raise ValueError("instant must be timezone-aware")
    return instant.astimezone(ZoneInfo(tz_name)).date()


def local_day_bounds_utc(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """UTC instants for the start of ``day`` and the start of the next day.

    The gap between them is 23 or 25 hours on daylight-saving change days.
    """
    zone = ZoneInfo(tz_name)
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def week_start_of(day: date, week_start: int) -> date:
    """First day of the week containing ``day``. week_start: 0=Monday ... 6=Sunday."""
    return day - timedelta(days=(day.weekday() - week_start) % 7)


def week_dates(day: date, week_start: int) -> list[date]:
    first = week_start_of(day, week_start)
    return [first + timedelta(days=i) for i in range(7)]


def date_range(start: date, end: date) -> list[date]:
    """Inclusive list of dates."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def runs_past_midnight(timeline_start: time, timeline_end: time) -> bool:
    return timeline_end < timeline_start


def logical_today(instant: datetime, tz_name: str, timeline_start: time, timeline_end: time) -> date:
    """The user's current day. For a timeline that runs past midnight (e.g. 11:00-02:00),
    the hours before timeline_end still belong to the previous day."""
    local = instant.astimezone(ZoneInfo(tz_name))
    if runs_past_midnight(timeline_start, timeline_end) and local.time() < timeline_end:
        return local.date() - timedelta(days=1)
    return local.date()
