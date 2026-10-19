"""Local AI endpoints. All of them return proposals only; none of them write data."""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai import features
from app.ai.provider import AIProvider
from app.ai.runner import get_provider
from app.config import get_config
from app.db import get_db
from app.deps import Ctx, get_ctx
from app.errors import invalid

router = APIRouter(prefix="/api/ai", tags=["ai"])

SETUP_STEPS = [
    "Install Ollama on this computer (macOS: brew install ollama).",
    "Start it: ollama serve   (or: brew services start ollama).",
    "Download the model once (needs internet, about 2.5 GB): ollama pull phi4-mini",
    "Reload this page. After the download, AI works offline.",
]


@router.get("/status")
def status(provider: AIProvider = Depends(get_provider)) -> dict:
    s = provider.status()
    return {**s, "provider": provider.name, "model": provider.model,
            "base_url": get_config().ollama_base_url, "setup": SETUP_STEPS}


class BreakdownIn(BaseModel):
    task_id: uuid.UUID


@router.post("/breakdown")
def breakdown(data: BreakdownIn, db: Session = Depends(get_db),
              provider: AIProvider = Depends(get_provider)) -> dict:
    return features.breakdown(db, provider, data.task_id)


class DailyPlanIn(BaseModel):
    date: date
    available_minutes: int = Field(ge=15, le=960)
    task_ids: list[uuid.UUID] | None = Field(default=None, max_length=25)


@router.post("/daily-plan")
def daily_plan(data: DailyPlanIn, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx),
               provider: AIProvider = Depends(get_provider)) -> dict:
    return features.daily_plan(db, ctx, provider, data.date, data.available_minutes, data.task_ids)


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
    return features.reasons_summary(db, ctx, provider, data.start, data.end)


@router.post("/habit-review")
def habit_review(data: RangeIn, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx),
                 provider: AIProvider = Depends(get_provider)) -> dict:
    _check_range(data)
    return features.habit_review(db, ctx, provider, data.start, data.end)


class PromptsIn(BaseModel):
    focus: Literal["day", "week", "tomorrow"] | None = None


@router.post("/journal-prompts")
def journal_prompts(data: PromptsIn, provider: AIProvider = Depends(get_provider)) -> dict:
    return features.journal_prompts(provider, data.focus)


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
    return features.journal_summary(db, provider, sorted(set(data.dates)))


@router.post("/money-review")
def money_review(db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx),
                 provider: AIProvider = Depends(get_provider)) -> dict:
    """Trends, where to cut back and saving tips. Sends calculated totals only (no notes, no balances)."""
    return features.money_review(db, ctx, provider)
