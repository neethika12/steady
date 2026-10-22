"""AI proposal validation, grounding, privacy and failure handling (with labelled fixtures)."""

import logging

import httpx
import pytest

from app.ai import runner
from app.ai.ollama import OllamaProvider
from app.ai.provider import AIBadOutput, AIUnavailable
from app.main import app
from tests.conftest import ok
from tests.fixtures.ai_fixtures import BAD_JSON, FixtureProvider


@pytest.fixture
def ai(client):
    provider = FixtureProvider()
    app.dependency_overrides[runner.get_provider] = lambda: provider
    runner.limiter.calls.clear()
    yield provider
    app.dependency_overrides.pop(runner.get_provider, None)


def task(client, title, **extra):
    return ok(client.post("/api/tasks", json={"title": title, **extra}), 201)


# ---- availability ----

def test_unavailable_ai_returns_clear_503_and_core_features_still_work(client, ai):
    ai.available = False
    s = ok(client.get("/api/ai/status"))
    assert s["available"] is False and s["setup"]
    t = task(client, "Write report")
    r = client.post("/api/ai/breakdown", json={"task_id": t["id"]})
    assert r.status_code == 503
    assert r.json()["detail"]["message"].startswith("AI unavailable")
    ok(client.post("/api/tasks", json={"title": "still works"}), 201)  # non-AI features unaffected


def test_real_adapter_reports_unreachable_server():
    p = OllamaProvider("http://127.0.0.1:9", "phi4-mini", timeout_seconds=2)
    assert p.status()["reason"] == "server_unreachable"
    with pytest.raises(AIUnavailable):
        p.generate_json(system="s", prompt="p", schema={}, max_tokens=10)


def test_real_adapter_rejects_truncated_and_non_json_answers(monkeypatch):
    p = OllamaProvider("http://ollama.test", "phi4-mini", timeout_seconds=2)
    req = httpx.Request("POST", "http://ollama.test/api/chat")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, request=req, json={"done_reason": "length", "message": {"content": "{"}}))
    with pytest.raises(AIBadOutput):
        p.generate_json(system="s", prompt="p", schema={}, max_tokens=10)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, request=req, json={"done_reason": "stop", "message": {"content": "not json"}}))
    with pytest.raises(AIBadOutput):
        p.generate_json(system="s", prompt="p", schema={}, max_tokens=10)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(404, request=req, json={}))
    with pytest.raises(AIUnavailable) as e:
        p.generate_json(system="s", prompt="p", schema={}, max_tokens=10)
    assert e.value.reason == "model_missing"


# ---- breakdown ----

def test_breakdown_is_a_proposal_and_writes_nothing(client, ai):
    t = task(client, "Write quarterly report", estimated_minutes=60, description="For the finance team")
    ai.replies = [{"steps": [{"title": "Collect the numbers", "estimated_minutes": 30},
                             {"title": "Draft the summary", "estimated_minutes": 45}]}]
    r = ok(client.post("/api/ai/breakdown", json={"task_id": t["id"]}))
    assert [s["title"] for s in r["steps"]] == ["Collect the numbers", "Draft the summary"]
    assert r["total_minutes"] == 75 and r["exceeds_original_estimate"] is True
    assert "Write quarterly report" in ai.prompts[0]
    assert len(ok(client.get("/api/tasks?view=all_active"))) == 1  # nothing created


def test_malformed_answer_is_retried_then_rejected(client, ai):
    t = task(client, "Plan trip")
    ai.replies = [BAD_JSON, {"steps": [{"title": "x", "estimated_minutes": 1}]}]  # both invalid
    r = client.post("/api/ai/breakdown", json={"task_id": t["id"]})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "ai_invalid"
    assert len(ai.prompts) == 2  # one retry, then stop (bounded)
    assert "rejected because" in ai.prompts[1]


def test_retry_can_recover(client, ai):
    t = task(client, "Plan trip")
    ai.replies = [BAD_JSON, {"steps": [{"title": "Pick dates", "estimated_minutes": 10},
                                       {"title": "Book train", "estimated_minutes": 20}]}]
    assert len(ok(client.post("/api/ai/breakdown", json={"task_id": t["id"]}))["steps"]) == 2


# ---- daily plan ----

def test_daily_plan_rejects_unknown_records(client, ai):
    task(client, "A", estimated_minutes=30)
    ai.replies = [{"selected": [{"ref": "T9", "reason": "made up"}], "note": ""}] * 2
    r = client.post("/api/ai/daily-plan", json={"date": "2026-03-02", "available_minutes": 60})
    assert r.status_code == 502


