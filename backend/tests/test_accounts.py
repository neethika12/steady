"""Accounts, sessions, and that one person's data is never visible to another."""

import dataclasses

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.main import PUBLIC_PATHS, app
from app.models import FinanceCategory, JournalEntry, Task, User
from app.services import auth
from tests.conftest import TEST_EMAIL, TEST_PASSWORD, new_client, ok


def fill_account(c):
    """One of everything."""
    t = ok(c.post("/api/tasks", json={"title": "Private task"}), 201)
    h = ok(c.post("/api/habits", json={"name": "Private habit", "start_date": "2026-03-01",
                                         "schedule": {"schedule_type": "daily"}}), 201)
    ok(c.put("/api/journal/2026-03-02", json={"base_version": 0, "body": "Private diary"}))
    ok(c.post("/api/finance/setup", json={"accounts": [{"name": "Private bank", "type": "debit", "balance_cents": 5000}]}))
    ok(c.put("/api/finance/splitwise", json={"get_cents": 100, "pay_cents": 0}))
    ok(c.put("/api/settings", json={"timezone": "Asia/Kolkata"}))
    return t, h


def test_sign_up_log_out_log_in(client):
    assert ok(client.get("/api/auth/session"))["user"]["email"] == TEST_EMAIL
    assert client.post("/api/auth/logout").status_code == 204
    assert ok(client.get("/api/auth/session"))["user"] is None
    assert client.get("/api/tasks").status_code == 401
    assert client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": "wrong password!"}).status_code == 401
    ok(client.post("/api/auth/login", json={"email": "  YOU@example.com ", "password": TEST_PASSWORD}))  # email case/space ignored
    ok(client.get("/api/tasks"))


def test_sign_up_rules(client):
    anon = TestClient(app, base_url="https://testserver")
    assert anon.post("/api/auth/signup", json={"email": TEST_EMAIL, "password": "another long one"}).status_code == 409
    assert anon.post("/api/auth/signup", json={"email": "new@example.com", "password": "short"}).status_code == 422
    assert anon.post("/api/auth/signup", json={"email": "not-an-email", "password": "long enough pw"}).status_code == 422
    r = client.get("/api/auth/session")
    assert "steady_session" not in r.headers.get("set-cookie", "")  # the cookie value isn't echoed back


def test_every_api_route_needs_a_signed_in_user(client):
    anon = TestClient(app, base_url="https://testserver")
    checked = 0
    for path, methods in app.openapi()["paths"].items():
        if not path.startswith("/api/") or path in PUBLIC_PATHS:
            continue
        url = path.replace("{", "").replace("}", "")  # any value: it must be refused before it's looked at
        for method in (m.upper() for m in methods):
            r = anon.request(method, url, json={})
            assert r.status_code == 401, (method, path, r.status_code)
            checked += 1
    assert checked > 40


def test_people_never_see_each_others_data(client, Session):
    t, h = fill_account(client)
    with new_client("other@example.com", "a different password") as other:
        assert "Private task" not in str(ok(other.get("/api/tasks?status=all")))
        assert "Private" not in str(ok(other.get("/api/tasks/inbox"))) if other.get("/api/tasks/inbox").status_code == 200 else True
        assert other.get(f"/api/tasks/{t['id']}").status_code == 404
        assert other.patch(f"/api/tasks/{t['id']}", json={"title": "Hacked"}).status_code == 404
        assert other.delete(f"/api/tasks/{t['id']}").status_code in (404, 204)
        assert other.put(f"/api/habits/{h['id']}/checkins/2026-03-02", json={"value": 1}).status_code == 404
        assert not any(x.get("name") == "Private habit" for x in ok(other.get("/api/habits")))
        assert ok(other.get("/api/journal/2026-03-02"))["exists"] is False
        ok(other.put("/api/journal/2026-03-02", json={"base_version": 0, "body": "My own diary"}))  # same date, own entry
        o = ok(other.get("/api/finance/overview"))
        assert o["set_up"] is False and o["splitwise"]["get_cents"] == 0
        assert ok(other.get("/api/settings"))["timezone"] != "Asia/Kolkata"
        exported = ok(other.get("/api/data/export"))
        assert "Private" not in str(exported)
        assert len(ok(other.get("/api/finance/categories"))) == 12  # their own starter categories
    # ...and the first person's data is untouched.
    assert "Private task" in str(ok(client.get(f"/api/tasks/{t['id']}")))  # the other person's delete did nothing
    assert ok(client.get("/api/journal/2026-03-02"))["body"] == "Private diary"


def test_the_database_itself_enforces_separation(client, Session):
    fill_account(client)
    me = ok(client.get("/api/auth/session"))["user"]["id"]
    with Session(info={"user_id": None}) as s:  # nobody signed in: nothing visible, nothing writable
        assert s.scalar(select(func.count()).select_from(Task)) == 0
        assert s.scalar(select(func.count()).select_from(JournalEntry)) == 0
        with pytest.raises(Exception):
            s.add(Task(title="Orphan"))
            s.flush()
    with new_client("third@example.com", "yet another password"):
        pass
    with Session() as s:
        other_id = s.scalars(select(User.id).where(User.email == "third@example.com")).one()
    with Session(info={"user_id": other_id}) as s:  # even code that forgets to filter sees only its own rows
        assert s.scalar(select(func.count()).select_from(Task)) == 0
        assert s.scalar(select(func.count()).select_from(FinanceCategory)) == 12
        with pytest.raises(Exception):  # and can't write rows for someone else
            s.execute(text("INSERT INTO tasks (id, user_id, title, description, priority, status, origin, created_at, "
                           "updated_at) VALUES (gen_random_uuid(), :u, 'x', '', 'medium', 'active', 'inbox', now(), now())"),
                      {"u": me})
    with Session(info={"user_id": me}) as s:
        assert s.scalar(select(func.count()).select_from(Task)) == 1


def test_delete_account_removes_everything_and_only_that(client, admin_engine):
    fill_account(client)
    with new_client("keeper@example.com", "keeper password 1") as keeper:
        ok(keeper.post("/api/tasks", json={"title": "Keep me"}), 201)
        assert client.post("/api/auth/delete-account", json={"password": "wrong password"}).status_code == 403
        assert client.post("/api/auth/delete-account", json={"password": TEST_PASSWORD}).status_code == 204
        assert client.get("/api/tasks").status_code == 401
        with admin_engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM users WHERE email = :e"), {"e": TEST_EMAIL}).scalar() == 0
            for table in ("tasks", "habits", "journal_entries", "finance_accounts", "finance_categories", "app_settings"):
                owners = conn.execute(text(f"SELECT count(DISTINCT user_id) FROM {table}")).scalar()
                assert owners <= 1, table  # only the keeper's rows are left
        assert "Keep me" in str(ok(keeper.get("/api/tasks?status=all")))
    assert client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}).status_code == 401


def test_change_password_signs_out_other_browsers(client):
    with TestClient(app, base_url="https://testserver") as laptop:
        ok(laptop.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}))
        assert client.post("/api/auth/password", json={"current_password": "nope nope nope",
                                                       "new_password": "brand new password"}).status_code == 403
        assert client.post("/api/auth/password", json={"current_password": TEST_PASSWORD,
                                                       "new_password": "brand new password"}).status_code == 204
        assert laptop.get("/api/tasks").status_code == 401  # signed out
        ok(client.get("/api/tasks"))  # this browser stays signed in
    ok(client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": "brand new password"}))


def test_repeated_wrong_passwords_are_slowed_down(client):
    anon = TestClient(app, base_url="https://testserver")
    codes = [anon.post("/api/auth/login", json={"email": TEST_EMAIL, "password": f"guess {i}"}).status_code
             for i in range(10)]
    assert codes[:8] == [401] * 8 and codes[8:] == [429, 429]
    # Even the right password is refused until the limit passes.
    assert anon.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}).status_code == 429


def test_passwords_and_session_tokens_are_not_stored_in_plain_text(client, admin_engine):
    with admin_engine.connect() as conn:
        stored = conn.execute(text("SELECT password_hash FROM users WHERE email = :e"), {"e": TEST_EMAIL}).scalar()
        token_hash = conn.execute(text("SELECT token_hash FROM auth_sessions")).scalar()
    assert stored.startswith("scrypt$") and TEST_PASSWORD not in stored
    cookie = client.cookies.get(auth.SESSION_COOKIE)
    assert cookie and token_hash != cookie and len(token_hash) == 64


def test_first_account_on_a_local_server_claims_data_from_before_accounts(Session, admin_engine, clock, monkeypatch):
    from app.deps import get_now
    from app.routers import auth as auth_router
    with admin_engine.begin() as conn:  # what migration 0010 leaves behind for existing data
        conn.execute(text("INSERT INTO users (id, created_at, updated_at) VALUES (:o, now(), now())"), {"o": str(auth.OWNER_ID)})
        conn.execute(text("INSERT INTO tasks (id, user_id, title, description, priority, status, origin, created_at, "
                          "updated_at) VALUES (gen_random_uuid(), :o, 'From before', '', 'medium', 'active', 'inbox', "
                          "now(), now())"), {"o": str(auth.OWNER_ID)})
    app.state.session_factory = Session
    app.dependency_overrides[get_now] = lambda: clock.now
    auth.signup_limiter.clear()
    try:
        cfg = dataclasses.replace(auth_router.get_config(), claim_existing_data=True)
        monkeypatch.setattr(auth_router, "get_config", lambda: cfg)
        with new_client("owner@example.com", "owner password 1") as owner:
            assert "From before" in str(ok(owner.get("/api/tasks?status=all")))
        with new_client("second@example.com", "second password 1") as second:  # only the first one claims it
            assert "From before" not in str(ok(second.get("/api/tasks?status=all")))
    finally:
        app.dependency_overrides.clear()
        del app.state.session_factory
