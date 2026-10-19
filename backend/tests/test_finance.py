"""Money: setup, balances, the rules for each kind of entry, and month figures."""

import uuid

from tests.conftest import ok

MON, TUE = "2026-03-02", "2026-03-03"


def categories(client):
    food = ok(client.post("/api/finance/categories", json={"name": "Groceries", "kind": "expense"}), 201)
    fun = ok(client.post("/api/finance/categories", json={"name": "Entertainment", "kind": "expense"}), 201)
    pay = ok(client.post("/api/finance/categories", json={"name": "Salary", "kind": "income"}), 201)
    return food, fun, pay


def set_up(client):
    o = ok(client.post("/api/finance/setup", json={"accounts": [
        {"name": "Everyday debit", "type": "debit", "balance_cents": 120_000},
        {"name": "Rewards card", "type": "credit", "balance_cents": 0},
    ]}))
    by_type = {a["type"]: a for a in o["accounts"]}
    return by_type["debit"], by_type["credit"]


def spend(client, account, category, cents, when=MON, note="", **extra):
    return client.post("/api/finance/transactions", json={
        "kind": "expense", "amount_cents": cents, "account_id": account["id"], "category_id": category["id"],
        "occurred_on": when, "note": note, **extra})


def test_setup_once_and_starting_balances(client):
    assert ok(client.get("/api/finance/overview"))["set_up"] is False
    debit, credit = set_up(client)
    assert (debit["balance_cents"], credit["balance_cents"]) == (120_000, 0)
    o = ok(client.get("/api/finance/overview"))
    assert (o["available_cents"], o["owed_cents"], o["net_cents"], o["set_up"]) == (120_000, 0, 120_000, True)
    r = client.post("/api/finance/setup", json={"accounts": [{"name": "Again", "type": "debit", "balance_cents": 1}]})
    assert r.status_code == 409


def test_spending_moves_the_right_balance(client):
    food, fun, _ = categories(client)
    debit, credit = set_up(client)
    ok(spend(client, debit, food, 4_250, note="Weekly shop"), 201)  # $42.50 from debit
    ok(spend(client, credit, fun, 1_999, note="Cinema"), 201)  # $19.99 on the card
    o = ok(client.get("/api/finance/overview"))
    bal = {a["type"]: a["balance_cents"] for a in o["accounts"]}
    assert bal == {"debit": 120_000 - 4_250, "credit": 1_999}  # debit down, card owed up
    assert (o["available_cents"], o["owed_cents"], o["net_cents"]) == (115_750, 1_999, 113_751)
    d = ok(client.get(f"/api/finance/day?date={MON}"))
    assert d["spent_cents"] == 6_249
    assert {t["note"] for t in d["transactions"]} == {"Weekly shop", "Cinema"}
    assert {t["account_name"] for t in d["transactions"]} == {"Everyday debit", "Rewards card"}


def test_income_and_card_payment(client):
    food, _, salary = categories(client)
    debit, credit = set_up(client)
    ok(spend(client, credit, food, 30_000), 201)
    ok(client.post("/api/finance/transactions", json={"kind": "income", "amount_cents": 250_000,
                                                      "account_id": debit["id"], "category_id": salary["id"], "occurred_on": MON}), 201)
    ok(client.post("/api/finance/transactions", json={"kind": "payment", "amount_cents": 10_000,
                                                      "account_id": debit["id"], "to_account_id": credit["id"], "occurred_on": MON}), 201)
    bal = {a["type"]: a["balance_cents"] for a in ok(client.get("/api/finance/overview"))["accounts"]}
    assert bal == {"debit": 120_000 + 250_000 - 10_000, "credit": 30_000 - 10_000}


def test_rules_are_enforced(client):
    food, _, salary = categories(client)
    debit, credit = set_up(client)
    assert spend(client, debit, food, 0).status_code == 422  # amount must be positive
    assert spend(client, debit, food, 500, when="2026-03-03").status_code == 422  # future (today is Monday)
    assert spend(client, debit, food, 500, when="2026-03-01").status_code == 422  # before the account was set up
    assert spend(client, debit, salary, 500).status_code == 422  # income category on an expense
    r = client.post("/api/finance/transactions", json={"kind": "income", "amount_cents": 500,
                                                       "account_id": credit["id"], "category_id": salary["id"], "occurred_on": MON})
    assert r.status_code == 422  # money in goes to a debit account
    r = client.post("/api/finance/transactions", json={"kind": "payment", "amount_cents": 500,
                                                       "account_id": credit["id"], "to_account_id": debit["id"], "occurred_on": MON})
    assert r.status_code == 422  # payments go debit -> credit


