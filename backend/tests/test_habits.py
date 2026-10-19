"""Habit schedules, pauses, weekly targets, schedule changes and check-ins."""

from tests.conftest import ok

# 2 March 2026 is a Monday.


def habit(client, name="Read", kind="boolean", start="2026-03-02", **schedule):
    body = {"name": name, "kind": kind, "start_date": start,
            "schedule": {"schedule_type": "daily", **schedule}}
    return ok(client.post("/api/habits", json=body), 201)


def check(client, h, d, value=1, status=200):
    return ok(client.put(f"/api/habits/{h['id']}/checkins/{d}", json={"value": value}), status)


def day(client, d):
    return ok(client.get(f"/api/habits/day?date={d}"))


def find(view, h):
    for group in ("scheduled", "weekly", "other"):
        for item in view[group]:
            if item["habit"]["id"] == h["id"]:
                return group, item
    raise AssertionError("habit not in view")


def statuses(client, h, start, end):
    cal = ok(client.get(f"/api/habits/calendar?start={start}&end={end}"))
    row = next(r for r in cal if r["habit"]["id"] == h["id"])
    return [d["status"] for d in row["days"]]


def test_daily_progress_and_streak(client, clock):
    h = habit(client)
    clock.set("2026-03-05T12:00:00Z")  # Thursday
    for d in ("2026-03-02", "2026-03-03", "2026-03-04"):
        check(client, h, d)
    view = day(client, "2026-03-05")
    group, item = find(view, h)
    assert group == "scheduled" and item["status"] == "pending"
    assert item["streak"] == {"unit": "days", "value": 3}  # today not done yet doesn't break it
    assert view["progress"] == {"done": 0, "scheduled": 1, "pct": 0}
    check(client, h, "2026-03-05")
    assert find(day(client, "2026-03-05"), h)[1]["streak"]["value"] == 4


def test_pause_days_are_not_failures(client, clock):
    h = habit(client)
    clock.set("2026-03-02T12:00:00Z")
    check(client, h, "2026-03-02")
    ok(client.post(f"/api/habits/{h['id']}/pause", json={"start_date": "2026-03-03", "end_date": "2026-03-04"}))
    clock.set("2026-03-05T12:00:00Z")
    check(client, h, "2026-03-05")
    assert statuses(client, h, "2026-03-02", "2026-03-05") == ["done", "paused", "paused", "done"]
    assert find(day(client, "2026-03-05"), h)[1]["streak"]["value"] == 2
    ins = ok(client.get("/api/insights/habits?start=2026-03-02&end=2026-03-05"))["habits"][0]
    assert ins["scheduled_days"] == 2 and ins["completed_days"] == 2 and ins["paused_days"] == 2
    assert ins["consistency_pct"] == 100


def test_open_ended_pause_and_resume(client, clock):
    h = habit(client)
    clock.set("2026-03-03T12:00:00Z")
    ok(client.post(f"/api/habits/{h['id']}/pause", json={}))
    assert find(day(client, "2026-03-03"), h)[1]["status"] == "paused"
    assert client.post(f"/api/habits/{h['id']}/pause", json={}).status_code == 409  # overlapping
    clock.set("2026-03-06T12:00:00Z")
    ok(client.post(f"/api/habits/{h['id']}/resume", json={}))
    assert statuses(client, h, "2026-03-02", "2026-03-06") == ["missed", "paused", "paused", "paused", "pending"]


def test_selected_weekdays(client, clock):
    h = habit(client, "Gym", schedule_type="weekdays", weekdays=[0, 2, 4])  # Mon Wed Fri
    clock.set("2026-03-07T12:00:00Z")  # Saturday
    check(client, h, "2026-03-02")
    check(client, h, "2026-03-03")  # Tuesday: extra
    check(client, h, "2026-03-06")
    assert statuses(client, h, "2026-03-02", "2026-03-07") == [
        "done", "extra", "missed", "not_scheduled", "done", "not_scheduled"]
    assert find(day(client, "2026-03-07"), h)[1]["streak"]["value"] == 1  # Wednesday was missed
    assert find(day(client, "2026-03-07"), h)[0] == "other"  # not scheduled on Saturday


