"""Dated task history: carry-forward, reviews, corrections and completion maths."""

from datetime import date

from app.services.tasks import _PlanFacts, compute_day_stats
from tests.conftest import ok

MON, TUE, WED = "2026-03-02", "2026-03-03", "2026-03-04"


def day(client, d):
    return ok(client.get(f"/api/plans/day?date={d}"))


def new_task(client, title="Update resume", planned=MON, **extra):
    return ok(client.post("/api/tasks", json={"title": title, "planned_date": planned, **extra}), 201)


def review(client, plan_id, outcome, reason=None, status=200, **extra):
    if outcome == "not_completed":
        extra.setdefault("reason_note", "Ran out of time")
    return ok(client.put(f"/api/plans/{plan_id}/review",
                         json={"outcome": outcome, "reason": reason, **extra}), status)


def test_carry_forward_preserves_monday_outcome(client, clock):
    """The README example: Monday not completed, Tuesday carried forward and completed."""
    clock.set("2026-03-02T20:00:00Z")  # Monday evening
    task = new_task(client)
    monday_plan = day(client, MON)["plans"][0]
    review(client, monday_plan["id"], "not_completed", "not_enough_time")
    ok(client.post(f"/api/plans/{monday_plan['id']}/follow-up", json={"action": "reschedule", "date": TUE}))

    clock.set("2026-03-03T18:00:00Z")  # Tuesday
    tuesday_plan = day(client, TUE)["plans"][0]
    assert tuesday_plan["carried_from_date"] == MON
    assert tuesday_plan["times_carried"] == 1
    review(client, tuesday_plan["id"], "completed")

    monday = day(client, MON)
    assert monday["plans"][0]["state"] == "not_completed"
    assert monday["plans"][0]["reason"] == "not_enough_time"
    assert monday["plans"][0]["carried_to_date"] == TUE
    assert monday["plans"][0]["follow_up"] == "rescheduled"
    assert monday["stats"]["completed"] == 0 and monday["stats"]["counted"] == 1
    assert monday["stats"]["completion_pct"] == 0

    tuesday = day(client, TUE)
    assert tuesday["stats"]["completed"] == 1 and tuesday["stats"]["completion_pct"] == 100
    assert tuesday["stats"]["carried_in"] == 1
    assert tuesday["plans"][0]["completed_at"].startswith("2026-03-03T18:00")

    history = ok(client.get(f"/api/tasks/{task['id']}"))
    assert [p["plan_date"] for p in history["plans"]] == [MON, TUE]
    assert history["task"]["status"] == "completed"


def test_review_never_reschedules_automatically(client):
    new_task(client)
    plan = day(client, MON)["plans"][0]
    review(client, plan["id"], "not_completed", "too_large")
    task = ok(client.get(f"/api/tasks/{plan['task_id']}"))
    assert task["task"]["planned_date"] is None
    assert len(task["plans"]) == 1
    needs = ok(client.get("/api/tasks?view=needs_decision"))
    assert [t["id"] for t in needs] == [plan["task_id"]]
    waiting = ok(client.get("/api/plans/needs-decision"))
    assert [p["id"] for p in waiting] == [plan["id"]]
    ok(client.post(f"/api/plans/{plan['id']}/follow-up", json={"action": "unscheduled"}))
    assert ok(client.get("/api/plans/needs-decision")) == []
    assert [t["id"] for t in ok(client.get("/api/tasks?view=unscheduled"))] == [plan["task_id"]]


def test_rescheduling_unreviewed_past_plan_keeps_it_in_denominator(client, clock):
    new_task(client)
    clock.set("2026-03-04T12:00:00Z")  # Wednesday; Monday was never reviewed
    plan = day(client, MON)["plans"][0]
    ok(client.put(f"/api/tasks/{plan['task_id']}/schedule", json={"planned_date": WED}))
    monday = day(client, MON)
    assert monday["plans"][0]["state"] == "awaiting_review"
    assert monday["stats"]["awaiting_review"] == 1
    assert monday["stats"]["counted"] == 1 and monday["stats"]["completion_pct"] == 0
    assert day(client, WED)["plans"][0]["carried_from_date"] == MON
    pending = ok(client.get("/api/plans/pending-reviews"))
    assert pending == [{"date": MON, "unreviewed": 1}]


def test_moving_a_future_unreviewed_plan_is_a_plain_move(client):
    task = new_task(client, planned=TUE)
    ok(client.put(f"/api/tasks/{task['id']}/schedule", json={"planned_date": WED}))
    assert day(client, TUE)["plans"] == []
    wed = day(client, WED)["plans"][0]
    assert wed["carried_from_date"] is None
    history = ok(client.get(f"/api/tasks/{task['id']}"))
    assert any(a["action"] == "moved" for a in history["audit"])


