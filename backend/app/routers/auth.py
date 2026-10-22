"""Sign up, log in, log out, change password, delete account."""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_config
from app.db import get_db
from app.errors import AppError
from app.models import AppSettings, User
from app.timeutil import is_valid_timezone
from app.services import auth
from app.timeutil import utc_now

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class SignUp(Credentials):
    name: str = Field(min_length=1, max_length=80)
    timezone: str | None = Field(default=None, max_length=64)  # the device's, so "today" matches the person's day


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class PasswordReset(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    recovery_code: str = Field(min_length=10, max_length=60)
    new_password: str = Field(min_length=1, max_length=200)


class PasswordConfirm(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _client(request: Request) -> str:
    # Behind Vercel/Railway the first forwarded address is the browser's.
    fwd = request.headers.get("x-forwarded-for")
    return "ip:" + (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown"))


def _user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "has_recovery_code": bool(u.recovery_code_hash)}


def _set_cookie(response: Response, token: str) -> None:
    cfg = get_config()
    response.set_cookie(auth.SESSION_COOKIE, token, max_age=cfg.session_days * 86400, httponly=True,
                        secure=cfg.cookie_secure, samesite="lax", path="/")


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(auth.SESSION_COOKIE, path="/", secure=get_config().cookie_secure, httponly=True, samesite="lax")


def _require_user(request: Request, db: Session) -> User:
    user = db.get(User, request.state.user_id) if getattr(request.state, "user_id", None) else None
    if user is None:
        raise AppError(401, "auth_required", "Please log in.")
    return user


@router.get("/session")
def session(request: Request, db: Session = Depends(get_db)) -> dict:
    """Who is signed in (``user`` is null when nobody is)."""
    uid = getattr(request.state, "user_id", None)
    user = db.get(User, uid) if uid else None
    return {"user": _user_out(user) if user else None, "signup_enabled": get_config().signup_enabled,
            "min_password_length": auth.MIN_PASSWORD}


@router.post("/signup", status_code=201)
def sign_up(data: SignUp, request: Request, db: Session = Depends(get_db)) -> dict:
    """Creates the account only. No session is started: the person then logs in with it."""
    cfg = get_config()
    if not cfg.signup_enabled:
        raise AppError(403, "signup_closed", "New sign-ups are turned off on this server.")
    ip = _client(request)
    auth.signup_limiter.check(db, ip)
    auth.signup_limiter.fail(db, ip)  # counts every attempt: limits mass account creation
    user = auth.sign_up(db, data.name, data.email, data.password, cfg.claim_existing_data)
    if data.timezone and is_valid_timezone(data.timezone) and db.scalars(select(AppSettings)).first() is None:
        db.add(AppSettings(timezone=data.timezone, timezone_confirmed=True))  # the new account's own settings row
    code = auth.new_recovery_code(user)
    db.commit()
    # Shown once, so the person can reset their password later without email.
    return {"user": _user_out(user), "recovery_code": code}


@router.post("/login")
def log_in(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    keys = ("email:" + data.email.strip().lower(), _client(request))
    auth.login_limiter.check(db, *keys)
    user = auth.log_in(db, data.email, data.password)
    if user is None:
        auth.login_limiter.fail(db, *keys)
        raise AppError(401, "invalid_login", "That email and password don't match an account.")
    token = auth.create_session(db, user, utc_now(), get_config().session_days)  # real time, never a test clock
    db.commit()
    _set_cookie(response, token)
    return {"user": _user_out(user)}


@router.post("/logout", status_code=204)
def log_out(request: Request, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        auth.end_session(db, token)
        db.commit()
    response = Response(status_code=204)
    _clear_cookie(response)
    return response


@router.post("/password", status_code=204)
def change_password(data: PasswordChange, request: Request, db: Session = Depends(get_db)) -> Response:
    """Also signs out every other browser."""
    user = _require_user(request, db)
    keys = (f"user:{user.id}",)
    auth.login_limiter.check(db, *keys)
    if not auth.verify_password(data.current_password, user.password_hash):
        auth.login_limiter.fail(db, *keys)
        raise AppError(403, "wrong_password", "Your current password isn't right.")
    auth.check_new_password(data.new_password)
    user.password_hash = auth.hash_password(data.new_password)
    auth.end_other_sessions(db, user.id, request.cookies.get(auth.SESSION_COOKIE))
    db.commit()
    return Response(status_code=204)


@router.post("/delete-account", status_code=204)
def delete_account(data: PasswordConfirm, request: Request, db: Session = Depends(get_db)) -> Response:
    """Permanently deletes the account and every record in it."""
    user = _require_user(request, db)
    keys = (f"user:{user.id}",)
    auth.login_limiter.check(db, *keys)
    if not auth.verify_password(data.password, user.password_hash):
        auth.login_limiter.fail(db, *keys)
        raise AppError(403, "wrong_password", "That password isn't right, so nothing was deleted.")
    db.delete(user)  # the database removes everything that belongs to it (ON DELETE CASCADE)
    db.commit()
    response = Response(status_code=204)
    _clear_cookie(response)
    return response


@router.post("/reset-password")
def reset_password(data: PasswordReset, request: Request, db: Session = Depends(get_db)) -> dict:
    """Forgot password: email + recovery code + new password. Each code works once, so a new one
    is returned (shown once). Every signed-in browser of the account is signed out."""
    email = data.email.strip().lower()
    keys = ("email:" + email, _client(request))
    auth.reset_limiter.check(db, *keys)
    user = db.scalars(select(User).where(User.email == email)).first()
    if not auth.check_recovery_code(user, data.recovery_code):
        auth.reset_limiter.fail(db, *keys)
        raise AppError(401, "invalid_recovery", "That email and recovery code don't match.")
    auth.check_new_password(data.new_password)
    user.password_hash = auth.hash_password(data.new_password)
    code = auth.new_recovery_code(user)
    auth.end_other_sessions(db, user.id, None)
    db.commit()
    return {"recovery_code": code}


@router.post("/recovery-code")
def regenerate_recovery_code(data: PasswordConfirm, request: Request, db: Session = Depends(get_db)) -> dict:
    """Make a new recovery code (the old one stops working). Needs the current password."""
    user = _require_user(request, db)
    keys = (f"user:{user.id}",)
    auth.login_limiter.check(db, *keys)
    if not auth.verify_password(data.password, user.password_hash):
        auth.login_limiter.fail(db, *keys)
        raise AppError(403, "wrong_password", "That password isn't right.")
    code = auth.new_recovery_code(user)
    db.commit()
    return {"recovery_code": code}