def test_daily_plan_time_budget_is_enforced_by_the_app(client, ai):
    a = task(client, "Deep work", estimated_minutes=90, priority="high")
    b = task(client, "Email", estimated_minutes=30)
    c = task(client, "Call bank", estimated_minutes=20)
    task(client, "Something else", estimated_minutes=10)
    over_budget = {"selected": [{"ref": "T1", "reason": "high priority"}, {"ref": "T2", "reason": "quick"},
                                {"ref": "T3", "reason": "quick"}], "note": ""}
    ai.replies = [over_budget, over_budget]  # first attempt is sent back with feedback; the retry is trimmed
    r = ok(client.post("/api/ai/daily-plan", json={"date": "2026-03-02", "available_minutes": 120,
                                                    "task_ids": [a["id"], b["id"], c["id"]]}))
    assert [p["title"] for p in r["plan"]] == ["Deep work", "Email"]
    assert r["planned_minutes"] == 120 and r["model_respected_budget"] is False
    assert [x["title"] for x in r["left_out"]] == ["Call bank"]
    assert "Something else" not in ai.prompts[0]  # only the selected tasks were sent
    assert "140 minutes, more than the 120 available" in ai.prompts[1]
    # Nothing is scheduled until the user accepts:
    assert ok(client.get("/api/plans/day?date=2026-03-02"))["plans"] == []
    ok(client.post("/api/plans/batch", json={"date": "2026-03-02", "task_ids": [p["task_id"] for p in r["plan"]]}))
    assert len(ok(client.get("/api/plans/day?date=2026-03-02"))["plans"]) == 2


# ---- reasons summary ----

def _unfinished(client, title, reason, note="Ran out of time"):
    task(client, title, planned_date="2026-03-02")
    plan = next(p for p in ok(client.get("/api/plans/day?date=2026-03-02"))["plans"] if p["task"]["title"] == title)
    ok(client.put(f"/api/plans/{plan['id']}/review", json={"outcome": "not_completed", "reason": reason, "reason_note": note}))


def test_reasons_summary_is_grounded_and_sends_only_clipped_written_reasons(client, ai):
    _unfinished(client, "Tax return", "not_enough_time", note="Family visit took the evening. " + "x" * 300)
    _unfinished(client, "Gym booking", None, note="Too tired after work")
    ai.replies = [{"observations": [{"text": "One task ran out of time.", "refs": ["R2"]}],
                   "suggestions": [{"text": "Plan a shorter first step.", "refs": []}]}]
    r = ok(client.post("/api/ai/reasons-summary", json={"start": "2026-03-01", "end": "2026-03-07"}))
    assert r["records_sent"] == 2
    support = r["observations"][0]["support"]
    assert support[0]["date"] == "2026-03-02" and support[0]["ref"] == "R2"
    assert "Too tired after work" in ai.prompts[0]  # written reasons are the main evidence now
    assert "x" * 200 not in ai.prompts[0]  # ...but clipped to 160 characters


def test_observations_without_evidence_or_with_diagnoses_are_rejected(client, ai):
    _unfinished(client, "Tax return", "not_enough_time")
    ai.replies = [
        {"observations": [{"text": "You may have ADHD.", "refs": ["R1"]}], "suggestions": [{"text": "Rest more.", "refs": []}]},
        {"observations": [{"text": "Things were late.", "refs": []}], "suggestions": [{"text": "Rest more.", "refs": []}]},
    ]
    r = client.post("/api/ai/reasons-summary", json={"start": "2026-03-01", "end": "2026-03-07"})
    assert r.status_code == 502


def test_no_records_means_no_ai_call(client, ai):
    r = client.post("/api/ai/reasons-summary", json={"start": "2026-03-01", "end": "2026-03-07"})
    assert r.status_code == 422 and ai.prompts == []


# ---- habits ----

def test_habit_review_uses_calculated_numbers(client, ai, clock):
    h = ok(client.post("/api/habits", json={"name": "Read", "start_date": "2026-02-23",
                                             "schedule": {"schedule_type": "daily"}}), 201)
    ok(client.put(f"/api/habits/{h['id']}/checkins/2026-02-24", json={"value": 1}))
    ai.replies = [{"observations": [{"text": "Reading happened on one scheduled day.", "refs": ["H1"]}],
                   "suggestions": [{"habit_ref": "H1", "text": "Try three set weekdays."}]}]
    r = ok(client.post("/api/ai/habit-review", json={"start": "2026-02-23", "end": "2026-03-01"}))
    s = r["suggestions"][0]["support"][0]
    assert s["habit_id"] == h["id"] and s["scheduled_days"] == 7 and s["completed_days"] == 1
    assert '"consistency_pct": 14' in ai.prompts[0]


