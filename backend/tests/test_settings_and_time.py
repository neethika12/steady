"""Timezone, daylight-saving and week-start behaviour."""

from datetime import date, datetime, timezone

from app.timeutil import local_date_of, local_day_bounds_utc, week_start_of
from tests.conftest import ok


def test_health(client):
    assert ok(client.get("/api/health")) == {"status": "ok"}


def test_settings_default_update_and_validation(client):
    s = ok(client.get("/api/settings"))
    assert s["timezone"] == "UTC" and s["week_start"] == 0 and s["timezone_confirmed"] is False
    s = ok(client.put("/api/settings", json={"timezone": "Europe/Paris", "week_start": 6}))
    assert s["timezone"] == "Europe/Paris" and s["week_start"] == 6 and s["timezone_confirmed"] is True
    assert client.put("/api/settings", json={"timezone": "Mars/Base"}).status_code == 422
    assert client.put("/api/settings", json={"week_start": 9}).status_code == 422


def test_today_follows_configured_timezone(client, clock):
    clock.set("2026-03-10T03:30:00Z")  # 23:30 on 9 March in New York
    assert ok(client.get("/api/settings"))["today"] == "2026-03-10"
    s = ok(client.put("/api/settings", json={"timezone": "America/New_York"}))
    assert s["today"] == "2026-03-09"
    clock.set("2026-03-10T11:30:00Z")  # 00:30 on 11 March in Auckland (UTC+13)
    ok(client.put("/api/settings", json={"timezone": "Pacific/Auckland"}))
    assert ok(client.get("/api/settings"))["today"] == "2026-03-11"


def test_dst_days_have_23_and_25_hours():
    start, end = local_day_bounds_utc(date(2026, 3, 8), "America/New_York")  # spring forward
    assert (end - start).total_seconds() == 23 * 3600
    start, end = local_day_bounds_utc(date(2026, 11, 1), "America/New_York")  # fall back
    assert (end - start).total_seconds() == 25 * 3600
    start, end = local_day_bounds_utc(date(2026, 3, 29), "Europe/London")
    assert (end - start).total_seconds() == 23 * 3600


def test_local_date_around_dst_and_midnight():
    tz = "America/New_York"
    # 01:30 local happens twice on 1 Nov 2026; both instants are on the same local date.
    assert local_date_of(datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc), tz) == date(2026, 11, 1)
    assert local_date_of(datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc), tz) == date(2026, 11, 1)
    # Last second of 8 March local (EDT, UTC-4) vs first second of 9 March.
    assert local_date_of(datetime(2026, 3, 9, 3, 59, 59, tzinfo=timezone.utc), tz) == date(2026, 3, 8)
    assert local_date_of(datetime(2026, 3, 9, 4, 0, 0, tzinfo=timezone.utc), tz) == date(2026, 3, 9)


def test_week_start_preference():
    wednesday = date(2026, 3, 4)
    assert week_start_of(wednesday, 0) == date(2026, 3, 2)  # Monday
    assert week_start_of(wednesday, 6) == date(2026, 3, 1)  # Sunday
    assert week_start_of(date(2026, 3, 1), 0) == date(2026, 2, 23)


def test_week_view_respects_week_start(client):
    ok(client.put("/api/settings", json={"week_start": 6}))
    week = ok(client.get("/api/plans/week?date=2026-03-04"))
    assert week["start"] == "2026-03-01" and week["end"] == "2026-03-07"


def test_completion_timestamp_is_the_real_instant_in_utc(client, clock):
    ok(client.put("/api/settings", json={"timezone": "America/New_York"}))
    clock.set("2026-03-03T02:00:00Z")  # 21:00 on Monday 2 March in New York
    ok(client.post("/api/tasks", json={"title": "Late task", "planned_date": "2026-03-02"}), 201)
    plan = ok(client.get("/api/plans/day?date=2026-03-02"))["plans"][0]
    done = ok(client.put(f"/api/plans/{plan['id']}/review", json={"outcome": "completed"}))
    assert done["completed_at"].startswith("2026-03-03T02:00")  # stored as UTC
    assert done["plan_date"] == "2026-03-02"  # credited to the local day


def test_timeline_hours_default_and_validation(client):
    s = ok(client.get("/api/settings"))
    assert (s["timeline_start"], s["timeline_end"]) == ("07:00:00", "22:00:00")
    s = ok(client.put("/api/settings", json={"timeline_start": "11:00", "timeline_end": "02:00"}))
    assert (s["timeline_start"], s["timeline_end"]) == ("11:00:00", "02:00:00")
    assert client.put("/api/settings", json={"timeline_start": "09:00", "timeline_end": "09:00"}).status_code == 422


def test_night_owl_day_ends_at_the_end_of_their_timeline(client, clock):
    ok(client.put("/api/settings", json={"timeline_start": "11:00", "timeline_end": "02:00"}))
    clock.set("2026-03-03T01:30:00Z")  # 1:30 am on Tuesday (UTC)
    assert ok(client.get("/api/settings"))["today"] == "2026-03-02"  # still Monday for a night owl
    clock.set("2026-03-03T02:00:00Z")
    assert ok(client.get("/api/settings"))["today"] == "2026-03-03"  # the new day starts at 2 am
    ok(client.put("/api/settings", json={"timeline_start": "07:00", "timeline_end": "22:00"}))
    clock.set("2026-03-03T01:30:00Z")
    assert ok(client.get("/api/settings"))["today"] == "2026-03-03"  # normal timeline: midnight


def test_past_midnight_tasks_sort_last_and_ranges_need_a_night_timeline(client):
    body = {"title": "Late session", "planned_date": "2026-03-02", "planned_time": "23:30", "planned_end_time": "00:30"}
    r = client.post("/api/tasks", json=body)
    assert r.status_code == 422  # default 7 am - 10 pm timeline: no running past midnight
    ok(client.put("/api/settings", json={"timeline_start": "11:00", "timeline_end": "02:00"}))
    ok(client.post("/api/tasks", json=body), 201)
    ok(client.post("/api/tasks", json={"title": "After midnight", "planned_date": "2026-03-02", "planned_time": "01:00"}), 201)
    ok(client.post("/api/tasks", json={"title": "Lunch", "planned_date": "2026-03-02", "planned_time": "12:00"}), 201)
    titles = [p["task"]["title"] for p in ok(client.get("/api/plans/day?date=2026-03-02"))["plans"]]
    assert titles == ["Lunch", "Late session", "After midnight"]  # in the order of the user's day
