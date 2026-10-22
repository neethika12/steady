"""Local AI endpoints. All of them return proposals only; none of them write data."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import features
from app.ai.provider import AIProvider
from app.ai.runner import get_provider
from app.config import get_config
from app.db import get_db
from app.deps import Ctx, get_ctx
from app.errors import AppError, invalid
from app.models import AiUsage

router = APIRouter(prefix="/api/ai", tags=["ai"])

class _Metered:
    """Counts how many times the model was actually asked (retries included)."""

    def __init__(self, provider: AIProvider) -> None:
        self.provider, self.calls = provider, 0
        self.name, self.model = provider.name, provider.model
        self.serial = getattr(provider, "serial", True)

    def status(self) -> dict[str, Any]:
        return self.provider.status()

    def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return self.provider.generate_json(**kwargs)


def _used_today(db: Session) -> int:
    since = func.now() - timedelta(hours=24)
    return db.scalar(select(func.count()).select_from(AiUsage).where(AiUsage.created_at > since)) or 0


@contextmanager
def _quota(db: Session, provider: AIProvider, feature: str) -> Iterator[_Metered]:
    """Per-person daily limit (AI_DAILY_LIMIT_PER_USER; 0 = none). Only requests that reached
    the model count, whether or not their answer passed the checks."""
    limit = get_config().ai_daily_limit_per_user
    if limit and _used_today(db) >= limit:
        raise AppError(429, "ai_daily_limit",
                       f"You've used your {limit} AI requests for today. They free up again within 24 hours.")
    metered = _Metered(provider)
    try:
        yield metered
    finally:
        if metered.calls:
            db.rollback()  # AI features only read; start a clean transaction for the record
            db.add(AiUsage(feature=feature))
            db.commit()


SETUP_STEPS = [
    "Install Ollama on this computer (macOS: brew install ollama).",
    "Start it: ollama serve   (or: brew services start ollama).",
    "Download the model once (needs internet, about 2.5 GB): ollama pull phi4-mini",
    "Reload this page. After the download, AI works offline.",
]


@router.get("/status")
def status(db: Session = Depends(get_db), provider: AIProvider = Depends(get_provider)) -> dict:
    s = provider.status()
    cfg = get_config()
    return {**s, "provider": provider.name, "model": provider.model,
            # Setup steps and address only apply to a model on this computer.
            "base_url": None if provider.name in ("groq", "disabled") else cfg.ollama_base_url,
            "setup": [] if provider.name in ("groq", "disabled") else SETUP_STEPS,
            "daily_limit": cfg.ai_daily_limit_per_user or None, "used_today": _used_today(db)}


class BreakdownIn(BaseModel):
    task_id: uuid.UUID


@router.post("/breakdown")
def breakdown(data: BreakdownIn, db: Session = Depends(get_db),
              provider: AIProvider = Depends(get_provider)) -> dict:
    with _quota(db, provider, "breakdown") as p:
        return features.breakdown(db, p, data.task_id)


class DailyPlanIn(BaseModel):
    date: date
    available_minutes: int = Field(ge=15, le=960)
    task_ids: list[uuid.UUID] | None = Field(default=None, max_length=25)


@router.post("/daily-plan")
def daily_plan(data: DailyPlanIn, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx),
               provider: AIProvider = Depends(get_provider)) -> dict:
    with _quota(db, provider, "daily_plan") as p:
        return features.daily_plan(db, ctx, p, data.date, data.available_minutes, data.task_ids)


class RangeIn(BaseModel):
    start: date
    end: date


def _check_range(r: RangeIn) -> None:
    if r.end < r.start or (r.end - r.start).days > 92:
        raise invalid("range", "Choose a range of up to three months.")


@router.post("/reasons-summary")
def reasons_summary(data: RangeIn, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx),
                    provider: AIProvider = Depends(get_provider)) -> dict:
    _check_range(data)
    with _quota(db, provider, "reasons_summary") as p:
        return features.reasons_summary(db, ctx, p, data.start, data.end)


@router.post("/habit-review")
def habit_review(data: RangeIn, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx),
                 provider: AIProvider = Depends(get_provider)) -> dict:
    _check_range(data)
    with _quota(db, provider, "habit_review") as p:
        return features.habit_review(db, ctx, p, data.start, data.end)


class PromptsIn(BaseModel):
    focus: Literal["day", "week", "tomorrow"] | None = None


@router.post("/journal-prompts")
def journal_prompts(data: PromptsIn, db: Session = Depends(get_db), provider: AIProvider = Depends(get_provider)) -> dict:
    with _quota(db, provider, "journal_prompts") as p:
        return features.journal_prompts(p, data.focus)


@router.get("/journal-summary/preview")
def journal_preview(dates: list[date] = Query(min_length=1, max_length=14), db: Session = Depends(get_db)) -> dict:
    return features.journal_share_preview(db, sorted(set(dates)))


class JournalSummaryIn(BaseModel):
    dates: list[date] = Field(min_length=1, max_length=14)
    confirm_share: bool  # must be true: the user saw what will be shared and agreed


@router.post("/journal-summary")
def journal_summary(data: JournalSummaryIn, db: Session = Depends(get_db),
                    provider: AIProvider = Depends(get_provider)) -> dict:
    if not data.confirm_share:
        raise invalid("confirm_required", "Journal analysis needs your explicit confirmation of what will be shared.")
    with _quota(db, provider, "journal_summary") as p:
        return features.journal_summary(db, p, sorted(set(data.dates)))


@router.post("/money-review")
def money_review(db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx),
                 provider: AIProvider = Depends(get_provider)) -> dict:
    """Trends, where to cut back and saving tips. Sends calculated totals only (no notes, no balances)."""
    with _quota(db, provider, "money_review") as p:
        return features.money_review(db, ctx, p)