# ---- journal ----

def test_journal_prompts_send_no_journal_content(client, ai):
    ok(client.put("/api/journal/2026-03-01", json={"base_version": 0, "body": "secret words"}))
    ai.replies = [{"prompts": ["What felt light today?", "What do you want to remember?", "What can wait?"]}]
    r = ok(client.post("/api/ai/journal-prompts", json={"focus": "day"}))
    assert len(r["prompts"]) == 3 and r["shared"]["journal_content_sent"] is False
    assert "secret" not in ai.prompts[0]


def test_journal_summary_needs_confirmation_and_sends_only_selected_days(client, ai):
    ok(client.put("/api/journal/2026-03-01", json={"base_version": 0, "body": "Walked by the river."}))
    ok(client.put("/api/journal/2026-02-27", json={"base_version": 0, "body": "Unselected private day."}))
    preview = ok(client.get("/api/ai/journal-summary/preview?dates=2026-03-01&dates=2026-02-28"))
    assert [e["exists"] for e in preview["entries"]] == [False, True]
    r = client.post("/api/ai/journal-summary", json={"dates": ["2026-03-01"], "confirm_share": False})
    assert r.status_code == 422 and ai.prompts == []
    ai.replies = [{"summary": "You wrote about a walk by the river.",
                   "themes": [{"text": "Time outdoors", "dates": ["2026-03-01"]}]}]
    r = ok(client.post("/api/ai/journal-summary", json={"dates": ["2026-03-01"], "confirm_share": True}))
    assert r["themes"][0]["dates"] == ["2026-03-01"]
    assert "river" in ai.prompts[0] and "Unselected" not in ai.prompts[0]


def test_journal_summary_rejects_dates_not_supplied(client, ai):
    ok(client.put("/api/journal/2026-03-01", json={"base_version": 0, "body": "Hello"}))
    bad = {"summary": "A day of greetings.", "themes": [{"text": "Greetings", "dates": ["2026-02-01"]}]}
    ai.replies = [bad, bad]
    r = client.post("/api/ai/journal-summary", json={"dates": ["2026-03-01"], "confirm_share": True})
    assert r.status_code == 502


# ---- spending / safety limits ----

def test_rate_limit(client, ai, monkeypatch):
    monkeypatch.setattr(runner.limiter, "per_minute", 2)
    t = task(client, "Plan trip")
    good = {"steps": [{"title": "Pick dates", "estimated_minutes": 10}, {"title": "Book train", "estimated_minutes": 20}]}
    ai.replies = [good, good, good]
    body = {"task_id": t["id"]}
    ok(client.post("/api/ai/breakdown", json=body))
    ok(client.post("/api/ai/breakdown", json=body))
    r = client.post("/api/ai/breakdown", json=body)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "ai_rate_limited"


def test_logs_contain_no_personal_content(client, ai, caplog):
    t = task(client, "Confidential salary talk")
    ai.replies = [{"steps": [{"title": "Note talking points", "estimated_minutes": 15},
                             {"title": "Book a meeting", "estimated_minutes": 5}]}]
    with caplog.at_level(logging.INFO, logger="steady.ai"):
        ok(client.post("/api/ai/breakdown", json={"task_id": t["id"]}))
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "feature=breakdown" in logged
    assert "Confidential" not in logged and "talking points" not in logged


def test_daily_plan_within_budget_is_accepted_first_time(client, ai):
    a = task(client, "Email", estimated_minutes=30)
    ai.replies = [{"selected": [{"ref": "T1", "reason": "quick"}], "note": ""}]
    r = ok(client.post("/api/ai/daily-plan", json={"date": "2026-03-02", "available_minutes": 60, "task_ids": [a["id"]]}))
    assert r["model_respected_budget"] is True and len(ai.prompts) == 1


def test_numbers_must_come_from_supplied_data(client, ai, clock):
    h = ok(client.post("/api/habits", json={"name": "Stretch", "start_date": "2026-03-02",
                                             "schedule": {"schedule_type": "daily"}}), 201)
    clock.set("2026-03-04T12:00:00Z")
    ok(client.put(f"/api/habits/{h['id']}/checkins/2026-03-02", json={"value": 1}))
    invented = {"observations": [{"text": "Done once in 7 days.", "refs": ["H1"]}],
                "suggestions": [{"habit_ref": "H1", "text": "Try fewer days."}]}
    grounded = {"observations": [{"text": "H1: Done on 1 of 2 scheduled days (refs: H1).", "refs": ["H1"]}],
                "suggestions": [{"habit_ref": "H1", "text": "Try fewer days."}]}
    ai.replies = [invented, grounded]
    r = ok(client.post("/api/ai/habit-review", json={"start": "2026-03-02", "end": "2026-03-04"}))
    assert "the number 7" in ai.prompts[1]
    assert r["observations"][0]["text"] == "Done on 1 of 2 scheduled days."  # labels tidied