def test_not_reviewed_is_distinct_from_not_completed(client, clock):
    a = new_task(client, "A")
    new_task(client, "B")
    plans = {p["task"]["title"]: p for p in day(client, MON)["plans"]}
    review(client, plans["A"]["id"], "not_completed")  # written reason only, no tag
    today = day(client, MON)["stats"]
    assert today["not_completed"] == 1 and today["open"] == 1 and today["awaiting_review"] == 0
    clock.set("2026-03-03T12:00:00Z")
    past = day(client, MON)["stats"]
    assert past["not_completed"] == 1 and past["awaiting_review"] == 1 and past["open"] == 0
    assert past["completion_pct"] == 0 and past["counted"] == 2
    assert a["id"]


def test_correction_is_audited_and_reverts_task_status(client):
    new_task(client)
    plan = day(client, MON)["plans"][0]
    review(client, plan["id"], "completed")
    review(client, plan["id"], "completed")  # repeated submission: no change
    review(client, plan["id"], "not_completed", "waiting", correction_note="ticked by mistake")
    history = ok(client.get(f"/api/tasks/{plan['task_id']}"))
    assert history["task"]["status"] == "active"
    assert history["task"]["completed_at"] is None
    actions = [a["action"] for a in history["audit"]]
    assert actions.count("review") == 1 and actions.count("correction") == 1
    correction = next(a for a in history["audit"] if a["action"] == "correction")
    assert correction["before"]["outcome"] == "completed"
    assert correction["after"]["outcome"] == "not_completed"
    assert correction["note"] == "ticked by mistake"


def test_cannot_review_future_day(client):
    new_task(client, planned=TUE)
    plan = day(client, TUE)["plans"][0]
    r = client.put(f"/api/plans/{plan['id']}/review", json={"outcome": "completed"})
    assert r.status_code == 409


def test_cancellation_is_excluded_from_denominator_and_counted_separately(client):
    new_task(client, "Keep")
    cancel = new_task(client, "Drop")
    ok(client.post(f"/api/tasks/{cancel['id']}/cancel"))
    stats = day(client, MON)["stats"]
    assert stats["planned"] == 2 and stats["cancelled"] == 1 and stats["counted"] == 1
    states = {p["task"]["title"]: p["state"] for p in day(client, MON)["plans"]}
    assert states == {"Keep": "planned", "Drop": "cancelled"}


def test_split_follow_up_is_explicit_and_idempotent(client):
    new_task(client, "Write report", estimated_minutes=240)
    plan = day(client, MON)["plans"][0]
    review(client, plan["id"], "not_completed", "too_large")
    steps = [{"title": "Outline"}, {"title": "Draft intro", "planned_date": TUE}]
    ok(client.post(f"/api/plans/{plan['id']}/follow-up", json={"action": "split", "steps": steps}))
    ok(client.post(f"/api/tasks/{plan['task_id']}/split", json={"steps": steps}))  # repeat
    history = ok(client.get(f"/api/tasks/{plan['task_id']}"))
    assert history["task"]["status"] == "split"
    assert sorted(c["title"] for c in history["children"]) == ["Draft intro", "Outline"]
    assert [p["task"]["title"] for p in day(client, TUE)["plans"]] == ["Draft intro"]
    assert day(client, MON)["plans"][0]["state"] == "not_completed"


def test_duplicate_create_with_same_id_returns_existing(client):
    body = {"id": "6f1d7c58-3c55-4a8e-9a0b-6b3ad8a0e001", "title": "Once", "planned_date": MON}
    ok(client.post("/api/tasks", json=body), 201)
    ok(client.post("/api/tasks", json=body), 200)
    assert len(day(client, MON)["plans"]) == 1


def test_scheduling_to_a_day_with_an_existing_record_is_refused(client, clock):
    task = new_task(client)
    plan = day(client, MON)["plans"][0]
    review(client, plan["id"], "not_completed")
    ok(client.post(f"/api/plans/{plan['id']}/follow-up", json={"action": "reschedule", "date": TUE}))
    r = client.put(f"/api/tasks/{task['id']}/schedule", json={"planned_date": MON})
    assert r.status_code == 409