def test_weekly_target_uses_weeks_not_daily_streaks(client, clock):
    h = habit(client, "Run", schedule_type="weekly_target", weekly_target=3)
    clock.set("2026-03-11T12:00:00Z")  # Wednesday of week 2
    for d in ("2026-03-02", "2026-03-04", "2026-03-06"):  # week 1: 3 sessions
        check(client, h, d)
    check(client, h, "2026-03-10")  # week 2 so far: 1
    group, item = find(day(client, "2026-03-11"), h)
    assert group == "weekly"
    assert item["status"] == "open"  # never "missed" on individual days
    assert item["week"]["sessions"] == 1 and item["week"]["required"] == 3 and not item["week"]["met"]
    assert item["streak"] == {"unit": "weeks", "value": 1}  # week 2 in progress doesn't break it
    assert "missed" not in statuses(client, h, "2026-03-02", "2026-03-11")
    ins = ok(client.get("/api/insights/habits?start=2026-03-02&end=2026-03-15"))["habits"][0]
    assert ins["weekly"] == {"weeks_evaluated": 1, "weeks_met": 1, "sessions": 3}
    assert ins["scheduled_days"] == 0  # weekly habits aren't judged per day


def test_weekly_target_scaled_for_partial_week(client, clock):
    h = habit(client, "Swim", start="2026-03-05", schedule_type="weekly_target", weekly_target=3)
    clock.set("2026-03-08T12:00:00Z")
    check(client, h, "2026-03-06")
    check(client, h, "2026-03-07")
    week = find(day(client, "2026-03-08"), h)[1]["week"]
    assert week["available_days"] == 4 and week["required"] == 2 and week["met"]


def test_schedule_change_preserves_history(client, clock):
    h = habit(client)  # daily from Monday
    clock.set("2026-03-04T12:00:00Z")  # Wednesday; Monday done, Tuesday missed
    check(client, h, "2026-03-02")
    ok(client.put(f"/api/habits/{h['id']}/schedule",
                  json={"schedule": {"schedule_type": "weekdays", "weekdays": [0]}}))  # Mondays only, from today
    clock.set("2026-03-06T12:00:00Z")
    assert statuses(client, h, "2026-03-02", "2026-03-06") == [
        "done", "missed", "not_scheduled", "not_scheduled", "not_scheduled"]
    detail = next(x for x in ok(client.get("/api/habits")) if x["id"] == h["id"])
    assert len(detail["schedules"]) == 2
    assert detail["schedules"][0]["effective_to"] == "2026-03-03"
    # Rewriting days before the latest version is refused.
    r = client.put(f"/api/habits/{h['id']}/schedule",
                   json={"schedule": {"schedule_type": "daily"}, "effective_from": "2026-03-02"})
    assert r.status_code == 422


def test_duplicate_checkins_never_double_count(client, clock):
    h = habit(client, "Water", kind="count", unit="glasses", target_value=8)
    check(client, h, "2026-03-02", 5)
    check(client, h, "2026-03-02", 5)
    check(client, h, "2026-03-02", 8)
    item = find(day(client, "2026-03-02"), h)[1]
    assert item["value"] == 8 and item["status"] == "done"
    cal = ok(client.get("/api/habits/calendar?start=2026-03-02&end=2026-03-02"))
    assert cal[0]["days"][0]["value"] == 8


def test_duration_habit_target_and_checkin_rules(client, clock):
    h = habit(client, "Reading", kind="duration", target_value=20)
    check(client, h, "2026-03-02", 15)
    assert find(day(client, "2026-03-02"), h)[1]["status"] == "pending"
    check(client, h, "2026-03-02", 25)
    assert find(day(client, "2026-03-02"), h)[1]["status"] == "done"
    assert client.put(f"/api/habits/{h['id']}/checkins/2026-03-09", json={"value": 5}).status_code == 422
    b = habit(client, "Meditate")
    assert client.put(f"/api/habits/{b['id']}/checkins/2026-03-02", json={"value": 3}).status_code == 422
    assert client.delete(f"/api/habits/{b['id']}/checkins/2026-03-02").status_code == 204


def test_archived_habit_keeps_history_and_stops_counting(client, clock):
    h = habit(client)
    clock.set("2026-03-03T12:00:00Z")
    check(client, h, "2026-03-02")
    ok(client.post(f"/api/habits/{h['id']}/archive"))
    assert ok(client.get("/api/habits")) == []
    assert len(ok(client.get("/api/habits?include_archived=true"))) == 1
    clock.set("2026-03-06T12:00:00Z")
    # Archived on Tuesday: Tuesday still counted as it was, later days are inactive.
    assert statuses(client, h, "2026-03-02", "2026-03-05") == ["done", "missed", "inactive", "inactive"]


def test_habit_validation(client):
    bad = {"name": "X", "schedule": {"schedule_type": "weekdays", "weekdays": []}}
    assert client.post("/api/habits", json=bad).status_code == 422
    bad = {"name": "X", "schedule": {"schedule_type": "weekly_target"}}
    assert client.post("/api/habits", json=bad).status_code == 422