def test_repeated_submission_records_once_and_edit_delete(client):
    food, fun, _ = categories(client)
    debit, credit = set_up(client)
    tid = str(uuid.uuid4())
    ok(spend(client, debit, food, 1_000, id=tid), 201)
    ok(spend(client, debit, food, 1_000, id=tid), 200)
    assert ok(client.get(f"/api/finance/day?date={MON}"))["spent_cents"] == 1_000
    ok(client.patch(f"/api/finance/transactions/{tid}", json={"account_id": credit["id"], "category_id": fun["id"], "amount_cents": 1_500}))
    bal = {a["type"]: a["balance_cents"] for a in ok(client.get("/api/finance/overview"))["accounts"]}
    assert bal == {"debit": 120_000, "credit": 1_500}  # moved to the card
    assert client.delete(f"/api/finance/transactions/{tid}").status_code == 204
    assert client.delete(f"/api/finance/transactions/{tid}").status_code == 204
    assert ok(client.get("/api/finance/overview"))["owed_cents"] == 0


def test_month_figures(client, clock):
    food, fun, _ = categories(client)
    clock.set("2026-02-27T12:00:00Z")
    debit, credit = set_up(client)
    ok(spend(client, debit, food, 5_000, when="2026-02-27"), 201)  # last month
    clock.set("2026-03-03T12:00:00Z")  # Tuesday the 3rd
    ok(spend(client, debit, food, 3_000, when=MON), 201)
    ok(spend(client, credit, fun, 1_000, when=MON), 201)
    ok(spend(client, debit, food, 2_000, when=TUE), 201)
    m = ok(client.get("/api/finance/month?month=2026-03"))
    assert m["spent_cents"] == 6_000 and m["previous_month_spent_cents"] == 5_000
    assert m["days_counted"] == 3 and m["avg_per_day_cents"] == 2_000  # March 1-3
    assert [(r["name"], r["spent_cents"], r["share_pct"]) for r in m["by_category"]] == [("Groceries", 5_000, 83), ("Entertainment", 1_000, 17)]
    assert m["top_expenses"][0]["amount_cents"] == 3_000
    assert client.get("/api/finance/month?month=2026-13").status_code == 422


def test_money_is_exported(client):
    food, _, _ = categories(client)
    debit, _ = set_up(client)
    ok(spend(client, debit, food, 700), 201)
    exported = ok(client.get("/api/data/export"))
    assert len(exported["finance_accounts"]) == 2 and len(exported["finance_transactions"]) == 1
    assert exported["settings"]["currency"] == "USD"


# ---------------------------------------------------------------- repeating entries

def repeat(client, account, category, cents, next_on, name="Rent", **extra):
    return client.post("/api/finance/recurring", json={
        "name": name, "kind": "expense", "amount_cents": cents, "account_id": account["id"],
        "category_id": category["id"], "frequency": "monthly", "next_on": next_on, **extra})


def balances_by_type(client):
    return {a["type"]: a["balance_cents"] for a in ok(client.get("/api/finance/overview"))["accounts"]}


def test_monthly_bill_is_added_on_its_day_and_only_once(client, clock):
    food, _, _ = categories(client)
    debit, credit = set_up(client)  # today: Monday 2 March
    rule = ok(repeat(client, credit, food, 1_599, "2026-03-02", name="Streaming"), 201)
    assert rule["next_on"] == "2026-04-02" and rule["day_of_month"] == 2  # today's was added straight away
    d = ok(client.get(f"/api/finance/day?date={MON}"))
    assert [(t["note"], t["amount_cents"], t["recurring_id"]) for t in d["transactions"]] == [("Streaming", 1_599, rule["id"])]
    for _ in range(3):  # reading again never adds it twice
        ok(client.get("/api/finance/overview"))
    assert balances_by_type(client)["credit"] == 1_599

    clock.set("2026-05-10T12:00:00Z")  # away for two months: April and May are both added
    assert balances_by_type(client)["credit"] == 3 * 1_599
    assert ok(client.get("/api/finance/day?date=2026-04-02"))["spent_cents"] == 1_599
    assert ok(client.get("/api/finance/day?date=2026-05-02"))["spent_cents"] == 1_599
    assert ok(client.get("/api/finance/recurring"))["rules"][0]["next_on"] == "2026-06-02"
    # Future days show what's scheduled, without recording it.
    s = ok(client.get("/api/finance/day?date=2026-06-02"))
    assert s["transactions"] == [] and [r["name"] for r in s["scheduled"]] == ["Streaming"]


