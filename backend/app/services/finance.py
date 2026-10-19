"""Money: accounts, transactions and the figures shown in the Money tab.

Balances are calculated, never stored:
  debit account  = opening balance + money in - spending from it - card payments made from it
  credit card    = amount owed at setup + spending on it - payments made to it
All amounts are whole cents (integers), so totals never drift.

Splitwise is kept separately: just the two totals from your Splitwise app (what you should get
and what you should pay), entered by hand. It isn't linked to entries.
"""

import calendar
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.deps import Ctx
from app.errors import conflict, invalid, not_found
from app.models import FinanceAccount, FinanceCategory, FinanceRecurring, FinanceSplitwise, FinanceTransaction


def _pct(part: int, whole: int) -> int | None:
    return None if whole <= 0 else (200 * part + whole) // (2 * whole)


def accounts(db: Session, include_archived: bool = False) -> list[FinanceAccount]:
    stmt = select(FinanceAccount).order_by(FinanceAccount.type.desc(), FinanceAccount.created_at)
    if not include_archived:
        stmt = stmt.where(FinanceAccount.archived_at.is_(None))
    return list(db.scalars(stmt))


def balances(db: Session) -> dict[uuid.UUID, int]:
    accs = {a.id: a for a in db.scalars(select(FinanceAccount))}
    bal = {a.id: a.opening_balance_cents for a in accs.values()}
    T = FinanceTransaction
    rows = db.execute(select(T.kind, T.account_id, T.to_account_id, func.sum(T.amount_cents))
                      .group_by(T.kind, T.account_id, T.to_account_id)).all()
    for kind, acc_id, to_id, total in rows:
        total = int(total)
        if kind == "expense":
            bal[acc_id] += total if accs[acc_id].type == "credit" else -total
        elif kind == "income":
            bal[acc_id] += total
        elif kind == "payment":
            bal[acc_id] -= total  # paid out of the debit account
            bal[to_id] -= total  # ...reducing what is owed on the card
    return bal


def splitwise(db: Session) -> FinanceSplitwise | None:
    return db.scalars(select(FinanceSplitwise)).first()  # the signed-in user's row


def splitwise_out(sw: FinanceSplitwise | None) -> dict:
    return {"get_cents": sw.get_cents if sw else 0, "pay_cents": sw.pay_cents if sw else 0,
            "updated_at": sw.updated_at if sw else None}


def set_splitwise(db: Session, ctx: Ctx, get_cents: int | None, pay_cents: int | None) -> FinanceSplitwise:
    """Replace the Splitwise totals (one row per user, created on first save)."""
    db.execute(insert(FinanceSplitwise).values(get_cents=0, pay_cents=0, created_at=ctx.now, updated_at=ctx.now)
               .on_conflict_do_nothing(index_elements=["user_id"]))
    sw = db.scalars(select(FinanceSplitwise).with_for_update()).one()
    if get_cents is not None:
        sw.get_cents = get_cents
    if pay_cents is not None:
        sw.pay_cents = pay_cents
    sw.updated_at = ctx.now
    db.flush()
    return sw


def overview(db: Session) -> dict:
    bal = balances(db)
    items = [{"account": a, "balance_cents": bal[a.id]} for a in accounts(db)]
    available = sum(i["balance_cents"] for i in items if i["account"].type == "debit")
    owed = sum(i["balance_cents"] for i in items if i["account"].type == "credit")
    sw = splitwise_out(splitwise(db))
    return {"accounts": items, "available_cents": available, "owed_cents": owed, "splitwise": sw,
            "net_cents": available - owed + sw["get_cents"] - sw["pay_cents"],
            "set_up": bool(items) or db.scalar(select(func.count()).select_from(FinanceAccount)) > 0}


def get_account(db: Session, account_id: uuid.UUID) -> FinanceAccount:
    a = db.get(FinanceAccount, account_id)
    if a is None:
        raise not_found("Account")
    return a


def create_account(db: Session, ctx: Ctx, name: str, type_: str, balance_cents: int,
                   account_id: uuid.UUID | None = None) -> FinanceAccount:
    if account_id and (existing := db.get(FinanceAccount, account_id)):
        return existing  # repeated submission
    a = FinanceAccount(id=account_id or uuid.uuid4(), name=name.strip(), type=type_,
                       opening_balance_cents=balance_cents, opened_on=ctx.today)
    db.add(a)
    db.flush()
    return a


