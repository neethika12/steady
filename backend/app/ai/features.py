"""The six AI features. Each one:

1. selects the records to send with ordinary code (never "the whole database"),
2. gives every record a short ref (T1, R1, H1, or a date) and sends minimal fields,
3. validates the reply against a schema and checks every ref it cites exists,
4. does any arithmetic (time budgets, counts, percentages) itself,
5. returns a proposal. Nothing is saved until the user accepts it through the
   normal endpoints.
"""

import json
import re
import uuid
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai import runner
from app.ai.provider import AIProvider
from app.ai.runner import ProposalRejected, asks_for_more, check_language, check_numbers, name_refs, tidy
from app.deps import Ctx
from app.errors import invalid
from app.models import REASON_LABELS, Task, TaskPlan
from app.services import finance as finance_service
from app.services import habits as habit_service
from app.services import journal as journal_service
from app.services import tasks as task_service

_PRIORITY = {"high": 0, "medium": 1, "low": 2}


def destination() -> str:
    """Where AI requests go, in plain words (shown before journal entries are shared)."""
    if runner.default_provider().name == "groq":
        return "Groq's AI service (it doesn't keep or train on what's sent)"
    return "the local Ollama model on this computer"


def _clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _str(max_len: int, min_len: int = 1) -> dict:
    return {"type": "string", "minLength": min_len, "maxLength": max_len}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


def _arr(items: dict, lo: int, hi: int) -> dict:
    return {"type": "array", "items": items, "minItems": lo, "maxItems": hi}


def _refs_ok(refs: list[str], known: set[str], what: str) -> None:
    unknown = [r for r in refs if r not in known]
    if unknown:
        raise ProposalRejected(f"it referred to {what} that were not supplied ({', '.join(unknown[:3])})")


# ---------------------------------------------------------------- 1. break down