def test_journal_prompt_labels_are_removed(client, ai):
    ai.replies = [{"prompts": ["T1: What felt light today?", "R2: What can wait?", "3. What do you want to keep?"]}]
    r = ok(client.post("/api/ai/journal-prompts", json={}))
    assert r["prompts"] == ["What felt light today?", "What can wait?", "What do you want to keep?"]


def test_low_consistency_habits_get_easier_not_harder_suggestions(client, ai, clock):
    h = ok(client.post("/api/habits", json={"name": "Walk", "start_date": "2026-03-02",
                                             "schedule": {"schedule_type": "daily"}}), 201)
    clock.set("2026-03-06T12:00:00Z")
    ok(client.put(f"/api/habits/{h['id']}/checkins/2026-03-02", json={"value": 1}))  # 1 of 4 = 25%
    harder = {"observations": [{"text": "H1 was done on 1 of 4 days.", "refs": ["H1"]}],
              "suggestions": [{"habit_ref": "H1", "text": "Increase the frequency."},
                              {"habit_ref": "H1", "text": "Try three set weekdays instead."}]}
    ai.replies = [harder, harder]
    r = ok(client.post("/api/ai/habit-review", json={"start": "2026-03-02", "end": "2026-03-06"}))
    assert "making it easier" in ai.prompts[1]
    assert [x["text"] for x in r["suggestions"]] == ["Try three set weekdays instead."]
    assert r["observations"][0]["text"] == "“Walk” was done on 1 of 4 days."


# ---- money ----

def test_money_review_is_grounded_and_sends_totals_only(client, ai, clock):
    from tests.test_finance import three_months_of_spending
    three_months_of_spending(client, clock)
    ai.replies = [{
        "trends": [{"text": "Groceries averaged 120 a month; by day 10 you have spent 50, against 100 usually.", "refs": ["C1"]}],
        "cut_back": [{"category_ref": "C1", "reduce_pct": 20, "text": "Plan the week's meals before you shop."}],
        "save_tips": [{"text": "Move part of your salary aside on the day it arrives.", "refs": []}],
    }]
    r = ok(client.post("/api/ai/money-review"))
    cut = r["cut_back"][0]
    assert (cut["category"], cut["reduce_pct"], cut["based_on_cents"]) == ("Groceries", 20, 12_000)
    assert (cut["saving_monthly_cents"], cut["saving_yearly_cents"]) == (2_400, 28_800)  # the app does the maths
    assert r["trends"][0]["support"][0]["label"] == "Groceries"
    prompt = ai.prompts[0]
    assert "secret note" not in prompt and "Everyday debit" not in prompt  # no notes, no account names
    assert '"average_per_full_month": 120.0' in prompt


def test_money_review_rejects_invented_numbers_and_investment_advice(client, ai, clock):
    from tests.test_finance import three_months_of_spending
    three_months_of_spending(client, clock)
    base = {"cut_back": [{"category_ref": "C1", "reduce_pct": 10, "text": "Shop with a list."}],
            "save_tips": [{"text": "Review your bills.", "refs": []}]}
    ai.replies = [
        {**base, "trends": [{"text": "Groceries cost 999 a month.", "refs": ["C1"]}]},
        {**base, "trends": [{"text": "Groceries are your biggest category.", "refs": ["C1"]}],
         "save_tips": [{"text": "Invest what you save in stocks.", "refs": []}]},
    ]
    r = client.post("/api/ai/money-review")
    assert r.status_code == 502 and len(ai.prompts) == 2
    assert "999" in ai.prompts[1] or "number" in ai.prompts[1]  # the retry was told why


def test_money_review_needs_some_spending_first(client, ai):
    assert client.post("/api/ai/money-review").status_code == 422
    assert ai.prompts == []


