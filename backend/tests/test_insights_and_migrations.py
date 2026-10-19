"""Deterministic To-Do insights, and the migration matching the models."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.models import Base
from tests.conftest import ok


def test_task_insights_distinguish_missing_from_recorded(client, clock):
    clock.set("2026-03-04T20:00:00Z")
    titles = ["A", "B", "C", "D"]
    for t in titles:
        ok(client.post("/api/tasks", json={"title": t, "planned_date": "2026-03-02",
                                           "estimated_minutes": 30}), 201)
    plans = {p["task"]["title"]: p for p in ok(client.get("/api/plans/day?date=2026-03-02"))["plans"]}
    ok(client.put(f"/api/plans/{plans['A']['id']}/review", json={"outcome": "completed"}))
    ok(client.patch(f"/api/tasks/{plans['A']['task_id']}", json={"actual_minutes": 45}))
    ok(client.put(f"/api/plans/{plans['B']['id']}/review", json={"outcome": "not_completed", "reason": "not_enough_time", "reason_note": "Meetings ran over"}))
    ok(client.put(f"/api/plans/{plans['C']['id']}/review", json={"outcome": "not_completed", "reason_note": "Blocked"}))  # written reason, no tag
    ok(client.post(f"/api/plans/{plans['B']['id']}/follow-up", json={"action": "reschedule", "date": "2026-03-03"}))
    # D is never reviewed.
    ins = ok(client.get("/api/insights/tasks?start=2026-03-02&end=2026-03-08"))
    assert ins["evaluated_through"] == "2026-03-04"
    t = ins["totals"]
    assert (t["planned"], t["completed"], t["not_completed"], t["partial"], t["awaiting_review"]) == (5, 1, 2, 0, 2)
    assert t["completion_pct"] == 20
    r = ins["reasons"]
    assert (r["unfinished"], r["with_reason"], r["without_reason"], r["tagged"], r["untagged"]) == (2, 2, 0, 1, 1)
    assert r["by_reason"] == [{"reason": "not_enough_time", "label": "Not enough time", "count": 1}]
    assert ins["carryover"]["carried_plans"] == 1 and ins["carryover"]["tasks_carried"] == 1
    d = ins["durations"]
    assert d["tasks_with_both"] == 1 and d["estimated_total"] == 30 and d["actual_total"] == 45


def test_migrations_match_models(engine):
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff
