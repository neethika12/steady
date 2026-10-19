"""Test setup.

Tests use a separate database named "<your database>_test" on the same server.
They refuse to run against any database whose name doesn't end in "_test",
so the real data can never be touched.
"""

import os
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import get_config
from app.db import use_app_role
from app.deps import get_now
from app.main import app
from app.models import Base

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

base_url = make_url(get_config().database_url)
TEST_DB = base_url.database if base_url.database.endswith("_test") else f"{base_url.database}_test"
TEST_URL = base_url.set(database=TEST_DB)
assert TEST_URL.database.endswith("_test"), "Refusing to run tests on a non-test database"


def _create_test_database() -> None:
    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()


def alembic_config() -> AlembicConfig:
    cfg = AlembicConfig(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    cfg.attributes["database_url"] = TEST_URL.render_as_string(hide_password=False)
    cfg.attributes["configure_logging"] = False
    return cfg


@pytest.fixture(scope="session")
def admin_engine():
    """Full-rights connection, for setting up and wiping the test database only."""
    _create_test_database()
    eng = create_engine(TEST_URL)
    with eng.begin() as conn:  # start every run from an empty schema
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(alembic_config(), "head")
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def engine(admin_engine):
    """What the app uses: the restricted role, so row-level security applies in tests too."""
    eng = use_app_role(create_engine(TEST_URL))
    yield eng
    eng.dispose()


DATA_TABLES = [t.name for t in Base.metadata.sorted_tables if t.name not in ("users", "auth_sessions")]


@pytest.fixture
def wipe_data(admin_engine):
    """Delete every record but keep the accounts (like moving to a fresh database)."""
    def wipe():
        with admin_engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {', '.join(DATA_TABLES)} CASCADE"))
    return wipe


@pytest.fixture
def Session(engine, admin_engine):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with admin_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    return sessionmaker(bind=engine, expire_on_commit=False)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 3, 2, 15, 0, tzinfo=timezone.utc)  # Monday

    def set(self, iso: str) -> None:
        self.now = datetime.fromisoformat(iso.replace("Z", "+00:00"))


@pytest.fixture
def clock():
    return Clock()


TEST_EMAIL, TEST_PASSWORD = "you@example.com", "correct horse battery"


def new_client(email: str = TEST_EMAIL, password: str = TEST_PASSWORD) -> TestClient:
    """A browser signed in to its own account (HTTPS, so the secure session cookie is sent)."""
    c = TestClient(app, base_url="https://testserver")
    r = c.post("/api/auth/signup", json={"name": "Test Person", "email": email, "password": password})
    assert r.status_code == 201, r.text
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def client(Session, clock):
    from app.services import auth
    app.state.session_factory = Session
    app.dependency_overrides[get_now] = lambda: clock.now
    auth.login_limiter.clear()
    auth.signup_limiter.clear()
    with new_client() as c:
        yield c
    app.dependency_overrides.clear()
    del app.state.session_factory


def ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()
