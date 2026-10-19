"""Money tab API. No AI is involved anywhere in money tracking."""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Ctx, get_ctx
from app.errors import invalid, not_found
from app.models import FinanceCategory, FinanceRecurring, FinanceTransaction
from app.services import finance as service

router = APIRouter(prefix="/api/finance", tags=["money"])

MAX_CENTS = 100_000_000_000  # a billion: guards against typos like extra zeros


class AccountIn(BaseModel):
    id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=60)
    type: Literal["debit", "credit"]
    balance_cents: int = Field(ge=-MAX_CENTS, le=MAX_CENTS)  # debit: money in it; credit: amount owed

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Give the account a name")
        return v.strip()


class SetupIn(BaseModel):
    accounts: list[AccountIn] = Field(min_length=1, max_length=20)


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    opening_balance_cents: int | None = Field(default=None, ge=-MAX_CENTS, le=MAX_CENTS)
    archived: bool | None = None


class AccountOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    opening_balance_cents: int
    opened_on: date
    archived: bool
    balance_cents: int


class TransactionIn(BaseModel):
    id: uuid.UUID | None = None
    kind: Literal["expense", "income", "payment"] = "expense"
    amount_cents: int = Field(gt=0, le=MAX_CENTS)
    occurred_on: date | None = None
    account_id: uuid.UUID
    to_account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    note: str = Field(default="", max_length=500)


class TransactionUpdate(BaseModel):
    kind: Literal["expense", "income", "payment"] | None = None
    amount_cents: int | None = Field(default=None, gt=0, le=MAX_CENTS)
    occurred_on: date | None = None
    account_id: uuid.UUID | None = None
    to_account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class SplitwiseIn(BaseModel):
    get_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)  # you should get
    pay_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)  # you should pay


class RecurringIn(BaseModel):
    id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["expense", "income", "payment"] = "expense"
    amount_cents: int = Field(gt=0, le=MAX_CENTS)
    account_id: uuid.UUID
    to_account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    frequency: Literal["weekly", "monthly", "yearly"] = "monthly"
    interval: int = Field(default=1, ge=1, le=12)
    next_on: date

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Give it a name, like Rent or Netflix")
        return v.strip()


class RecurringUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    kind: Literal["expense", "income", "payment"] | None = None
    amount_cents: int | None = Field(default=None, gt=0, le=MAX_CENTS)
    account_id: uuid.UUID | None = None
    to_account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    frequency: Literal["weekly", "monthly", "yearly"] | None = None
    interval: int | None = Field(default=None, ge=1, le=12)
    next_on: date | None = None
    paused: bool | None = None


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["expense", "income"] = "expense"


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    archived: bool | None = None


def _account_out(a, balance: int) -> AccountOut:
    return AccountOut(id=a.id, name=a.name, type=a.type, opening_balance_cents=a.opening_balance_cents,
                      opened_on=a.opened_on, archived=a.archived_at is not None, balance_cents=balance)


