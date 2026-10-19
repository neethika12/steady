"""FastAPI application entry point."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.config import get_config
from app.db import open_session, session_factory
from app.routers import ai, auth, data, finance, habits, journal, settings, tasks
from app.services import auth as auth_service
from app.timeutil import utc_now

# Request bodies (journal text, task titles) are never logged.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

app = FastAPI(title="Steady API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_config().cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


# Everything under /api needs a signed-in user, except these.
PUBLIC_PATHS = {"/api/health", "/api/auth/session", "/api/auth/signup", "/api/auth/login", "/api/auth/logout"}


@app.middleware("http")
async def authenticate(request: Request, call_next):
    """Resolve the session cookie to a user; refuse /api requests without one."""
    token = request.cookies.get(auth_service.SESSION_COOKIE)
    user_id = None
    if token:
        def lookup():
            with open_session(session_factory(request), None) as db:
                return auth_service.user_for_token(db, token, utc_now())
        user_id = await run_in_threadpool(lookup)
    request.state.user_id = user_id
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_PATHS and user_id is None:
        return JSONResponse(status_code=401, content={"detail": {"code": "auth_required", "message": "Please log in."}})
    return await call_next(request)


@app.exception_handler(IntegrityError)
def integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
    # Usually two identical requests racing each other. Nothing was saved by this one.
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    return JSONResponse(status_code=409, content={"detail": {
        "code": "duplicate",
        "message": "That change conflicts with a record that already exists. Refresh and try again.",
        "constraint": constraint,
    }})


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


for module in (auth, settings, tasks, habits, journal, finance, data, ai):
    app.include_router(module.router)
