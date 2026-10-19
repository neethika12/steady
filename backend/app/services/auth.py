"""Accounts: passwords, sign-in sessions and the per-user starter data.

- Passwords are hashed with scrypt (Python standard library) and a random salt per user.
- A session is a random token in an HttpOnly cookie; the database keeps only its SHA-256.
- Failed log-ins are rate limited per email address and per client address.
"""

import hashlib
import hmac
import re
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.errors import AppError, conflict, invalid
from app.models import AuthSession, FinanceCategory, User

SESSION_COOKIE = "steady_session"
OWNER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")  # placeholder owner from migration 0010
MIN_PASSWORD = 10
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")

STARTER_CATEGORIES = [
    ("expense", "Groceries"), ("expense", "Dining out"), ("expense", "Transport"), ("expense", "Housing & rent"),
    ("expense", "Bills & utilities"), ("expense", "Health"), ("expense", "Shopping"), ("expense", "Entertainment"),
    ("expense", "Education"), ("expense", "Other"),
    ("income", "Salary"), ("income", "Other income"),
]


# ---------------------------------------------------------------- passwords

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, maxmem=64 * 1024 * 1024, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = bytes.fromhex(digest)
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(expected), maxmem=64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


_DUMMY_HASH = hash_password(secrets.token_hex(8))  # so unknown emails take as long as wrong passwords


def check_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise invalid("weak_password", f"Use at least {MIN_PASSWORD} characters for your password.")
    if len(password) > 200:
        raise invalid("weak_password", "That password is too long (200 characters at most).")


def normalize_email(email: str) -> str:
    e = email.strip().lower()
    if not _EMAIL.match(e) or len(e) > 254:
        raise invalid("email", "Enter a valid email address.")
    return e


# ---------------------------------------------------------------- rate limiting

class AttemptLimiter:
    """At most ``limit`` failures per key in ``window`` seconds (kept in memory)."""

    def __init__(self, limit: int, window: int) -> None:
        self.limit, self.window = limit, window
        self.fails: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def _trim(self, q: deque[float], now: float) -> None:
        while q and now - q[0] > self.window:
            q.popleft()

    def check(self, *keys: str) -> None:
        now = time.monotonic()
        with self.lock:
            for k in keys:
                q = self.fails[k]
                self._trim(q, now)
                if len(q) >= self.limit:
                    wait = int(self.window - (now - q[0])) // 60 + 1
                    raise AppError(429, "too_many_attempts", f"Too many attempts. Try again in about {wait} minutes.")

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self.lock:
            for k in keys:
                self.fails[k].append(now)

    def clear(self) -> None:
        with self.lock:
            self.fails.clear()


login_limiter = AttemptLimiter(limit=8, window=15 * 60)
signup_limiter = AttemptLimiter(limit=10, window=60 * 60)


# ---------------------------------------------------------------- sessions

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def act_as(db: Session, user_id: uuid.UUID) -> None:
    """From now on this session works as ``user_id`` (this transaction and later ones)."""
    db.info["user_id"] = user_id
    db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id)})


def create_session(db: Session, user: User, now: datetime, days: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=_token_hash(token), expires_at=now + timedelta(days=days),
                       last_seen_at=now))
    user.last_login_at = now
    return token


def user_for_token(db: Session, token: str, now: datetime) -> uuid.UUID | None:
    s = db.scalars(select(AuthSession).where(AuthSession.token_hash == _token_hash(token))).first()
    if s is None:
        return None
    if s.expires_at <= now:
        db.delete(s)
        db.commit()
        return None
    if now - s.last_seen_at > timedelta(hours=1):  # don't write on every request
        s.last_seen_at = now
        db.commit()
    return s.user_id


def end_session(db: Session, token: str) -> None:
    s = db.scalars(select(AuthSession).where(AuthSession.token_hash == _token_hash(token))).first()
    if s is not None:
        db.delete(s)


def end_other_sessions(db: Session, user_id: uuid.UUID, keep_token: str | None) -> None:
    keep = _token_hash(keep_token) if keep_token else None
    for s in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id)):
        if s.token_hash != keep:
            db.delete(s)


# ---------------------------------------------------------------- accounts

def seed_new_user(db: Session) -> None:
    """Per-user starter data (the session must already act as the new user)."""
    for i, (kind, name) in enumerate(STARTER_CATEGORIES):
        db.add(FinanceCategory(name=name, kind=kind, sort_order=i))


def sign_up(db: Session, email: str, password: str, claim_existing: bool) -> User:
    email = normalize_email(email)
    check_new_password(password)
    if db.scalars(select(User).where(User.email == email)).first():
        raise conflict("email_taken", "An account with that email already exists. Log in instead.")
    if claim_existing:
        owner = db.get(User, OWNER_ID)
        if owner is not None and owner.email is None:  # data from before accounts existed: it becomes yours
            owner.email, owner.password_hash = email, hash_password(password)
            db.flush()
            act_as(db, owner.id)
            return owner
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    act_as(db, user.id)
    seed_new_user(db)
    db.flush()
    return user


def log_in(db: Session, email: str, password: str) -> User | None:
    try:
        email = normalize_email(email)
    except AppError:
        return None
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None
