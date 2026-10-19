"""One journal entry per local calendar day, with optimistic conflict detection.

Every save sends the ``version`` the client started editing from. If someone else
(another tab or device) saved in the meantime, the versions differ and the save is
refused with 409 and the newer entry, so nothing is silently overwritten.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import Ctx
from app.errors import conflict, invalid
from app.models import JournalEntry
from app.schemas import JournalOut, JournalSave

FIELDS = ("body", "mood", "energy", "went_well", "was_difficult", "on_mind")


def entry_out(entry: JournalEntry | None, day: date) -> JournalOut:
    if entry is None:
        return JournalOut(entry_date=day, exists=False, version=0, updated_at=None)
    return JournalOut(entry_date=entry.entry_date, exists=True, version=entry.version,
                      updated_at=entry.updated_at,
                      **{f: getattr(entry, f) for f in FIELDS})


def get_entry(db: Session, day: date, lock: bool = False) -> JournalEntry | None:
    stmt = select(JournalEntry).where(JournalEntry.entry_date == day)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalars(stmt).one_or_none()


def _check_day(ctx: Ctx, day: date) -> None:
    if day > ctx.today:
        raise invalid("future_date", "Journal entries can only be written for today or earlier.")


def _is_empty(data: JournalSave) -> bool:
    return (not data.body.strip() and data.mood is None and data.energy is None
            and not data.went_well.strip() and not data.was_difficult.strip()
            and not data.on_mind.strip())


def save_entry(db: Session, ctx: Ctx, day: date, data: JournalSave) -> JournalOut:
    _check_day(ctx, day)
    entry = get_entry(db, day, lock=True)
    if entry is None:
        if data.base_version != 0:
            # The entry the client was editing no longer exists. Treat as a conflict
            # so the user decides; their text stays in the editor and the local draft.
            raise conflict("journal_conflict", "This entry changed elsewhere.",
                           current=entry_out(None, day).model_dump(mode="json"))
        if _is_empty(data):
            return entry_out(None, day)  # don't create blank entries
        entry = JournalEntry(entry_date=day, version=1,
                             **{f: getattr(data, f) for f in FIELDS})
        db.add(entry)
        try:
            db.flush()
        except IntegrityError:
            # Another request created this day's entry at the same moment.
            db.rollback()
            current = get_entry(db, day)
            raise conflict("journal_conflict", "This entry was created elsewhere.",
                           current=entry_out(current, day).model_dump(mode="json"))
        return entry_out(entry, day)

    if entry.version != data.base_version:
        raise conflict("journal_conflict", "This entry was changed elsewhere since you opened it.",
                       current=entry_out(entry, day).model_dump(mode="json"))
    if all(getattr(entry, f) == getattr(data, f) for f in FIELDS):
        return entry_out(entry, day)  # unchanged: repeated autosave
    for f in FIELDS:
        setattr(entry, f, getattr(data, f))
    entry.version += 1
    db.flush()
    return entry_out(entry, day)


def list_entries(db: Session, start: date, end: date) -> list[JournalEntry]:
    return list(db.scalars(
        select(JournalEntry)
        .where(JournalEntry.entry_date >= start, JournalEntry.entry_date <= end)
        .order_by(JournalEntry.entry_date.desc())
    ))