@router.get("/overview")
def overview(db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    service.catch_up(db, ctx)  # add any repeating entries that have come due
    o = service.overview(db)
    return {**o, "accounts": [_account_out(i["account"], i["balance_cents"]) for i in o["accounts"]]}


@router.post("/setup")
def setup(data: SetupIn, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    service.setup(db, ctx, [{"name": a.name, "type": a.type, "balance_cents": a.balance_cents} for a in data.accounts])
    db.commit()
    return overview(db, ctx)


@router.post("/accounts", response_model=AccountOut, status_code=201)
def add_account(data: AccountIn, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> AccountOut:
    a = service.create_account(db, ctx, data.name, data.type, data.balance_cents, data.id)
    db.commit()
    return _account_out(a, service.balances(db)[a.id])


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def edit_account(account_id: uuid.UUID, data: AccountUpdate, db: Session = Depends(get_db),
                 ctx: Ctx = Depends(get_ctx)) -> AccountOut:
    a = service.get_account(db, account_id)
    if data.name is not None:
        a.name = data.name.strip()
    if data.opening_balance_cents is not None:
        a.opening_balance_cents = data.opening_balance_cents
    if data.archived is not None:
        a.archived_at = ctx.now if data.archived else None
    db.commit()
    return _account_out(a, service.balances(db)[a.id])


@router.get("/categories")
def categories(include_archived: bool = False, db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(FinanceCategory).order_by(FinanceCategory.kind, FinanceCategory.sort_order, FinanceCategory.name)
    if not include_archived:
        stmt = stmt.where(FinanceCategory.archived_at.is_(None))
    return [{"id": c.id, "name": c.name, "kind": c.kind, "archived": c.archived_at is not None} for c in db.scalars(stmt)]


@router.post("/categories", status_code=201)
def add_category(data: CategoryIn, db: Session = Depends(get_db)) -> dict:
    c = FinanceCategory(name=data.name.strip(), kind=data.kind, sort_order=1000)
    db.add(c)
    db.commit()
    return {"id": c.id, "name": c.name, "kind": c.kind, "archived": False}


@router.patch("/categories/{category_id}")
def edit_category(category_id: uuid.UUID, data: CategoryUpdate, db: Session = Depends(get_db),
                  ctx: Ctx = Depends(get_ctx)) -> dict:
    c = db.get(FinanceCategory, category_id)
    if c is None:
        raise not_found("Category")
    if data.name is not None:
        c.name = data.name.strip()
    if data.archived is not None:
        c.archived_at = ctx.now if data.archived else None
    db.commit()
    return {"id": c.id, "name": c.name, "kind": c.kind, "archived": c.archived_at is not None}


@router.get("/day")
def day(date: date, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    service.catch_up(db, ctx)
    return service.day(db, ctx, date)


@router.get("/month")
def month(month: str, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    service.catch_up(db, ctx)
    return service.month(db, ctx, month)


# Repeating entries: each one is added automatically on its date (the next time the Money tab
# loads), as an ordinary entry you can edit or delete.

@router.get("/recurring")
def recurring(db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    service.catch_up(db, ctx)
    return service.rules_summary(db, ctx)


def _rule_response(db: Session, ctx: Ctx, r: FinanceRecurring) -> dict:
    accs, cats = service._names(db)
    return service.rule_out(r, accs, cats, ctx)


@router.post("/recurring", status_code=201)
def add_recurring(data: RecurringIn, response: Response, db: Session = Depends(get_db),
                  ctx: Ctx = Depends(get_ctx)) -> dict:
    r, created = service.create_rule(db, ctx, data)
    db.commit()
    if not created:
        response.status_code = 200
    service.catch_up(db, ctx)  # one starting today is added right away
    return _rule_response(db, ctx, r)


@router.patch("/recurring/{rule_id}")
def edit_recurring(rule_id: uuid.UUID, data: RecurringUpdate, db: Session = Depends(get_db),
                   ctx: Ctx = Depends(get_ctx)) -> dict:
    r = service.get_rule(db, rule_id)
    service.update_rule(db, ctx, r, data.model_dump(exclude_unset=True))
    db.commit()
    service.catch_up(db, ctx)
    return _rule_response(db, ctx, r)


@router.delete("/recurring/{rule_id}", status_code=204)
def delete_recurring(rule_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """Stops it repeating. Entries it already added stay, as ordinary entries."""
    r = db.get(FinanceRecurring, rule_id)
    if r is not None:  # deleting twice is harmless
        db.delete(r)
        db.commit()
    return Response(status_code=204)


@router.post("/transactions", status_code=201)
def add_transaction(data: TransactionIn, response: Response, db: Session = Depends(get_db),
                    ctx: Ctx = Depends(get_ctx)) -> dict:
    t, created = service.create_transaction(db, ctx, data)
    db.commit()
    if not created:
        response.status_code = 200
    accs, cats = service._names(db)
    return service.transaction_out(t, accs, cats)


@router.patch("/transactions/{transaction_id}")
def edit_transaction(transaction_id: uuid.UUID, data: TransactionUpdate, db: Session = Depends(get_db),
                     ctx: Ctx = Depends(get_ctx)) -> dict:
    t = db.get(FinanceTransaction, transaction_id)
    if t is None:
        raise not_found("Entry")
    service.update_transaction(db, ctx, t, data.model_dump(exclude_unset=True))
    db.commit()
    accs, cats = service._names(db)
    return service.transaction_out(t, accs, cats)


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    t = db.get(FinanceTransaction, transaction_id)
    if t is not None:  # deleting twice is harmless
        db.delete(t)
        db.commit()
    return Response(status_code=204)



@router.get("/trends")
def trends(db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    """The last three complete months and this month so far, calculated (no AI)."""
    service.catch_up(db, ctx)
    return service.trends(db, ctx)


@router.put("/splitwise")
def set_splitwise(data: SplitwiseIn, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)) -> dict:
    """Replace your Splitwise totals (copied from the Splitwise app)."""
    sw = service.set_splitwise(db, ctx, data.get_cents, data.pay_cents)
    db.commit()
    return service.splitwise_out(sw)