def setup(db: Session, ctx: Ctx, items: list[dict]) -> list[FinanceAccount]:
    """First-time setup: create every account in one go. Refused once accounts exist."""
    if db.scalar(select(func.count()).select_from(FinanceAccount)):
        raise conflict("already_set_up", "Your accounts are already set up. Add more from “Manage accounts”.")
    if not items:
        raise invalid("no_accounts", "Add at least one debit account or credit card.")
    return [create_account(db, ctx, i["name"], i["type"], i["balance_cents"]) for i in items]


def _validate(db: Session, ctx: Ctx, kind: str, occurred_on: date, account_id: uuid.UUID,
              to_account_id: uuid.UUID | None, category_id: uuid.UUID | None) -> None:
    if occurred_on > ctx.today:
        raise invalid("future_date", "You can only record money for today or earlier.")
    acc = get_account(db, account_id)
    if occurred_on < acc.opened_on:
        raise invalid("before_setup", f"“{acc.name}” was set up on {acc.opened_on.isoformat()} with its balance as of "
                                      "that day, so record things from that day on.")
    to = _validate_shape(db, kind, acc, to_account_id, category_id)
    if to is not None and occurred_on < to.opened_on:
        raise invalid("before_setup", f"“{to.name}” was set up on {to.opened_on.isoformat()}.")


def _validate_shape(db: Session, kind: str, acc: FinanceAccount, to_account_id: uuid.UUID | None,
                    category_id: uuid.UUID | None) -> FinanceAccount | None:
    """Which accounts and categories each kind of entry may use. Returns the card for a payment."""
    if kind == "payment":
        to = get_account(db, to_account_id) if to_account_id else None
        if acc.type != "debit" or to is None or to.type != "credit":
            raise invalid("payment_accounts", "A card payment goes from a debit account to a credit card.")
        return to
    cat = db.get(FinanceCategory, category_id) if category_id else None
    if cat is None:
        raise invalid("category", "Choose what it was for.")
    if cat.kind != kind:
        raise invalid("category", "That category doesn't match the type of entry.")
    if kind == "income" and acc.type != "debit":
        raise invalid("income_account", "Money in goes to a debit account. To pay a card, use “Card payment”.")
    return None


def create_transaction(db: Session, ctx: Ctx, data) -> tuple[FinanceTransaction, bool]:
    if data.id and (existing := db.get(FinanceTransaction, data.id)):
        return existing, False  # repeated submission
    occurred_on = data.occurred_on or ctx.today
    _validate(db, ctx, data.kind, occurred_on, data.account_id, data.to_account_id, data.category_id)
    t = FinanceTransaction(id=data.id or uuid.uuid4(), occurred_on=occurred_on, kind=data.kind,
                           amount_cents=data.amount_cents, account_id=data.account_id,
                           to_account_id=data.to_account_id if data.kind == "payment" else None,
                           category_id=data.category_id if data.kind != "payment" else None,
                           note=(data.note or "").strip())
    db.add(t)
    db.flush()
    return t, True


def update_transaction(db: Session, ctx: Ctx, t: FinanceTransaction, changes: dict) -> FinanceTransaction:
    merged = {"kind": t.kind, "occurred_on": t.occurred_on, "account_id": t.account_id,
              "to_account_id": t.to_account_id, "category_id": t.category_id, **changes}
    _validate(db, ctx, merged["kind"], merged["occurred_on"], merged["account_id"],
              merged["to_account_id"], merged["category_id"])
    for k, v in changes.items():
        setattr(t, k, v.strip() if k == "note" and isinstance(v, str) else v)
    if t.kind == "payment":
        t.category_id = None
    else:
        t.to_account_id = None
    db.flush()
    return t


def _names(db: Session) -> tuple[dict, dict]:
    accs = {a.id: a for a in db.scalars(select(FinanceAccount))}
    cats = {c.id: c for c in db.scalars(select(FinanceCategory))}
    return accs, cats