def test_money_review_caps_cuts_to_essentials(client, ai, clock):
    from tests.test_finance import three_months_of_spending
    food, _ = three_months_of_spending(client, clock)
    ok(client.patch(f"/api/finance/categories/{food['id']}", json={"name": "Health"}))
    ai.replies = [{"trends": [{"text": "Health is your biggest category over 2 months.", "refs": ["C1"]}],
                   "cut_back": [{"category_ref": "C1", "reduce_pct": 50, "text": "Compare prices to spend 50% less."}],
                   "save_tips": [{"text": "Review your bills.", "refs": []}]}]
    cut = ok(client.post("/api/ai/money-review"))["cut_back"][0]
    assert (cut["category"], cut["reduce_pct"], cut["saving_monthly_cents"]) == ("Health", 10, 1_200)
    assert cut["text"] == "Compare prices to spend 10% less."  # the text matches the capped figure


# ---- hosted AI (Groq) and the per-person daily limit ----

PROMPTS = {"prompts": ["What felt light today?", "What do you want to remember?", "What can wait?"]}


def test_daily_ai_limit_is_per_person_and_counts_only_real_requests(client, ai, monkeypatch):
    import dataclasses

    from app.routers import ai as ai_router
    from tests.conftest import new_client
    cfg = dataclasses.replace(ai_router.get_config(), ai_daily_limit_per_user=2)
    monkeypatch.setattr(ai_router, "get_config", lambda: cfg)
    # Nothing to summarise: the model isn't asked, so it doesn't count.
    assert client.post("/api/ai/reasons-summary", json={"start": "2026-03-01", "end": "2026-03-02"}).status_code == 422
    ai.replies = [PROMPTS, PROMPTS]
    ok(client.post("/api/ai/journal-prompts", json={"focus": "day"}))
    ok(client.post("/api/ai/journal-prompts", json={"focus": "day"}))
    s = ok(client.get("/api/ai/status"))
    assert (s["daily_limit"], s["used_today"]) == (2, 2)
    r = client.post("/api/ai/journal-prompts", json={"focus": "day"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "ai_daily_limit"
    assert len(ai.prompts) == 2  # the third was refused before reaching the model
    with new_client("someone@example.com", "someone else's pw") as other:  # their own allowance
        ai.replies = [PROMPTS]
        ok(other.post("/api/ai/journal-prompts", json={"focus": "day"}))


class _Reply:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_groq_adapter_sends_a_strict_schema_and_reads_the_answer(monkeypatch):
    import json as _json

    from app.ai import groq
    from app.ai.provider import AIBadOutput, AIUnavailable
    sent = {}

    def post(url, json, headers, timeout):
        sent.update(url=url, body=json, headers=headers)
        return _Reply(200, {"choices": [{"finish_reason": "stop", "message": {"content": _json.dumps(PROMPTS)}}]})

    monkeypatch.setattr(groq.httpx, "post", post)
    p = groq.GroqProvider("test-key", "openai/gpt-oss-20b", 30)
    schema = {"type": "object", "properties": {"prompts": {"type": "array", "minItems": 3, "maxItems": 3,
                                                           "items": {"type": "string", "minLength": 5}}},
              "required": ["prompts"], "additionalProperties": False}
    assert p.generate_json(system="s", prompt="p", schema=schema, max_tokens=200) == PROMPTS
    fmt = sent["body"]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert "minItems" not in str(fmt) and "minLength" not in str(fmt)  # lengths are checked by the app afterwards
    assert sent["headers"]["Authorization"] == "Bearer test-key" and sent["url"].endswith("/chat/completions")
    assert p.serial is False  # a hosted service can answer several people at once

    monkeypatch.setattr(groq.httpx, "post", lambda *a, **k: _Reply(429, {}))
    try:
        p.generate_json(system="s", prompt="p", schema=schema, max_tokens=200)
        raise AssertionError("expected AIUnavailable")
    except AIUnavailable as e:
        assert e.reason == "busy"
    monkeypatch.setattr(groq.httpx, "post", lambda *a, **k: _Reply(200, {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]}))
    try:
        p.generate_json(system="s", prompt="p", schema=schema, max_tokens=200)
        raise AssertionError("expected AIBadOutput")
    except AIBadOutput:
        pass
    assert groq.GroqProvider("", "m", 30).status()["reason"] == "not_configured"


def test_server_picks_the_ai_provider_from_settings(monkeypatch):
    import dataclasses

    from app.ai import runner
    from app.config import get_config
    for setting, expected in ((dict(ai_provider="groq", groq_api_key="k"), "groq"), (dict(ai_provider="ollama"), "ollama"),
                              (dict(ai_enabled=False), "disabled")):
        cfg = dataclasses.replace(get_config(), **setting)
        monkeypatch.setattr(runner, "get_config", lambda cfg=cfg: cfg)
        runner.default_provider.cache_clear()
        assert runner.default_provider().name == expected
    runner.default_provider.cache_clear()
