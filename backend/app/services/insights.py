"""Deterministic To-Do insights. Habit insights live in services/habits.py.

Task and habit metrics are deliberately never combined.
"""

from collections import Counter
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.deps import Ctx
from app.errors import invalid
from app.models import REASON_LABELS
from app.services.tasks import _PlanFacts, _pct, compute_day_stats, plans_between, plans_out


def task_insights(db: Session, ctx: Ctx, start: date, end: date) -> dict:
    if end < start or (end - start).days > 366:
        raise invalid("range", "Choose a range of up to one year.")
    end_eval = min(end, ctx.today)
    plans = plans_between(db, start, end_eval) if end_eval >= start else []
    serialized = plans_out(db, plans, ctx.today)

    days = []
    d = start
    while d <= end_eval:
        facts = [_PlanFacts(p.plan_date, p.outcome, p.carried_from_plan_id is not None,
                            p.task.estimated_minutes) for p in serialized if p.plan_date == d]
        days.append(compute_day_stats(d, ctx.today, facts))
        d += timedelta(days=1)

    keys = ("planned", "counted", "completed", "partial", "not_completed",
            "awaiting_review", "open", "cancelled", "carried_in")
    totals = {k: sum(getattr(s, k) for s in days) for k in keys}
    totals["completion_pct"] = _pct(totals["completed"], totals["counted"])
    totals["days_with_plans"] = sum(1 for s in days if s.planned)
    totals["days_without_plans"] = sum(1 for s in days if not s.planned)

    # Non-completion reasons: only plans explicitly reviewed as partly/not completed.
    unfinished = [p for p in serialized if p.outcome in ("partial", "not_completed")]
    with_reason = [p for p in unfinished if p.reason or p.reason_note]
    tagged = [p for p in with_reason if p.reason]
    by_reason = Counter(p.reason for p in tagged)
    reasons = {
        "unfinished": len(unfinished),
        "with_reason": len(with_reason),
        "without_reason": len(unfinished) - len(with_reason),
        "tagged": len(tagged),
        "untagged": len(with_reason) - len(tagged),
        "by_reason": [{"reason": r, "label": REASON_LABELS[r], "count": n}
                      for r, n in by_reason.most_common()],
        "records": [{"plan_id": p.id, "date": p.plan_date, "task_title": p.task.title,
                     "outcome": p.outcome, "reason": p.reason, "note": p.reason_note} for p in with_reason],
    }

    # Carryover: how often tasks moved to a later day.
    carried = [p for p in serialized if p.carried_from_plan_id]
    per_task = Counter()
    titles = {}
    for p in carried:
        per_task[p.task_id] = max(per_task[p.task_id], p.times_carried)
        titles[p.task_id] = p.task.title
    carryover = {
        "carried_plans": len(carried),
        "tasks_carried": len(per_task),
        "share_of_plans_pct": _pct(len(carried), len(serialized)),
        "most_carried": [{"task_id": t, "title": titles[t], "times_carried": n}
                         for t, n in per_task.most_common(5)],
    }

    # Estimated vs actual, for completed tasks that have both numbers.
    seen = set()
    duration_rows = []
    for p in serialized:
        t = p.task
        if p.outcome == "completed" and t.id not in seen and t.estimated_minutes and t.actual_minutes is not None:
            seen.add(t.id)
            duration_rows.append({"task_id": t.id, "title": t.title, "date": p.plan_date,
                                  "estimated_minutes": t.estimated_minutes,
                                  "actual_minutes": t.actual_minutes})
    completed_total = sum(1 for p in serialized if p.outcome == "completed")
    durations = {
        "tasks_with_both": len(duration_rows),
        "completed_without_actual": completed_total - len(duration_rows),
        "estimated_total": sum(r["estimated_minutes"] for r in duration_rows),
        "actual_total": sum(r["actual_minutes"] for r in duration_rows),
        "rows": duration_rows[:50],
    }
    return {"start": start, "end": end, "evaluated_through": end_eval, "totals": totals,
            "days": days, "reasons": reasons, "carryover": carryover, "durations": durations}
