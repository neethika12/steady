"""Journal saving, versioning and conflict handling."""

from tests.conftest import ok

D = "2026-03-02"


def save(client, base_version, status=200, **fields):
    return client.put(f"/api/journal/{D}", json={"base_version": base_version, **fields})


def test_empty_day_has_no_entry_and_blank_save_creates_nothing(client):
    entry = ok(client.get(f"/api/journal/{D}"))
    assert entry["exists"] is False and entry["version"] == 0
    assert ok(save(client, 0, body="  "))["exists"] is False
    assert ok(client.get("/api/journal")) == []


def test_create_then_update_with_versions(client):
    first = ok(save(client, 0, body="Hello", mood=4))
    assert first["version"] == 1 and first["exists"]
    second = ok(save(client, 1, body="Hello again", mood=4, energy=2, went_well="Lunch outside"))
    assert second["version"] == 2
    same = ok(save(client, 2, body="Hello again", mood=4, energy=2, went_well="Lunch outside"))
    assert same["version"] == 2  # unchanged autosave doesn't bump the version
    listing = ok(client.get("/api/journal"))
    assert listing[0]["entry_date"] == D and listing[0]["word_count"] == 2


def test_stale_save_is_refused_with_the_newer_entry(client):
    ok(save(client, 0, body="From the laptop"))
    ok(save(client, 1, body="From the laptop, edited"))
    r = save(client, 1, body="From the phone")  # phone still had version 1
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "journal_conflict"
    assert detail["current"]["body"] == "From the laptop, edited" and detail["current"]["version"] == 2
    assert ok(client.get(f"/api/journal/{D}"))["body"] == "From the laptop, edited"
    # The user explicitly chooses to keep their version: resubmit against the newer version.
    kept = ok(save(client, 2, body="From the phone"))
    assert kept["version"] == 3


def test_two_new_entries_for_the_same_day_conflict(client):
    ok(save(client, 0, body="First tab"))
    r = save(client, 0, body="Second tab")
    assert r.status_code == 409
    assert r.json()["detail"]["current"]["body"] == "First tab"


def test_validation_and_future_dates(client):
    assert save(client, 0, body="x", mood=6).status_code == 422
    r = client.put("/api/journal/2026-03-03", json={"base_version": 0, "body": "tomorrow"})
    assert r.status_code == 422
