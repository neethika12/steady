"""Database engine and the per-request session dependency.

Every connection the app uses switches to the restricted role ``steady_app`` as soon as it
opens, and every transaction records which user is signed in (``app.user_id``). Row-level
security (migration 0010) then limits each query to that user's rows. With no user set (for
example the sign-up and log-in endpoints), data tables appear empty and can't be written.
Migrations use their own connection with the normal credentials.
"""

import uuid
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_config

APP_ROLE = "steady_app"


def use_app_role(engine: Engine) -> Engine:
    """Make every new connection of ``engine`` run as the restricted role."""

    @event.listens_for(engine, "connect")
    def _switch_role(dbapi_connection, _record) -> None:
        with dbapi_connection.cursor() as cur:
            cur.execute(f"SET ROLE {APP_ROLE}")
        dbapi_connection.commit()  # a plain SET is undone if its transaction rolls back

    return engine


@event.listens_for(Session, "after_begin")
def _set_current_user(session: Session, _transaction, connection) -> None:
    user_id = session.info.get("user_id")
    connection.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id) if user_id else ""})


def make_engine(url: str) -> Engine:
    return use_app_role(create_engine(url, pool_pre_ping=True))


engine = make_engine(get_config().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def session_factory(request: Request) -> sessionmaker:
    """Tests point the app at their own database through ``app.state.session_factory``."""
    return getattr(request.app.state, "session_factory", SessionLocal)


def open_session(factory: sessionmaker, user_id: uuid.UUID | None) -> Session:
    return factory(info={"user_id": user_id})


def get_db(request: Request) -> Iterator[Session]:
    """One session (one transaction) per request, limited to the signed-in user's rows.

    Endpoints that change data call ``db.commit()`` themselves once every related
    record has been written, so a failure part-way through rolls everything back.
    """
    session = open_session(session_factory(request), getattr(request.state, "user_id", None))
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
