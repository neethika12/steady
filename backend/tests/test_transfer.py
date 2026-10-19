"""JSON export and import with the documented duplicate policy."""

import copy

from tests.conftest import ok


def seed(client):
    ok(client.post("/api/tasks", json={"title": "Loose idea"}), 201)  # an undated (Inbox) task
    t = ok(client.post("/api/tasks", json={"title": "Task", "planned_date": "2026-03-02"}), 201)
    plan = ok(client.get("/api/plans/day?date=2026-03-02"))["plans"][0]
    ok(client.put(f"/api/plans/{plan['id']}/review", json={"outcome": "not_completed", "reason": "waiting", "reason_note": "Waiting on IT"}))
    ok(client.post(f"/api/plans/{plan['id']}/follow-up", json={"action": "split", "steps": [{"title": "Child"}]}))
    h = ok(client.post("/api/habits", json={"name": "Walk", "start_date": "2026-03-02",
                                             "schedule": {"schedule_type": "daily"}}), 201)
    ok(client.put(f"/api/habits/{h['id']}/checkins/2026-03-02", json={"value": 1}))
    ok(client.put("/api/journal/2026-03-02", json={"base_version": 0, "body": "Dear diary"}))
    return t


def test_export_import_round_trip(client, wipe_data):
    seed(client)
    exported = ok(client.get("/api/data/export"))
    assert exported["format"] == "steady-export" and exported["version"] == 1
    assert len(exported["tasks"]) == 3 and len(exported["task_plans"]) == 1
    wipe_data()

    dry = ok(client.post("/api/data/import?dry_run=true", json=exported))
    assert dry["collections"]["tasks"]["imported"] == 3
    assert ok(client.get("/api/journal/2026-03-02"))["exists"] is False  # dry run wrote nothing

    report = ok(client.post("/api/data/import?dry_run=false", json=exported))
    assert all(c["imported"] == c["in_file"] for c in report["collections"].values())
    assert report["settings_applied"] is False
    assert ok(client.get("/api/journal/2026-03-02"))["body"] == "Dear diary"
    day = ok(client.get("/api/plans/day?date=2026-03-02"))
    assert day["plans"][0]["reason"] == "waiting"

    again = ok(client.post("/api/data/import?dry_run=false", json=exported))
    assert all(c["imported"] == 0 and c["skipped_existing"] == c["in_file"]
               for c in again["collections"].values())


def test_import_reports_natural_key_conflicts_and_never_overwrites(client, wipe_data):
    seed(client)
    exported = ok(client.get("/api/data/export"))
    other = copy.deepcopy(exported)
    other["journal_entries"][0]["id"] = "00000000-0000-4000-8000-000000000001"
    other["journal_entries"][0]["body"] = "A different diary"
    report = ok(client.post("/api/data/import?dry_run=false", json=other))
    assert report["collections"]["journal_entries"]["conflicts"] == 1
    assert ok(client.get("/api/journal/2026-03-02"))["body"] == "Dear diary"


def test_import_rejects_bad_files(client):
    assert client.post("/api/data/import", json={"format": "other", "version": 1,
                                                   "exported_at": "2026-03-02T00:00:00Z"}).status_code == 422
    broken = {"format": "steady-export", "version": 1, "exported_at": "2026-03-02T00:00:00Z",
              "task_plans": [{"id": "00000000-0000-4000-8000-000000000002",
                              "task_id": "00000000-0000-4000-8000-000000000003",
                              "plan_date": "2026-03-02", "created_at": "2026-03-02T00:00:00Z",
                              "updated_at": "2026-03-02T00:00:00Z"}]}
    r = client.post("/api/data/import?dry_run=false", json=broken)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "bad_references"
    extra = {"format": "steady-export", "version": 1, "exported_at": "2026-03-02T00:00:00Z",
             "surprise": []}
    assert client.post("/api/data/import", json=extra).status_code == 422