def transaction_out(t: FinanceTransaction, accs: dict, cats: dict) -> dict:
    return {
        "id": t.id, "occurred_on": t.occurred_on, "kind": t.kind, "amount_cents": t.amount_cents,
        "account_id": t.account_id, "account_name": accs[t.account_id].name, "account_type": accs[t.account_id].type,
        "to_account_id": t.to_account_id, "to_account_name": accs[t.to_account_id].name if t.to_account_id else None,
        "category_id": t.category_id, "category_name": cats[t.category_id].name if t.category_id else None,
        "note": t.note, "recurring_id": t.recurring_id, "created_at": t.created_at,
    }


def transactions_between(db: Session, start: date, end: date) -> list[FinanceTransaction]:
    return list(db.scalars(select(FinanceTransaction)
                           .where(FinanceTransaction.occurred_on >= start, FinanceTransaction.occurred_on <= end)
                           .order_by(FinanceTransaction.occurred_on.desc(), FinanceTransaction.created_at.desc())))


def day(db: Session, ctx: Ctx, d: date) -> dict:
    accs, cats = _names(db)
    txs = transactions_between(db, d, d)
    return {
        "date": d,
        "transactions": [transaction_out(t, accs, cats) for t in txs],
        "spent_cents": sum(t.amount_cents for t in txs if t.kind == "expense"),
        "income_cents": sum(t.amount_cents for t in txs if t.kind == "income"),
        "scheduled": scheduled_on(db, ctx, d),
    }


