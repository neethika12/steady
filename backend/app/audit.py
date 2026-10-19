"""Append-only audit trail for changes to dated history."""

import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def _plain(value: Any) -> Any:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def snapshot(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: _plain(getattr(obj, f)) for f in fields}


PLAN_FIELDS = ("plan_date", "planned_time", "planned_end_time", "outcome", "reason", "reason_note", "completed_at", "follow_up")
TASK_FIELDS = (
    "title", "description", "priority", "category", "estimated_minutes",
    "actual_minutes", "deadline", "planned_date", "status", "archived_at",
)


def record(
    db: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
    note: str | None = None,
) -> None:
    db.add(AuditLog(entity_type=entity_type, entity_id=entity_id, action=action,
                    before=before, after=after, note=note))