def test_week_view_and_batch_schedule(client):
    a = ok(client.post("/api/tasks", json={"title": "A"}), 201)
    b = ok(client.post("/api/tasks", json={"title": "B"}), 201)
    ok(client.post("/api/plans/batch", json={"date": WED, "task_ids": [a["id"], b["id"], a["id"]]}))
    week = ok(client.get(f"/api/plans/week?date={WED}"))
    assert week["start"] == MON and len(week["days"]) == 7
    assert week["days"][2]["stats"]["planned"] == 2
    assert all(d["stats"]["completion_pct"] is None for i, d in enumerate(week["days"]) if i != 2)


def test_completing_earlier_day_removes_later_unreviewed_plan(client, clock):
    task = new_task(client)
    clock.set("2026-03-03T09:00:00Z")
    ok(client.put(f"/api/tasks/{task['id']}/schedule", json={"planned_date": WED}))
    monday_plan = day(client, MON)["plans"][0]
    review(client, monday_plan["id"], "completed")  # done on Monday after all
    assert day(client, WED)["plans"] == []
    assert ok(client.get(f"/api/tasks/{task['id']}"))["task"]["status"] == "completed"


# ---- pure completion maths ----

def facts(*outcomes, est=None):
    return [_PlanFacts(date(2026, 3, 2), o, False, est) for o in outcomes]


def test_empty_day_has_no_percentage():
    s = compute_day_stats(date(2026, 3, 2), date(2026, 3, 2), [])
    assert s.planned == 0 and s.completion_pct is None and s.effort_pct is None


def test_completion_percentage_rules():
    d, today = date(2026, 3, 2), date(2026, 3, 5)
    s = compute_day_stats(d, today, facts("completed", "partial", "not_completed", None, "cancelled"))
    assert (s.planned, s.counted, s.completed) == (5, 4, 1)
    assert s.awaiting_review == 1 and s.cancelled == 1
    assert s.completion_pct == 25
    s = compute_day_stats(d, today, facts("completed", "completed", None))
    assert s.completion_pct == 67  # 66.7 rounds half-up to 67
    s = compute_day_stats(d, today, facts("cancelled"))
    assert s.counted == 0 and s.completion_pct is None


def test_effort_uses_estimates_only():
    d = date(2026, 3, 2)
    plans = [_PlanFacts(d, "completed", False, 30), _PlanFacts(d, None, False, 90),
             _PlanFacts(d, "completed", False, None)]
    s = compute_day_stats(d, d, plans)
    assert (s.estimated_minutes_planned, s.estimated_minutes_completed, s.effort_pct) == (120, 30, 25)
    assert s.plans_without_estimate == 1


def test_inbox_capture_is_an_undated_task(client):
    """The To-Do Inbox panel is simply the list of active tasks without a day."""
    body = {"id": "6f1d7c58-3c55-4a8e-9a0b-6b3ad8a0e0aa", "title": "Call the dentist"}
    ok(client.post("/api/tasks", json=body), 201)
    ok(client.post("/api/tasks", json=body), 200)  # double submit: still one task
    inbox = ok(client.get("/api/tasks?view=unscheduled"))
    assert [t["title"] for t in inbox] == ["Call the dentist"] and inbox[0]["planned_date"] is None
    ok(client.put(f"/api/tasks/{body['id']}/schedule", json={"planned_date": WED}))  # dragged onto Wednesday
    assert ok(client.get("/api/tasks?view=unscheduled")) == []
    assert [p["task"]["title"] for p in day(client, WED)["plans"]] == ["Call the dentist"]


