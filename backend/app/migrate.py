"""Apply pending database migrations the first time a serverless instance handles a request.

Docker starts the backend with scripts/start.sh, which migrates before serving; serverless
hosts (like Vercel) have no start script, so MIGRATE_ON_START=true makes the app do it itself.
A PostgreSQL advisory lock makes sure only one instance migrates at a time; the others wait and
then find nothing to do. Migrations only ever move the schema forward; nothing is wiped.
"""

import os
import threading

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from app.config import get_config

_LOCK_ID = 7_212_026  # any constant; identifies "Steady migrations" among advisory locks
_done = False
_guard = threading.Lock()


def _alembic_config() -> Config:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "alembic"))
    cfg.attributes["configure_logging"] = False
    return cfg


def ensure_schema() -> None:
    global _done
    if _done or not get_config().migrate_on_start:
        return
    with _guard:
        if _done:
            return
        url = get_config().database_url
        cfg = _alembic_config()
        cfg.attributes["database_url"] = url  # migrate exactly the database that was checked
        head = ScriptDirectory.from_config(cfg).get_current_head()
        engine = create_engine(url, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as lock_conn:
                lock_conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": _LOCK_ID})
                try:
                    with engine.connect() as conn:
                        current = MigrationContext.configure(conn).get_current_revision()
                    if current != head:
                        command.upgrade(cfg, "head")
                finally:
                    lock_conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": _LOCK_ID})
        finally:
            engine.dispose()
        _done = True