def month_bounds(month: str) -> tuple[date, date]:
    try:
        y, m = (int(x) for x in month.split("-"))
        first = date(y, m, 1)
    except ValueError:
        raise invalid("month", "Month must look like 2026-10.")
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def month(db: Session, ctx: Ctx, month_str: str) -> dict:
    first, last = month_bounds(month_str)
    accs, cats = _names(db)
    txs = transactions_between(db, first, last)
    expenses = [t for t in txs if t.kind == "expense"]
    spent = sum(t.amount_cents for t in expenses)
    by_cat: dict = defaultdict(int)
    for t in expenses:
        by_cat[t.category_id] += t.amount_cents
    daily: dict = defaultdict(int)
    for t in expenses:
        daily[t.occurred_on] += t.amount_cents
    # Days that count towards the average: the whole month if it's over, up to today if it's this month.
    days_counted = 0 if first > ctx.today else ((min(last, ctx.today) - first).days + 1)
    prev_first, prev_last = month_bounds(f"{(first - timedelta(days=1)).year}-{(first - timedelta(days=1)).month:02d}")
    prev_spent = sum(t.amount_cents for t in transactions_between(db, prev_first, prev_last) if t.kind == "expense")
    return {
        "month": month_str, "start": first, "end": last,
        "spent_cents": spent,
        "income_cents": sum(t.amount_cents for t in txs if t.kind == "income"),
        "card_payments_cents": sum(t.amount_cents for t in txs if t.kind == "payment"),
        "by_category": sorted(
            [{"category_id": cid, "name": cats[cid].name, "spent_cents": c, "share_pct": _pct(c, spent)}
             for cid, c in by_cat.items()], key=lambda r: -r["spent_cents"]),
        "daily": [{"date": d, "spent_cents": c} for d, c in sorted(daily.items())],
        "days_counted": days_counted,
        "avg_per_day_cents": (spent // days_counted) if days_counted else None,
        "previous_month_spent_cents": prev_spent,
        "top_expenses": [transaction_out(t, accs, cats) for t in sorted(expenses, key=lambda t: -t.amount_cents)[:3]],
    }


# ---------------------------------------------------------------- repeating entries

MAX_CATCH_UP = 400  # per rule per request; a weekly rule untouched for years can't run away


def occurrence(anchor: date, frequency: str, interval: int, n: int) -> date:
    """The n-th date (from 0) of a schedule. Monthly/yearly clamp to the end of short months."""
    if frequency == "weekly":
        return anchor + timedelta(weeks=interval * n)
    months = interval * n * (12 if frequency == "yearly" else 1)
    y, m = divmod(anchor.month - 1 + months, 12)
    y, m = anchor.year + y, m + 1
    return date(y, m, min(anchor.day, calendar.monthrange(y, m)[1]))


def next_on(r: FinanceRecurring) -> date:
    return occurrence(r.anchor_on, r.frequency, r.interval, r.posted_count)


def _skip_to(r: FinanceRecurring, today: date) -> None:
    """Move past occurrences before ``today`` without adding them (used when resuming)."""
    while next_on(r) < today:
        r.posted_count += 1


def catch_up(db: Session, ctx: Ctx) -> int:
    """Add an entry for every occurrence of an active rule that is due on or before today.

    Safe to run on every read: the rule rows are locked while this runs, and each rule can add
    only one entry per day (unique constraint), so simultaneous requests never double-post.
    Returns how many entries were added.
    """
    due = db.scalar(select(func.count()).select_from(FinanceRecurring)
                    .where(FinanceRecurring.paused_at.is_(None))
                    .where(FinanceRecurring.anchor_on <= ctx.today))
    if not due:
        return 0
    rules = db.scalars(select(FinanceRecurring).where(FinanceRecurring.paused_at.is_(None))
                       .order_by(FinanceRecurring.created_at).with_for_update()).all()
    added = 0
    for r in rules:
        for _ in range(MAX_CATCH_UP):
            when = next_on(r)
            if when > ctx.today:
                break
            res = db.execute(insert(FinanceTransaction).values(
                id=uuid.uuid4(), occurred_on=when, kind=r.kind, amount_cents=r.amount_cents,
                account_id=r.account_id, to_account_id=r.to_account_id, category_id=r.category_id,
                note=r.name, recurring_id=r.id, created_at=ctx.now, updated_at=ctx.now,
            ).on_conflict_do_nothing(constraint="uq_finance_transactions_recurring_day"))
            added += res.rowcount or 0
            r.posted_count += 1
    db.commit()
    return added


def _check_rule(db: Session, kind: str, account_id: uuid.UUID, to_account_id: uuid.UUID | None,
                category_id: uuid.UUID | None) -> None:
    acc = get_account(db, account_id)
    if acc.archived_at is not None:
        raise invalid("archived_account", f"“{acc.name}” is archived. Restore it first, or choose another account.")
    to = _validate_shape(db, kind, acc, to_account_id, category_id)
    if to is not None and to.archived_at is not None:
        raise invalid("archived_account", f"“{to.name}” is archived. Restore it first, or choose another card.")


def _check_start(ctx: Ctx, start: date) -> None:
    if start < ctx.today:
        raise invalid("past_start", "Choose today or a later date for the next one. "
                                    "Record earlier ones as normal entries.")


def get_rule(db: Session, rule_id: uuid.UUID) -> FinanceRecurring:
    r = db.get(FinanceRecurring, rule_id)
    if r is None:
        raise not_found("Repeating entry")
    return r


def create_rule(db: Session, ctx: Ctx, data) -> tuple[FinanceRecurring, bool]:
    if data.id and (existing := db.get(FinanceRecurring, data.id)):
        return existing, False  # repeated submission
    _check_rule(db, data.kind, data.account_id, data.to_account_id, data.category_id)
    _check_start(ctx, data.next_on)
    r = FinanceRecurring(id=data.id or uuid.uuid4(), name=data.name.strip(), kind=data.kind,
                         amount_cents=data.amount_cents, account_id=data.account_id,
                         to_account_id=data.to_account_id if data.kind == "payment" else None,
                         category_id=data.category_id if data.kind != "payment" else None,
                         frequency=data.frequency, interval=data.interval, anchor_on=data.next_on, posted_count=0)
    db.add(r)
    db.flush()
    return r, True


def update_rule(db: Session, ctx: Ctx, r: FinanceRecurring, changes: dict) -> FinanceRecurring:
    """Changes apply from the next occurrence on; entries already added are left as they are."""
    paused = changes.pop("paused", None)
    merged = {"kind": r.kind, "account_id": r.account_id, "to_account_id": r.to_account_id,
              "category_id": r.category_id, **{k: v for k, v in changes.items()
                                                if k in ("kind", "account_id", "to_account_id", "category_id")}}
    if merged["kind"] == "payment":
        merged["category_id"] = None
    else:
        merged["to_account_id"] = None
    _check_rule(db, merged["kind"], merged["account_id"], merged["to_account_id"], merged["category_id"])
    schedule_changed = any(k in changes and changes[k] != getattr(r, k) for k in ("frequency", "interval")) or (
        "next_on" in changes and changes["next_on"] != next_on(r))
    if schedule_changed:
        start = changes.get("next_on") or next_on(r)
        if start < ctx.today:
            start = ctx.today if "next_on" not in changes else start
        _check_start(ctx, start)
        r.anchor_on, r.posted_count = start, 0
    for k in ("name", "amount_cents", "frequency", "interval"):
        if k in changes:
            setattr(r, k, changes[k].strip() if k == "name" else changes[k])
    for k, v in merged.items():
        setattr(r, k, v)
    if paused is True and r.paused_at is None:
        r.paused_at = ctx.now
    elif paused is False and r.paused_at is not None:
        r.paused_at = None
        _skip_to(r, ctx.today)  # nothing is added for dates missed while paused
    db.flush()
    return r


def rule_out(r: FinanceRecurring, accs: dict, cats: dict, ctx: Ctx) -> dict:
    nxt = next_on(r)
    return {
        "id": r.id, "name": r.name, "kind": r.kind, "amount_cents": r.amount_cents,
        "account_id": r.account_id, "account_name": accs[r.account_id].name,
        "to_account_id": r.to_account_id, "to_account_name": accs[r.to_account_id].name if r.to_account_id else None,
        "category_id": r.category_id, "category_name": cats[r.category_id].name if r.category_id else None,
        "frequency": r.frequency, "interval": r.interval, "anchor_on": r.anchor_on, "day_of_month": r.anchor_on.day,
        "weekday": r.anchor_on.weekday(), "paused": r.paused_at is not None,
        "next_on": None if r.paused_at is not None else nxt,
    }


def rules_summary(db: Session, ctx: Ctx) -> dict:
    accs, cats = _names(db)
    rules = list(db.scalars(select(FinanceRecurring).order_by(FinanceRecurring.created_at)))
    horizon = ctx.today + timedelta(days=30)
    due_30 = 0
    for r in rules:
        if r.paused_at is not None or r.kind != "expense":
            continue
        n = r.posted_count
        while (d := occurrence(r.anchor_on, r.frequency, r.interval, n)) <= horizon:
            if d >= ctx.today:
                due_30 += r.amount_cents
            n += 1
    items = [rule_out(r, accs, cats, ctx) for r in rules]
    items.sort(key=lambda i: (i["paused"], i["next_on"] or date.max, i["name"].lower()))
    return {"rules": items, "bills_next_30_days_cents": due_30}


def scheduled_on(db: Session, ctx: Ctx, d: date) -> list[dict]:
    """Repeating entries that will be added on a future day (shown, not yet recorded)."""
    if d <= ctx.today or d > ctx.today + timedelta(days=800):
        return []
    accs, cats = _names(db)
    out = []
    for r in db.scalars(select(FinanceRecurring).where(FinanceRecurring.paused_at.is_(None))):
        n = r.posted_count
        while (when := occurrence(r.anchor_on, r.frequency, r.interval, n)) < d:
            n += 1
        if when == d:
            out.append(rule_out(r, accs, cats, ctx))
    return sorted(out, key=lambda i: i["name"].lower())


# ---------------------------------------------------------------- trends (calculated, no AI)

def add_months(first_of_month: date, n: int) -> date:
    y, m = divmod(first_of_month.month - 1 + n, 12)
    return date(first_of_month.year + y, m + 1, 1)


def monthly_equivalent(r: FinanceRecurring) -> int:
    """A repeating amount expressed per month (weekly ≈ 52/12 times a month)."""
    if r.frequency == "weekly":
        return round(r.amount_cents * 52 / 12 / r.interval)
    if r.frequency == "yearly":
        return round(r.amount_cents / (12 * r.interval))
    return round(r.amount_cents / r.interval)


def trends(db: Session, ctx: Ctx, full_months: int = 3) -> dict:
    """The last ``full_months`` complete months plus this month so far: totals, savings and categories."""
    this_first = ctx.today.replace(day=1)
    starts = [add_months(this_first, -i) for i in range(full_months, 0, -1)] + [this_first]
    txs = transactions_between(db, starts[0], ctx.today)
    first_entry = db.scalar(select(func.min(FinanceTransaction.occurred_on)))
    _, cats = _names(db)

    months = []
    per_cat: dict = defaultdict(dict)
    by_day_n: dict = defaultdict(dict)  # spending up to the same day of the month as today, per category
    for ms in starts:
        current = ms == this_first
        me = ctx.today if current else add_months(ms, 1) - timedelta(days=1)
        rows = [t for t in txs if ms <= t.occurred_on <= me]
        spent = sum(t.amount_cents for t in rows if t.kind == "expense")
        income = sum(t.amount_cents for t in rows if t.kind == "income")
        key = ms.strftime("%Y-%m")
        for t in rows:
            if t.kind == "expense":
                per_cat[t.category_id][key] = per_cat[t.category_id].get(key, 0) + t.amount_cents
                if t.occurred_on.day <= ctx.today.day:
                    by_day_n[t.category_id][key] = by_day_n[t.category_id].get(key, 0) + t.amount_cents
        months.append({
            "month": key, "complete": not current, "days": (me - ms).days + 1,
            "days_in_month": (add_months(ms, 1) - ms).days,
            # A month counts only if you were tracking by then (else its zeros would drag averages down).
            "tracked": first_entry is not None and first_entry <= me,
            "spent_cents": spent, "income_cents": income, "saved_cents": income - spent,
            "savings_rate_pct": _pct(income - spent, income) if income > 0 else None,
        })
    full = [m for m in months if m["complete"] and m["tracked"]]
    now = months[-1]

    categories = []
    for cid, by_month in per_cat.items():
        full_amounts = [by_month.get(m["month"], 0) for m in full]
        avg = (sum(full_amounts) // len(full_amounts)) if full_amounts else None
        so_far = by_month.get(now["month"], 0)
        # Compare like with like: this month so far vs. the same days of earlier months (not a projection,
        # which would make a once-a-month bill like rent look like it's doubling).
        usual = (sum(by_day_n[cid].get(m["month"], 0) for m in full) // len(full)) if full else None
        categories.append({
            "category_id": cid, "name": cats[cid].name,
            "by_month": [{"month": m["month"], "spent_cents": by_month.get(m["month"], 0)} for m in months],
            "avg_monthly_cents": avg, "this_month_cents": so_far, "usual_by_today_cents": usual,
            "change_pct": _pct(so_far - usual, usual) if usual else None,
        })
    categories.sort(key=lambda c: -(c["avg_monthly_cents"] if c["avg_monthly_cents"] is not None else c["this_month_cents"]))

    accs, _ = _names(db)
    bills = [{"name": r.name, "category_id": r.category_id, "account_name": accs[r.account_id].name,
              "monthly_cents": monthly_equivalent(r), "frequency": r.frequency, "interval": r.interval}
             for r in db.scalars(select(FinanceRecurring).where(FinanceRecurring.paused_at.is_(None),
                                                                 FinanceRecurring.kind == "expense"))]
    bills.sort(key=lambda b: -b["monthly_cents"])
    avg_spent = (sum(m["spent_cents"] for m in full) // len(full)) if full else None
    avg_income = (sum(m["income_cents"] for m in full) // len(full)) if full else None
    return {
        "months": months, "full_months_counted": len(full),
        "avg_monthly_spent_cents": avg_spent, "avg_monthly_income_cents": avg_income,
        "this_month_cents": now["spent_cents"],
        "usual_by_today_cents": (sum(sum(by_day_n[c].get(m["month"], 0) for c in by_day_n) for m in full) // len(full)
                                 if full else None),
        "day_of_month": ctx.today.day,
        "categories": categories,
        "repeating_bills": bills, "repeating_monthly_cents": sum(b["monthly_cents"] for b in bills),
        "splitwise": splitwise_out(splitwise(db)),
        "expense_entries": sum(1 for t in txs if t.kind == "expense"),
    }