def test_simultaneous_identical_captures_create_one_task(client):
    """Four identical submissions at the same moment (double click, retry) save one task."""
    import threading

    body = {"id": "6f1d7c58-3c55-4a8e-9a0b-6b3ad8a0e0bb", "title": "Pay rent"}
    statuses, barrier = [], threading.Barrier(4)

    def submit():
        barrier.wait()
        statuses.append(client.post("/api/tasks", json=body).status_code)

    threads = [threading.Thread(target=submit) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [200, 200, 200, 201]
    assert [t["title"] for t in ok(client.get("/api/tasks?view=unscheduled"))] == ["Pay rent"]



def test_not_completed_needs_a_written_reason(client):
    new_task(client)
    plan = day(client, MON)["plans"][0]
    for note in (None, "", "  "):
        r = client.put(f"/api/plans/{plan['id']}/review", json={"outcome": "not_completed", "reason_note": note})
        assert r.status_code == 422
    r = client.put(f"/api/plans/{plan['id']}/review", json={"outcome": "partial", "reason_note": "half"})
    assert r.status_code == 422  # only Completed / Not completed can be recorded now
    done = review(client, plan["id"], "not_completed", reason_note="Waited all day for the client's files")
    assert done["reason_note"] == "Waited all day for the client's files" and done["reason"] is None


def test_time_of_day_is_optional_sorted_and_carried(client, clock):
    late = new_task(client, "Evening call", planned_time="18:30")
    new_task(client, "Anytime chore")
    new_task(client, "Morning run", planned_time="07:00")
    plans = day(client, MON)["plans"]
    assert [(p["task"]["title"], p["planned_time"]) for p in plans] == [
        ("Morning run", "07:00:00"), ("Evening call", "18:30:00"), ("Anytime chore", None)]
    # Changing only the time keeps the same record and is audited.
    ok(client.put(f"/api/tasks/{late['id']}/schedule", json={"planned_date": MON, "planned_time": "19:00"}))
    assert day(client, MON)["plans"][1]["planned_time"] == "19:00:00"
    history = ok(client.get(f"/api/tasks/{late['id']}"))
    assert any(a["action"] == "time_changed" for a in history["audit"])
    # Not done -> carried to Tuesday: the time comes along unless you change it.
    plan = next(p for p in day(client, MON)["plans"] if p["task_id"] == late["id"])
    review(client, plan["id"], "not_completed")
    ok(client.put(f"/api/tasks/{late['id']}/schedule", json={"planned_date": TUE}))
    assert day(client, TUE)["plans"][0]["planned_time"] == "19:00:00"
    ok(client.put(f"/api/tasks/{late['id']}/schedule", json={"planned_date": TUE, "planned_time": None}))
    assert day(client, TUE)["plans"][0]["planned_time"] is None  # explicitly "anytime"


def test_restore_puts_a_task_back_on_the_day_it_was_cancelled_from(client):
    t = new_task(client, planned_time="14:00")  # planned for Monday at 2 pm
    ok(client.post(f"/api/tasks/{t['id']}/cancel"))
    assert day(client, MON)["plans"][0]["state"] == "cancelled"
    restored = ok(client.post(f"/api/tasks/{t['id']}/restore"))
    assert restored["status"] == "active" and restored["planned_date"] == MON
    plan = day(client, MON)["plans"][0]
    assert (plan["state"], plan["planned_time"]) == ("planned", "14:00:00")
    assert ok(client.get("/api/tasks?view=unscheduled")) == []  # not dumped in the Inbox
    ok(client.post(f"/api/tasks/{t['id']}/restore"))  # repeating is harmless
    assert len(day(client, MON)["plans"]) == 1
    assert any(a["action"] == "cancellation_undone" for a in ok(client.get(f"/api/tasks/{t['id']}"))["audit"])


def test_restore_to_a_past_day_comes_back_as_not_marked_yet(client, clock):
    t = new_task(client)
    ok(client.post(f"/api/tasks/{t['id']}/cancel"))
    clock.set("2026-03-04T12:00:00Z")  # two days later
    ok(client.post(f"/api/tasks/{t['id']}/restore"))
    assert day(client, MON)["plans"][0]["state"] == "awaiting_review"
    assert ok(client.get("/api/plans/pending-reviews")) == [{"date": MON, "unreviewed": 1}]


def test_restore_of_a_task_cancelled_from_the_inbox_returns_it_to_the_inbox(client):
    t = ok(client.post("/api/tasks", json={"title": "Someday idea"}), 201)
    ok(client.post(f"/api/tasks/{t['id']}/cancel"))
    assert ok(client.get("/api/tasks?view=unscheduled")) == []
    ok(client.post(f"/api/tasks/{t['id']}/restore"))
    assert [x["id"] for x in ok(client.get("/api/tasks?view=unscheduled"))] == [t["id"]]
    ok(client.post(f"/api/tasks/{t['id']}/archive"))  # archived tasks come back too
    ok(client.post(f"/api/tasks/{t['id']}/restore"))
    assert [x["id"] for x in ok(client.get("/api/tasks?view=unscheduled"))] == [t["id"]]


def test_delete_removes_the_task_and_all_its_day_records(client, clock):
    t = new_task(client)
    plan = day(client, MON)["plans"][0]
    review(client, plan["id"], "not_completed")
    ok(client.put(f"/api/tasks/{t['id']}/schedule", json={"planned_date": TUE}))
    keep = new_task(client, "Keep me")
    assert client.delete(f"/api/tasks/{t['id']}").status_code == 204
    assert client.delete(f"/api/tasks/{t['id']}").status_code == 204  # double click: harmless
    assert [p["task"]["title"] for p in day(client, MON)["plans"]] == ["Keep me"]
    assert day(client, TUE)["plans"] == []
    assert client.get(f"/api/tasks/{t['id']}").status_code == 404
    exported = ok(client.get("/api/data/export"))
    assert [x["id"] for x in exported["tasks"]] == [keep["id"]]
    assert all(a["entity_id"] != t["id"] or a["action"] == "deleted" for a in exported["audit_log"])
    assert not any("Update resume" in str(a) for a in exported["audit_log"])  # no content kept


def test_deleting_a_split_task_keeps_its_smaller_tasks(client):
    t = new_task(client)
    ok(client.post(f"/api/tasks/{t['id']}/split", json={"steps": [{"title": "Step one"}]}))
    assert client.delete(f"/api/tasks/{t['id']}").status_code == 204
    left = ok(client.get("/api/tasks?view=unscheduled"))
    assert [x["title"] for x in left] == ["Step one"] and left[0]["parent_task_id"] is None


def inbox(client):
    return [t["title"] for t in ok(client.get("/api/tasks?view=inbox"))]


def test_unfinished_inbox_task_returns_to_the_inbox_automatically(client):
    t = ok(client.post("/api/tasks", json={"title": "From the inbox"}), 201)
    assert t["origin"] == "inbox" and inbox(client) == ["From the inbox"]
    ok(client.put(f"/api/tasks/{t['id']}/schedule", json={"planned_date": MON}))  # dragged onto Monday
    assert inbox(client) == []
    review(client, day(client, MON)["plans"][0]["id"], "not_completed")
    assert inbox(client) == ["From the inbox"]


def test_unfinished_day_task_stays_on_its_day_until_the_user_chooses(client):
    t = new_task(client, "Made on Monday")
    assert t["origin"] == "day"
    plan = day(client, MON)["plans"][0]
    review(client, plan["id"], "not_completed")
    assert inbox(client) == []  # not moved anywhere automatically
    assert day(client, MON)["plans"][0]["state"] == "not_completed"
    # Choice 1: leave it on Monday.
    left = ok(client.post(f"/api/plans/{plan['id']}/follow-up", json={"action": "leave"}))
    assert left["follow_up"] == "left" and inbox(client) == []
    # Choice 2 (changing your mind): move it to the Inbox, where it then belongs.
    ok(client.post(f"/api/plans/{plan['id']}/follow-up", json={"action": "unscheduled"}))
    assert inbox(client) == ["Made on Monday"]
    assert ok(client.get(f"/api/tasks/{t['id']}"))["task"]["origin"] == "inbox"


def test_back_to_inbox_moves_a_day_task_into_the_inbox(client):
    t = new_task(client, "Not today after all", planned=TUE)
    ok(client.put(f"/api/tasks/{t['id']}/schedule", json={"planned_date": None}))
    assert inbox(client) == ["Not today after all"]


def test_time_ranges(client, clock):
    t = new_task(client, "Deep work", planned_time="09:00", planned_end_time="10:30")
    new_task(client, "Standup", planned_time="08:45", planned_end_time="09:00")
    plans = day(client, MON)["plans"]
    assert [(p["task"]["title"], p["planned_time"], p["planned_end_time"]) for p in plans] == [
        ("Standup", "08:45:00", "09:00:00"), ("Deep work", "09:00:00", "10:30:00")]
    # Invalid ranges are refused with a clear message.
    for body in ({"planned_time": "10:00", "planned_end_time": "09:00"},
                 {"planned_time": "10:00", "planned_end_time": "10:00"},
                 {"planned_end_time": "11:00"}):
        r = client.post("/api/tasks", json={"title": "Bad", "planned_date": MON, **body})
        assert r.status_code == 422
    # Changing the range on the same day; carrying it to another day keeps it.
    ok(client.put(f"/api/tasks/{t['id']}/schedule", json={"planned_date": MON, "planned_time": "13:00", "planned_end_time": "14:00"}))
    plan = next(p for p in day(client, MON)["plans"] if p["task_id"] == t["id"])
    assert (plan["planned_time"], plan["planned_end_time"]) == ("13:00:00", "14:00:00")
    review(client, plan["id"], "not_completed")
    ok(client.put(f"/api/tasks/{t['id']}/schedule", json={"planned_date": TUE}))
    tue = day(client, TUE)["plans"][0]
    assert (tue["planned_time"], tue["planned_end_time"]) == ("13:00:00", "14:00:00")
    ok(client.put(f"/api/tasks/{t['id']}/schedule", json={"planned_date": TUE, "planned_time": None}))
    tue = day(client, TUE)["plans"][0]
    assert (tue["planned_time"], tue["planned_end_time"]) == (None, None)  # back to anytime
