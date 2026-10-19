"""Migration 0002 turns open Inbox items into undated tasks without losing anything."""

from alembic import command
from sqlalchemy import create_engine, text

from tests.conftest import TEST_URL, alembic_config, base_url

MIG_DB = f"{TEST_URL.database}_mig"


def test_open_inbox_items_become_undated_tasks():
    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIG_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{MIG_DB}"'))
    url = TEST_URL.set(database=MIG_DB)
    cfg = alembic_config()
    cfg.attributes["database_url"] = url.render_as_string(hide_password=False)
    try:
        command.upgrade(cfg, "0001_initial")
        eng = create_engine(url)
        with eng.begin() as conn:
            conn.execute(text("""
                INSERT INTO inbox_items (id, text, status, created_at, updated_at) VALUES
                ('00000000-0000-4000-8000-000000000001', '  Book flights\nCheck baggage rules  ', 'open', now(), now()),
                ('00000000-0000-4000-8000-000000000002', 'Old idea', 'archived', now(), now()),
                ('00000000-0000-4000-8000-000000000003', 'Call mum', 'open', now(), now())
            """))
        command.upgrade(cfg, "head")
        with eng.connect() as conn:
            tasks = conn.execute(text(
                "SELECT title, description, status, planned_date, source_inbox_item_id::text FROM tasks ORDER BY title"
            )).all()
            items = dict(conn.execute(text("SELECT id::text, status FROM inbox_items")).all())
            audits = conn.execute(text("SELECT count(*) FROM audit_log WHERE action = 'converted_to_task'")).scalar()
        assert tasks == [
            ("Book flights", "Book flights\nCheck baggage rules", "active", None, "00000000-0000-4000-8000-000000000001"),
            ("Call mum", "", "active", None, "00000000-0000-4000-8000-000000000003"),
        ]
        assert items["00000000-0000-4000-8000-000000000001"] == "converted"
        assert items["00000000-0000-4000-8000-000000000002"] == "archived"  # untouched
        assert audits == 2
        command.upgrade(cfg, "head")  # running again is a no-op
        with eng.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM tasks")).scalar() == 2
        eng.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{MIG_DB}" WITH (FORCE)'))
        admin.dispose()


def test_task_origin_backfill():
    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIG_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{MIG_DB}"'))
    url = TEST_URL.set(database=MIG_DB)
    cfg = alembic_config()
    cfg.attributes["database_url"] = url.render_as_string(hide_password=False)
    try:
        command.upgrade(cfg, "0003_plan_time_of_day")
        eng = create_engine(url)
        with eng.begin() as conn:
            conn.execute(text("""
                INSERT INTO tasks (id, title, description, priority, status, planned_date, created_at, updated_at) VALUES
                ('00000000-0000-4000-8000-0000000000a1', 'Made on a day', '', 'medium', 'active', '2026-03-02', '2026-03-01 10:00+00', now()),
                ('00000000-0000-4000-8000-0000000000a2', 'Captured, planned later', '', 'medium', 'active', '2026-03-02', '2026-03-01 10:00+00', now()),
                ('00000000-0000-4000-8000-0000000000a3', 'Never planned', '', 'medium', 'active', NULL, '2026-03-01 10:00+00', now());
                INSERT INTO task_plans (id, task_id, plan_date, created_at, updated_at) VALUES
                ('00000000-0000-4000-8000-0000000000b1', '00000000-0000-4000-8000-0000000000a1', '2026-03-02', '2026-03-01 10:00:01+00', now()),
                ('00000000-0000-4000-8000-0000000000b2', '00000000-0000-4000-8000-0000000000a2', '2026-03-02', '2026-03-01 18:00+00', now());
            """))
        command.upgrade(cfg, "head")
        with eng.connect() as conn:
            origins = dict(conn.execute(text("SELECT title, origin FROM tasks")).all())
        assert origins == {"Made on a day": "day", "Captured, planned later": "inbox", "Never planned": "inbox"}
        eng.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{MIG_DB}" WITH (FORCE)'))
        admin.dispose()
