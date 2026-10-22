"""Database engine and the per-request session dependency.

Every transaction the app runs switches to the restricted role ``steady_app`` (SET LOCAL ROLE)
and records which user is signed in (``app.user_id``). Row-level security (migration 0010) then
limits each query to that user's rows. With no user set (for example the sign-up and log-in
endpoints), data tables appear empty and can't be written. Both settings last only for the
transaction, so they're safe behind connection poolers that hand connections between clients.
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


@event.listens_for(Session, "after_begin")
def _restrict_transaction(session: Session, _transaction, connection) -> None:
    user_id = session.info.get("user_id")
    connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
    connection.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id) if user_id else ""})


def make_engine(url: str) -> Engine:
    # Small pool: on serverless hosts each instance serves few requests at a time.
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2)


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