def test_month_end_dates_weekly_and_yearly_schedules(client, clock):
    from datetime import date
    from app.services.finance import occurrence
    jan31 = date(2026, 1, 31)
    assert [occurrence(jan31, "monthly", 1, n).isoformat() for n in range(4)] == [
        "2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]  # never drifts to the 28th
    assert occurrence(date(2028, 2, 29), "yearly", 1, 1) == date(2029, 2, 28)
    assert occurrence(date(2026, 3, 2), "weekly", 2, 3) == date(2026, 4, 13)
    assert occurrence(date(2026, 1, 15), "monthly", 3, 4) == date(2027, 1, 15)  # quarterly

    food, _, salary = categories(client)
    debit, _ = set_up(client)
    ok(client.post("/api/finance/recurring", json={
        "name": "Paycheck", "kind": "income", "amount_cents": 200_000, "account_id": debit["id"],
        "category_id": salary["id"], "frequency": "weekly", "interval": 2, "next_on": "2026-03-06"}), 201)
    clock.set("2026-03-21T12:00:00Z")  # 6th and 20th
    assert balances_by_type(client)["debit"] == 120_000 + 2 * 200_000


def test_deleted_entry_stays_deleted_and_changes_apply_going_forward(client, clock):
    food, fun, _ = categories(client)
    debit, credit = set_up(client)
    rule = ok(repeat(client, debit, food, 50_000, MON), 201)
    entry = ok(client.get(f"/api/finance/day?date={MON}"))["transactions"][0]
    assert client.delete(f"/api/finance/transactions/{entry['id']}").status_code == 204
    assert ok(client.get(f"/api/finance/day?date={MON}"))["transactions"] == []  # not re-added

    # A new amount and card apply to future entries only.
    ok(client.patch(f"/api/finance/recurring/{rule['id']}", json={"amount_cents": 52_000, "account_id": credit["id"]}))
    clock.set("2026-04-02T12:00:00Z")
    assert balances_by_type(client) == {"debit": 120_000, "credit": 52_000}

    # Moving the date re-anchors the schedule.
    r = ok(client.patch(f"/api/finance/recurring/{rule['id']}", json={"next_on": "2026-04-15"}))
    assert r["next_on"] == "2026-04-15" and r["day_of_month"] == 15
    assert client.patch(f"/api/finance/recurring/{rule['id']}", json={"next_on": "2026-04-01"}).status_code == 422

    # Deleting the rule keeps what it added.
    assert client.delete(f"/api/finance/recurring/{rule['id']}").status_code == 204
    assert client.delete(f"/api/finance/recurring/{rule['id']}").status_code == 204
    kept = ok(client.get("/api/finance/day?date=2026-04-02"))["transactions"]
    assert len(kept) == 1 and kept[0]["recurring_id"] is None


def test_paused_rule_skips_missed_dates(client, clock):
    food, _, _ = categories(client)
    debit, _ = set_up(client)
    rule = ok(repeat(client, debit, food, 1_000, "2026-03-05", name="Gym"), 201)
    p = ok(client.patch(f"/api/finance/recurring/{rule['id']}", json={"paused": True}))
    assert p["paused"] and p["next_on"] is None
    clock.set("2026-05-20T12:00:00Z")
    assert balances_by_type(client)["debit"] == 120_000  # nothing while paused
    r = ok(client.patch(f"/api/finance/recurring/{rule['id']}", json={"paused": False}))
    assert r["next_on"] == "2026-06-05"  # March-May are skipped, not back-filled
    assert balances_by_type(client)["debit"] == 120_000


def test_repeating_rules_are_checked(client):
    food, _, salary = categories(client)
    debit, credit = set_up(client)
    assert repeat(client, debit, food, 100, "2026-03-01").status_code == 422  # in the past
    assert repeat(client, debit, salary, 100, MON).status_code == 422  # income category on spending
    assert repeat(client, debit, food, 100, MON, frequency="daily").status_code == 422
    assert repeat(client, debit, food, 100, MON, interval=13).status_code == 422
    assert repeat(client, debit, food, 100, MON, name="  ").status_code == 422
    r = client.post("/api/finance/recurring", json={"name": "Card", "kind": "payment", "amount_cents": 100,
                                                    "account_id": credit["id"], "to_account_id": debit["id"], "next_on": MON})
    assert r.status_code == 422  # payments go debit -> credit
    ok(client.patch(f"/api/finance/accounts/{debit['id']}", json={"archived": True}))
    assert repeat(client, debit, food, 100, MON).status_code == 422  # archived account
    rid = str(uuid.uuid4())
    ok(repeat(client, credit, food, 100, "2026-03-09", id=rid), 201)
    ok(repeat(client, credit, food, 100, "2026-03-09", id=rid), 200)  # repeated submission
    s = ok(client.get("/api/finance/recurring"))
    assert len(s["rules"]) == 1 and s["bills_next_30_days_cents"] == 100


def test_repeating_entries_export_and_import(client):
    food, _, _ = categories(client)
    debit, _ = set_up(client)
    ok(repeat(client, debit, food, 900, MON), 201)
    exported = ok(client.get("/api/data/export"))
    assert len(exported["finance_recurring"]) == 1
    assert exported["finance_transactions"][0]["recurring_id"] == exported["finance_recurring"][0]["id"]
    report = ok(client.post("/api/data/import?dry_run=true", json=exported))
    assert report["collections"]["finance_recurring"]["skipped_existing"] == 1



# ---------------------------------------------------------------- Splitwise totals

def test_splitwise_totals_are_entered_by_hand(client):
    debit, credit = set_up(client)
    o = ok(client.get("/api/finance/overview"))
    assert (o["splitwise"]["get_cents"], o["splitwise"]["pay_cents"], o["splitwise"]["updated_at"]) == (0, 0, None)
    sw = ok(client.put("/api/finance/splitwise", json={"get_cents": 4_000, "pay_cents": 1_500}))
    assert (sw["get_cents"], sw["pay_cents"]) == (4_000, 1_500) and sw["updated_at"]
    ok(client.put("/api/finance/splitwise", json={"pay_cents": 0}))  # settled what you owed; the other stays
    o = ok(client.get("/api/finance/overview"))
    assert (o["splitwise"]["get_cents"], o["splitwise"]["pay_cents"]) == (4_000, 0)
    assert o["net_cents"] == 120_000 - 0 + 4_000  # net includes what you should get / pay on Splitwise
    assert {a["type"]: a["balance_cents"] for a in o["accounts"]} == {"debit": 120_000, "credit": 0}  # accounts untouched
    assert client.put("/api/finance/splitwise", json={"get_cents": -1}).status_code == 422
    exported = ok(client.get("/api/data/export"))
    assert exported["finance_splitwise"]["get_cents"] == 4_000


# ---------------------------------------------------------------- trends (calculated)

def three_months_of_spending(client, clock):
    food, fun, salary = categories(client)
    clock.set("2026-01-02T12:00:00Z")
    debit, credit = set_up(client)
    clock.set("2026-01-31T12:00:00Z")
    for when, cat, cents in [("2026-01-05", food, 6_000), ("2026-01-20", food, 4_000), ("2026-01-09", fun, 2_000)]:
        ok(spend(client, debit, cat, cents, when=when, note="secret note"), 201)
    ok(client.post("/api/finance/transactions", json={"kind": "income", "amount_cents": 300_000, "account_id": debit["id"],
                                                      "category_id": salary["id"], "occurred_on": "2026-01-15"}), 201)
    clock.set("2026-02-27T12:00:00Z")
    ok(spend(client, credit, food, 14_000, when="2026-02-10"), 201)
    ok(spend(client, credit, fun, 1_000, when="2026-02-11"), 201)
    clock.set("2026-03-10T12:00:00Z")
    ok(spend(client, debit, food, 5_000, when="2026-03-04"), 201)
    return food, fun


def test_trends_compare_this_month_with_full_months(client, clock):
    three_months_of_spending(client, clock)
    t = ok(client.get("/api/finance/trends"))
    assert [(m["month"], m["tracked"], m["spent_cents"]) for m in t["months"]] == [
        ("2025-12", False, 0), ("2026-01", True, 12_000), ("2026-02", True, 15_000), ("2026-03", True, 5_000)]
    jan = t["months"][1]
    assert (jan["saved_cents"], jan["savings_rate_pct"]) == (288_000, 96)
    assert t["full_months_counted"] == 2 and t["avg_monthly_spent_cents"] == 13_500  # December wasn't tracked: not averaged in
    food = next(c for c in t["categories"] if c["name"] == "Groceries")
    # By the 10th: January had 60 (the 5th), February 140 (the 10th); usually 100. A projection isn't used.
    assert (food["avg_monthly_cents"], food["this_month_cents"], food["usual_by_today_cents"]) == (12_000, 5_000, 10_000)
    assert food["change_pct"] == -50  # 50 so far vs. 100 usually by the 10th
    assert (t["this_month_cents"], t["usual_by_today_cents"], t["day_of_month"]) == (5_000, 11_000, 10)
    assert t["categories"][0]["name"] == "Groceries"  # biggest first
