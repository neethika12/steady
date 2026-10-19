from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Ctx, get_ctx
from app.errors import invalid
from app.schemas import JournalListItem, JournalOut, JournalSave
from app.services import journal as service

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("", response_model=list[JournalListItem])
def list_entries(start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
                 ctx: Ctx = Depends(get_ctx)) -> list[JournalListItem]:
    end = end or ctx.today
    start = start or end - timedelta(days=90)
    if end < start or (end - start).days > 400:
        raise invalid("range", "Choose a range of up to about a year.")
    out = []
    for e in service.list_entries(db, start, end):
        text = " ".join(e.body.split())
        out.append(JournalListItem(entry_date=e.entry_date, snippet=text[:140],
                                   word_count=len(e.body.split()), mood=e.mood, energy=e.energy,
                                   updated_at=e.updated_at))
    return out


@router.get("/{day}", response_model=JournalOut)
def read_entry(day: date, db: Session = Depends(get_db)) -> JournalOut:
    return service.entry_out(service.get_entry(db, day), day)


@router.put("/{day}", response_model=JournalOut)
def save_entry(day: date, data: JournalSave, db: Session = Depends(get_db),
               ctx: Ctx = Depends(get_ctx)) -> JournalOut:
    result = service.save_entry(db, ctx, day, data)
    db.commit()
    return result
