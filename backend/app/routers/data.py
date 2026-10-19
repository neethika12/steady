from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Ctx, get_ctx
from app.services import habits as habit_service
from app.services import insights as insight_service
from app.services import transfer

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/insights/tasks")
def task_insights(start: date, end: date, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    return insight_service.task_insights(db, ctx, start, end)


@router.get("/insights/habits")
def habit_insights(start: date, end: date, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    return habit_service.insights(db, ctx, start, end)


@router.get("/data/export")
def export_data(db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> JSONResponse:
    filename = f"steady-export-{ctx.today.isoformat()}.json"
    return JSONResponse(transfer.export_all(db),
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/data/import")
def import_data(data: transfer.ExportFile, dry_run: bool = True, db: Session = Depends(get_db)) -> dict:
    """Validate (dry_run=true, the default) or apply an export file. See services/transfer.py."""
    report = transfer.import_all(db, data, dry_run)
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return report