class _Step(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    estimated_minutes: int = Field(ge=5, le=240)


class _Breakdown(BaseModel):
    steps: list[_Step] = Field(min_length=2, max_length=8)


BREAKDOWN_SCHEMA = _obj({"steps": _arr(_obj({"title": _str(120, 3), "estimated_minutes": {"type": "integer", "minimum": 5, "maximum": 240}}), 2, 8)})


def breakdown(db: Session, provider: AIProvider, task_id: uuid.UUID) -> dict:
    task = db.get(Task, task_id)
    if task is None or task.status != "active":
        raise invalid("ai_source", "Choose an active task to break down.")
    title, extra, estimate = task.title, _clip(task.description, 400), task.estimated_minutes
    record = {"title": title}
    if extra:
        record["details"] = extra
    if estimate:
        record["estimated_minutes"] = estimate
    prompt = (
        "Break this single item into 2 to 6 small, concrete next actions that together achieve it. "
        "Each step starts with a verb, keeps the person's own wording where possible, and gets a realistic "
        "estimate in minutes. Do not add goals the item doesn't mention.\n"
        f"ITEM: {json.dumps(record, ensure_ascii=False)}"
    )

    def validate(ans: _Breakdown, last_attempt: bool) -> dict:
        titles = [s.title.strip() for s in ans.steps]
        if len({t.lower() for t in titles}) != len(titles):
            raise ProposalRejected("it repeated a step")
        check_language(*titles)
        total = sum(s.estimated_minutes for s in ans.steps)
        return {
            "source": {"type": "task", "id": task_id, "title": title},
            "steps": [{"title": s.title.strip(), "estimated_minutes": s.estimated_minutes} for s in ans.steps],
            "total_minutes": total,
            "original_estimate": estimate,
            "exceeds_original_estimate": bool(estimate and total > estimate),
            "shared": {"fields": list(record)},
        }

    return runner.run(provider, "breakdown", prompt, BREAKDOWN_SCHEMA, _Breakdown, validate, max_tokens=400)


# ---------------------------------------------------------------- 2. daily plan

class _Pick(BaseModel):
    ref: str = Field(max_length=6)
    reason: str = Field(min_length=3, max_length=200)


class _Plan(BaseModel):
    selected: list[_Pick] = Field(min_length=1, max_length=25)
    note: str = Field(default="", max_length=300)


def _candidate_tasks(db: Session, ctx: Ctx, day: date, task_ids: list[uuid.UUID] | None) -> list[Task]:
    stmt = select(Task).where(Task.status == "active", Task.archived_at.is_(None))
    if task_ids:
        stmt = stmt.where(Task.id.in_(task_ids))
    else:
        stmt = stmt.where(((Task.planned_date.is_(None)) & (Task.origin == "inbox")) | (Task.planned_date == day))
    tasks = list(db.scalars(stmt))
    tasks.sort(key=lambda t: (t.deadline or date.max, _PRIORITY.get(t.priority, 9), t.created_at))
    return tasks[:25]


def daily_plan(db: Session, ctx: Ctx, provider: AIProvider, day: date, available_minutes: int,
               task_ids: list[uuid.UUID] | None) -> dict:
    tasks = _candidate_tasks(db, ctx, day, task_ids)
    if not tasks:
        raise invalid("ai_no_tasks", "There are no active tasks to plan from. Add or select some tasks first.")
    refs = {f"T{i + 1}": t for i, t in enumerate(tasks)}
    records = []
    for ref, t in refs.items():
        r = {"ref": ref, "title": _clip(t.title, 100), "priority": t.priority,
             "estimated_minutes": t.estimated_minutes}
        if t.deadline:
            r["deadline"] = t.deadline.isoformat()
            r["days_until_deadline"] = (t.deadline - day).days
        records.append(r)
    prompt = (
        f"Plan the day {day.isoformat()}. Available time: {available_minutes} minutes in total. "
        "Choose tasks from the list, in the order to do them, so that the sum of estimated_minutes stays "
        "within the available time. Prefer near deadlines and high priority. Give a short reason per task "
        "that refers only to its priority, deadline or estimate.\n"
        f"TASKS: {json.dumps(records, ensure_ascii=False)}"
    )
    schema = _obj({
        "selected": _arr(_obj({"ref": {"type": "string", "enum": list(refs)}, "reason": _str(200, 3)}), 1, len(refs)),
        "note": _str(300, 0),
    })

    def validate(ans: _Plan, last_attempt: bool) -> dict:
        chosen = [p.ref for p in ans.selected]
        _refs_ok(chosen, set(refs), "tasks")
        if len(set(chosen)) != len(chosen):
            raise ProposalRejected("it chose the same task twice")
        check_language(ans.note, *(p.reason for p in ans.selected))
        model_total = sum(refs[p.ref].estimated_minutes or 0 for p in ans.selected)
        if model_total > available_minutes and not last_attempt:
            raise ProposalRejected(
                f"the chosen tasks add up to {model_total} minutes, more than the {available_minutes} available")
        # Deterministic time-budget check: walk the model's order and keep what fits.
        plan, left_out, used, unestimated = [], [], 0, 0
        for p in ans.selected:
            t = refs[p.ref]
            est = t.estimated_minutes
            row = {"ref": p.ref, "task_id": t.id, "title": t.title, "priority": t.priority,
                   "deadline": t.deadline, "estimated_minutes": est, "reason": p.reason.strip(),
                   "planned_for": t.planned_date}
            if est is None:
                unestimated += 1
                plan.append(row)
            elif used + est <= available_minutes:
                used += est
                plan.append(row)
            else:
                left_out.append({**row, "why": f"Needs {est} min but only {available_minutes - used} min would be left."})
        not_selected = [{"ref": r, "task_id": t.id, "title": t.title} for r, t in refs.items() if r not in chosen]
        return {
            "date": day, "available_minutes": available_minutes, "plan": plan, "left_out": left_out,
            "not_selected": not_selected, "planned_minutes": used, "unestimated_count": unestimated,
            "model_respected_budget": model_total <= available_minutes,
            "note": ans.note.strip(),
            "supplied_records": [{"ref": r, "task_id": t.id, "title": t.title} for r, t in refs.items()],
        }

    return runner.run(provider, "daily_plan", prompt, schema, _Plan, validate, max_tokens=600)


# ---------------------------------------------------------------- 3. reasons summary

class _Point(BaseModel):
    text: str = Field(min_length=5, max_length=240)
    refs: list[str] = Field(default_factory=list, max_length=20)


class _Summary(BaseModel):
    observations: list[_Point] = Field(min_length=1, max_length=4)
    suggestions: list[_Point] = Field(min_length=1, max_length=4)


def _point_schema(enum: list[str], need_refs: bool) -> dict:
    return _obj({"text": _str(240, 5), "refs": _arr({"type": "string", "enum": enum}, 1 if need_refs else 0, 20)})


def reasons_summary(db: Session, ctx: Ctx, provider: AIProvider, start: date, end: date) -> dict:
    plans = list(db.scalars(
        select(TaskPlan).options(selectinload(TaskPlan.task))
        .where(TaskPlan.plan_date >= start, TaskPlan.plan_date <= min(end, ctx.today),
               TaskPlan.outcome.in_(task_service.UNFINISHED),
               (TaskPlan.reason.is_not(None)) | (TaskPlan.reason_note.is_not(None)))
        .order_by(TaskPlan.plan_date.desc()).limit(60)
    ))
    if not plans:
        raise invalid("ai_no_records", "No unfinished tasks with recorded reasons in this range, so there is nothing to summarise.")
    refs = {f"R{i + 1}": p for i, p in enumerate(plans)}
    counts: dict[str, int] = {}
    for p in plans:
        if p.reason:
            counts[REASON_LABELS[p.reason]] = counts.get(REASON_LABELS[p.reason], 0) + 1
    records = []
    for r, p in refs.items():
        rec = {"ref": r, "date": p.plan_date.isoformat(), "task": _clip(p.task.title, 80),
               "outcome": p.outcome.replace("_", " ")}
        if p.reason:
            rec["tag"] = REASON_LABELS[p.reason]
        if p.reason_note:
            rec["written_reason"] = _clip(p.reason_note, 160)
        records.append(rec)
    prompt = (
        "These are tasks you (the reader) marked as not completed, with the reason you wrote and an optional tag. "
        f"Tag counts, already calculated: {json.dumps(counts)}. "
        "Write up to 3 observations about what was recorded (for example: 'Not enough time was recorded for 3 of "
        "6 tasks'), each listing in refs the records it is based on. Use only numbers from the counts. "
        "Then write up to 3 small, practical planning adjustments that match the recorded reasons. "
        "Address the reader as 'you'. Describe the records, not the reader's abilities or feelings. "
        "Do not write refs inside the text.\n"
        f"RECORDS: {json.dumps(records, ensure_ascii=False)}"
    )
    schema = _obj({"observations": _arr(_point_schema(list(refs), True), 1, 4),
                   "suggestions": _arr(_point_schema(list(refs), False), 1, 4)})

    def validate(ans: _Summary, last_attempt: bool) -> dict:
        for o in ans.observations:
            if not o.refs:
                raise ProposalRejected("an observation did not cite any records")
            _refs_ok(o.refs, set(refs), "records")
        for s in ans.suggestions:
            _refs_ok(s.refs, set(refs), "records")
        check_language(*(p.text for p in ans.observations + ans.suggestions))
        allowed = {float(v) for v in counts.values()} | {float(len(refs))}
        allowed |= {float(len(set(o.refs))) for o in ans.observations}
        for o in ans.observations:
            check_numbers(o.text, allowed)
        names = {r: p.task.title for r, p in refs.items()}

        def support(ids: list[str]) -> list[dict]:
            return [{"ref": r, "date": refs[r].plan_date, "task_title": refs[r].task.title,
                     "reason": REASON_LABELS[refs[r].reason] if refs[r].reason else (refs[r].reason_note or ""),
                     "outcome": refs[r].outcome} for r in dict.fromkeys(ids)]

        return {
            "start": start, "end": end, "records_sent": len(refs), "counts": counts,
            "observations": [{"text": name_refs(tidy(o.text), names), "support": support(o.refs)} for o in ans.observations],
            "suggestions": [{"text": name_refs(tidy(s.text), names), "support": support(s.refs)} for s in ans.suggestions],
            "shared": {"fields": ["date", "task title", "outcome", "tag", "written reason (first 160 characters)"]},
        }

    return runner.run(provider, "reasons_summary", prompt, schema, _Summary, validate, max_tokens=700)


# ---------------------------------------------------------------- 4. habit review

class _HabitSuggestion(BaseModel):
    habit_ref: str = Field(max_length=6)
    text: str = Field(min_length=5, max_length=240)


class _HabitReview(BaseModel):
    observations: list[_Point] = Field(min_length=1, max_length=4)
    suggestions: list[_HabitSuggestion] = Field(min_length=1, max_length=4)


def habit_review(db: Session, ctx: Ctx, provider: AIProvider, start: date, end: date) -> dict:
    stats = habit_service.insights(db, ctx, start, end)
    habits = {h.id: h for h in habit_service._load(db)}
    rows = [r for r in stats["habits"] if r["habit_id"] in habits][:15]
    if not rows:
        raise invalid("ai_no_records", "No habits with data in this range yet.")
    refs = {f"H{i + 1}": r for i, r in enumerate(rows)}
    records = []
    for ref, r in refs.items():
        h = habits[r["habit_id"]]
        s = habit_service.schedule_for(h, min(end, ctx.today)) or (h.schedules[-1] if h.schedules else None)
        rec = {"ref": ref, "name": _clip(r["name"], 60), "kind": h.kind,
               "schedule": (s.schedule_type if s else None),
               "scheduled_days": r["scheduled_days"], "completed_days": r["completed_days"],
               "consistency_pct": r["consistency_pct"], "paused_days": r["paused_days"]}
        if s and s.schedule_type == "weekdays":
            rec["weekdays"] = s.weekdays
        if s and s.schedule_type == "weekly_target":
            rec["sessions_per_week_target"] = s.weekly_target
        if r["weekly"]:
            rec["weeks_target_met"] = f"{r['weekly']['weeks_met']} of {r['weekly']['weeks_evaluated']}"
        if s and h.kind != "boolean":
            rec["daily_target"] = s.target_value
        if r["scheduled_days"]:
            rec["summary"] = (f"done on {r['completed_days']} of {r['scheduled_days']} scheduled days "
                              f"({r['consistency_pct']}%)")
        elif r["weekly"] and r["weekly"]["weeks_evaluated"]:
            rec["summary"] = f"weekly target met in {r['weekly']['weeks_met']} of {r['weekly']['weeks_evaluated']} full weeks"
        else:
            rec["summary"] = "not enough finished days yet to judge"
        records.append(rec)
    prompt = (
        f"Habit consistency from {start.isoformat()} to {end.isoformat()}. The numbers are already calculated: "
        "copy them from 'summary', never compute new ones. Write up to 3 observations, each listing in refs the "
        "habits it is about. Then up to 3 achievable adjustments, each for one habit: when consistency is below "
        "60%, make it easier (fewer days, a smaller daily target, different weekdays, or a pause); when it is 80% "
        "or more, suggest keeping it as it is. Skip habits whose summary says there isn't enough data. "
        "Paused days are not failures. Address the reader as 'you'. Do not write refs inside the text.\n"
        f"HABITS: {json.dumps(records, ensure_ascii=False)}"
    )
    schema = _obj({
        "observations": _arr(_point_schema(list(refs), True), 1, 4),
        "suggestions": _arr(_obj({"habit_ref": {"type": "string", "enum": list(refs)}, "text": _str(240, 5)}), 1, 4),
    })

    def validate(ans: _HabitReview, last_attempt: bool) -> dict:
        for o in ans.observations:
            if not o.refs:
                raise ProposalRejected("an observation did not cite any habits")
            _refs_ok(o.refs, set(refs), "habits")
        _refs_ok([s.habit_ref for s in ans.suggestions], set(refs), "habits")
        check_language(*(o.text for o in ans.observations), *(s.text for s in ans.suggestions))
        for o in ans.observations:
            allowed: set[float] = set()
            for r in o.refs:
                row = refs[r]
                allowed |= {float(v) for v in (row["scheduled_days"], row["completed_days"], row["consistency_pct"],
                                               row["paused_days"], row["missed_days"]) if v is not None}
                if row["weekly"]:
                    allowed |= {float(v) for v in row["weekly"].values()}
            check_numbers(o.text, allowed)

        # Achievable changes only: never "do more" of a habit that is below 60% consistency.
        suggestions, seen = [], set()
        for sug in ans.suggestions:
            pct = refs[sug.habit_ref]["consistency_pct"]
            if pct is not None and pct < 60 and asks_for_more(sug.text):
                if not last_attempt:
                    raise ProposalRejected(
                        f"it suggested doing more of {sug.habit_ref}, which is at {pct}% consistency; suggest making it easier")
                continue  # last attempt: drop just this suggestion
            key = (sug.habit_ref, sug.text.strip().lower())
            if key not in seen:
                seen.add(key)
                suggestions.append(sug)
        names = {r: row["name"] for r, row in refs.items()}

        def support(ids: list[str]) -> list[dict]:
            return [{"ref": r, "habit_id": refs[r]["habit_id"], "name": refs[r]["name"],
                     "scheduled_days": refs[r]["scheduled_days"], "completed_days": refs[r]["completed_days"],
                     "consistency_pct": refs[r]["consistency_pct"]} for r in dict.fromkeys(ids)]

        return {
            "start": start, "end": end, "records_sent": len(refs),
            "observations": [{"text": name_refs(tidy(o.text), names), "support": support(o.refs)} for o in ans.observations],
            "suggestions": [{"text": name_refs(tidy(s.text), names), "support": support([s.habit_ref])} for s in suggestions],
            "shared": {"fields": ["habit name", "schedule", "calculated consistency numbers"]},
        }

    return runner.run(provider, "habit_review", prompt, schema, _HabitReview, validate, max_tokens=700)


# ---------------------------------------------------------------- 5. journal

class _Prompts(BaseModel):
    prompts: list[str] = Field(min_length=3, max_length=3)


def journal_prompts(provider: AIProvider, focus: str | None) -> dict:
    """Sends no journal content at all: only the optional focus the user picked."""
    topics = {"day": "reflecting on the day", "week": "looking back on the week",
              "tomorrow": "preparing for tomorrow", None: "general reflection"}
    prompt = (f"Write 3 short, open, gentle journal prompts for {topics.get(focus, topics[None])}. "
              "Each is one question under 140 characters, with no numbering or labels. No clinical or therapy language.")
    schema = _obj({"prompts": _arr(_str(160, 10), 3, 3)})

    def validate(ans: _Prompts, last_attempt: bool) -> dict:
        prompts = [tidy(p) for p in ans.prompts]
        if len({p.lower() for p in prompts}) != 3:
            raise ProposalRejected("it repeated a prompt")
        check_language(*prompts)
        return {"prompts": prompts, "shared": {"fields": [], "journal_content_sent": False}}

    return runner.run(provider, "journal_prompts", prompt, schema, _Prompts, validate, max_tokens=250)


JOURNAL_FIELDS = (("body", "Free writing"), ("went_well", "What went well?"),
                  ("was_difficult", "What was difficult?"), ("on_mind", "What is on your mind?"))
JOURNAL_CHAR_LIMIT = 4000


def journal_share_preview(db: Session, dates: list[date]) -> dict:
    """Exactly what a summary request would send, so the user can decide first."""
    items = []
    for d in dates:
        e = journal_service.get_entry(db, d)
        if e is None:
            items.append({"date": d, "exists": False, "characters": 0, "truncated": False})
            continue
        text_len = sum(len(getattr(e, f)) for f, _ in JOURNAL_FIELDS)
        items.append({"date": d, "exists": True, "characters": min(text_len, JOURNAL_CHAR_LIMIT),
                      "truncated": text_len > JOURNAL_CHAR_LIMIT,
                      "mood": e.mood, "energy": e.energy})
    return {"entries": items,
            "fields_sent": ["free writing", "reflection answers", "mood (1-5)", "energy (1-5)"],
            "not_sent": ["any other day", "tasks", "habits", "settings"],
            "destination": destination()}


class _Theme(BaseModel):
    text: str = Field(min_length=5, max_length=200)
    dates: list[str] = Field(min_length=1, max_length=14)


class _JournalSummary(BaseModel):
    summary: str = Field(min_length=10, max_length=700)
    themes: list[_Theme] = Field(default_factory=list, max_length=4)


def journal_summary(db: Session, provider: AIProvider, dates: list[date]) -> dict:
    entries = [e for d in dates if (e := journal_service.get_entry(db, d)) is not None]
    if not entries:
        raise invalid("ai_no_records", "None of the selected days have a journal entry.")
    keys = [e.entry_date.isoformat() for e in entries]
    records = []
    for e in entries:
        rec: dict = {"date": e.entry_date.isoformat()}
        budget = JOURNAL_CHAR_LIMIT
        for field, label in JOURNAL_FIELDS:
            value = getattr(e, field).strip()
            if value and budget > 0:
                rec[label] = value[:budget]
                budget -= len(rec[label])
        if e.mood:
            rec["mood_1_to_5"] = e.mood
        if e.energy:
            rec["energy_1_to_5"] = e.energy
        records.append(rec)
    prompt = (
        "Summarise these journal entries the person chose to share, in a warm, neutral second-person voice "
        "('you wrote about…'). Then list up to 3 recurring themes, each with the dates it appears on. "
        "Describe only what is written. No advice unless the entries ask for it, no diagnosis, no guessing at causes.\n"
        f"ENTRIES: {json.dumps(records, ensure_ascii=False)}"
    )
    schema = _obj({"summary": _str(700, 10),
                   "themes": _arr(_obj({"text": _str(200, 5), "dates": _arr({"type": "string", "enum": keys}, 1, len(keys))}), 0, 4)})

    def validate(ans: _JournalSummary, last_attempt: bool) -> dict:
        for t in ans.themes:
            _refs_ok(t.dates, set(keys), "dates")
        check_language(ans.summary, *(t.text for t in ans.themes))
        return {"dates": keys, "summary": tidy(ans.summary),
                "themes": [{"text": tidy(t.text), "dates": sorted(set(t.dates))} for t in ans.themes]}

    return runner.run(provider, "journal_summary", prompt, schema, _JournalSummary, validate, max_tokens=600)


# ---------------------------------------------------------------- 6. money review

class _Trend(BaseModel):
    text: str = Field(min_length=5, max_length=240)
    refs: list[str] = Field(default_factory=list, max_length=20)


class _CutBack(BaseModel):
    category_ref: str = Field(max_length=6)
    reduce_pct: int
    text: str = Field(min_length=5, max_length=240)


class _MoneyReview(BaseModel):
    trends: list[_Trend] = Field(min_length=1, max_length=4)
    cut_back: list[_CutBack] = Field(min_length=1, max_length=3)
    save_tips: list[_Trend] = Field(min_length=1, max_length=4)


CUT_PCTS = [10, 15, 20, 25, 30, 50]
# Spending habits only: no investing, borrowing or tax advice.
_OFF_LIMITS = re.compile(r"\b(invest\w*|stocks?|shares|crypto\w*|bitcoin|trading|loans?|borrow\w*|mortgage|tax\w*|"
                         r"insurance polic\w*|retirement fund)\b", re.IGNORECASE)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_PCT_IN_TEXT = re.compile(r"\b\d+(?:\.\d+)?\s?%")
_JUST_A_PERCENT = re.compile(r"^\s*(consider\s+)?(reduc|cut|lower|decreas|trim)\w*\b.*\bby\s+\d+(?:\.\d+)?\s?%\s*\.?\s*$",
                             re.IGNORECASE)
# Essentials: never suggest cutting these by more than 10% (enforced, whatever the model says).
_ESSENTIAL = re.compile(r"\b(rent|housing|mortgage|health\w*|medical|medicine|pharmacy|doctor|child ?care|insurance)\b",
                        re.IGNORECASE)


def _amt(cents: int | None) -> float | None:
    return None if cents is None else round(cents / 100, 2)


def money_review(db: Session, ctx: Ctx, provider: AIProvider) -> dict:
    t = finance_service.trends(db, ctx)
    if t["expense_entries"] < 3:
        raise invalid("ai_no_records", "Record a few days of spending first, so there is something to review.")
    months = [m for m in t["months"] if m["tracked"]]
    mrefs = {f"M{i + 1}": m for i, m in enumerate(months)}
    crefs = {f"C{i + 1}": c for i, c in enumerate(t["categories"][:12])}
    brefs = {f"B{i + 1}": b for i, b in enumerate(t["repeating_bills"][:10])}
    month_recs = [{"ref": r, "month": m["month"],
                   "status": "complete" if m["complete"] else f"this month so far ({m['days']} of {m['days_in_month']} days)",
                   "spent": _amt(m["spent_cents"]), "money_in": _amt(m["income_cents"]), "saved": _amt(m["saved_cents"]),
                   "savings_rate_pct": m["savings_rate_pct"]} for r, m in mrefs.items()]
    day_n = t["day_of_month"]
    cat_recs = [{"ref": r, "category": c["name"], "average_per_full_month": _amt(c["avg_monthly_cents"]),
                 "this_month_so_far": _amt(c["this_month_cents"]),
                 f"usually_by_day_{day_n}": _amt(c["usual_by_today_cents"]),
                 "change_vs_usual_pct": c["change_pct"]} for r, c in crefs.items()]
    bill_recs = [{"ref": r, "name": _clip(b["name"], 40), "per_month": _amt(b["monthly_cents"])} for r, b in brefs.items()]
    extra = {"repeating_bills_per_month": _amt(t["repeating_monthly_cents"]),
             "average_spent_per_full_month": _amt(t["avg_monthly_spent_cents"]),
             "average_money_in_per_full_month": _amt(t["avg_monthly_income_cents"]),
             "spent_this_month_so_far": _amt(t["this_month_cents"]),
             f"usually_spent_by_day_{day_n}": _amt(t["usual_by_today_cents"]),
             "splitwise_you_should_pay": _amt(t["splitwise"]["pay_cents"]),
             "splitwise_you_should_get": _amt(t["splitwise"]["get_cents"])}
    prompt = (
        "These are the reader's spending figures, already calculated by the app (amounts in their currency). "
        "Write up to 3 TRENDS: what the figures show (for example which categories are biggest, rising or falling, "
        f"and how much was saved; this month is compared with what was usually spent by day {day_n}, since a "
        "month in progress can't be compared with whole months), each listing in refs the months, categories or bills it is based on. Copy numbers "
        "exactly as given; never calculate new ones. "
        "Then pick up to 3 categories to CUT BACK, the ones where spending is largest or rising, and choose how much "
        f"to reduce each (reduce_pct, one of {CUT_PCTS}). Its text is ONE concrete action, such as 'Cook at home on "
        "weeknights' or 'Cancel streaming services you rarely use', not 'reduce X by N%'. Don't write amounts or "
        "percentages in cut_back text: the app calculates the saving. Never suggest cutting essentials like rent or health care "
        "by more than 10%. "
        "Then give up to 3 practical SAVING TIPS based on these figures (for example reviewing repeating bills, "
        "setting a weekly limit for a category, or moving money aside when salary arrives). "
        "Stick to everyday spending habits: no investing, borrowing, insurance or tax advice. "
        "Address the reader as 'you'. Be kind and specific; don't judge. Do not write refs inside the text.\n"
        f"MONTHS: {json.dumps(month_recs)}\nCATEGORIES: {json.dumps(cat_recs, ensure_ascii=False)}\n"
        f"REPEATING BILLS: {json.dumps(bill_recs, ensure_ascii=False)}\nTOTALS: {json.dumps(extra)}"
    )
    all_refs = list(mrefs) + list(crefs) + list(brefs)
    schema = _obj({
        "trends": _arr(_point_schema(all_refs, True), 1, 4),
        "cut_back": _arr(_obj({"category_ref": {"type": "string", "enum": list(crefs)},
                               "reduce_pct": {"type": "integer", "enum": CUT_PCTS}, "text": _str(240, 5)}), 1, 3),
        "save_tips": _arr(_point_schema(all_refs, False), 1, 4),
    })

    # Every number the model may state: the figures sent, plus rounded forms of the amounts.
    # Small counts ("2 categories", "3 months") are fine; amounts must come from the figures.
    allowed: set[float] = set(map(float, CUT_PCTS)) | {float(n) for n in range(13)}
    for rec in [*month_recs, *cat_recs, *bill_recs, extra]:
        for v in rec.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                allowed |= {float(v), float(round(v)), float(round(v, 1))}
    for m in months:
        allowed |= {float(m["days"]), float(m["days_in_month"])}
    allowed |= {float(m["month"][:4]) for m in months} | {float(int(m["month"][5:])) for m in months} | {float(day_n)}

    def numbers_ok(text: str) -> None:
        check_numbers(_THOUSANDS.sub("", text), allowed)

    def validate(ans: _MoneyReview, last_attempt: bool) -> dict:
        for tr in ans.trends:
            if not tr.refs:
                raise ProposalRejected("a trend did not cite any figures")
            _refs_ok(tr.refs, set(all_refs), "figures")
        for tip in ans.save_tips:
            _refs_ok(tip.refs, set(all_refs), "figures")
        _refs_ok([c.category_ref for c in ans.cut_back], set(crefs), "categories")
        texts = [x.text for x in ans.trends + ans.save_tips] + [c.text for c in ans.cut_back]
        check_language(*texts)
        for text in texts:
            if _OFF_LIMITS.search(text):
                raise ProposalRejected("it gave investing, borrowing, insurance or tax advice; stick to spending habits")
            numbers_ok(text)
        cut, seen = [], set()
        for c in ans.cut_back:
            if c.reduce_pct not in CUT_PCTS:
                raise ProposalRejected(f"reduce_pct must be one of {CUT_PCTS}")
            if c.category_ref in seen:
                continue
            seen.add(c.category_ref)
            if _JUST_A_PERCENT.match(c.text) and not last_attempt:
                raise ProposalRejected("a cut_back text only repeated the percentage; give one concrete action instead")
            cat = crefs[c.category_ref]
            pct = min(c.reduce_pct, 10) if _ESSENTIAL.search(cat["name"]) else c.reduce_pct
            base = cat["avg_monthly_cents"] if cat["avg_monthly_cents"] is not None else cat["this_month_cents"]
            monthly = base * pct // 100
            cut.append({"category_id": cat["category_id"], "category": cat["name"], "reduce_pct": pct,
                        # the text's percentage matches the (possibly capped) figure
                        "text": _PCT_IN_TEXT.sub(f"{pct}%", tidy(c.text)), "based_on_cents": base,
                        "based_on": "average per month" if cat["avg_monthly_cents"] is not None else "this month so far",
                        "saving_monthly_cents": monthly, "saving_yearly_cents": monthly * 12})
        names = {**{r: m["month"] for r, m in mrefs.items()}, **{r: c["name"] for r, c in crefs.items()},
                 **{r: b["name"] for r, b in brefs.items()}}

        def support(ids: list[str]) -> list[dict]:
            out = []
            for r in dict.fromkeys(ids):
                if r in mrefs:
                    m = mrefs[r]
                    out.append({"ref": r, "kind": "month", "label": m["month"], "spent_cents": m["spent_cents"],
                                "income_cents": m["income_cents"], "complete": m["complete"]})
                elif r in crefs:
                    c = crefs[r]
                    out.append({"ref": r, "kind": "category", "label": c["name"], "avg_monthly_cents": c["avg_monthly_cents"],
                                "this_month_cents": c["this_month_cents"], "change_pct": c["change_pct"]})
                else:
                    b = brefs[r]
                    out.append({"ref": r, "kind": "bill", "label": b["name"], "monthly_cents": b["monthly_cents"]})
            return out

        return {
            "records_sent": len(all_refs),
            "trends": [{"text": name_refs(tidy(x.text), names), "support": support(x.refs)} for x in ans.trends],
            "cut_back": cut,
            "save_tips": [{"text": name_refs(tidy(x.text), names), "support": support(x.refs)} for x in ans.save_tips],
            "possible_saving_monthly_cents": sum(c["saving_monthly_cents"] for c in cut),
            "shared": {"fields": ["monthly totals", "category totals", "repeating bill names and amounts",
                                  "Splitwise totals"], "not_shared": ["entry notes", "account names", "balances"]},
        }

    return runner.run(provider, "money_review", prompt, schema, _MoneyReview, validate, max_tokens=900)
