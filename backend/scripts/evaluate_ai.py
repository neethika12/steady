"""Evaluate the local model on representative requests.

Runs against the separate test stack (default http://127.0.0.1:8001), never your
real data. It creates sample records there, calls each AI feature several times and
prints a Markdown report: validity, time-budget respect, grounding and latency.

    python backend/scripts/evaluate_ai.py --runs 3 > docs/AI_EVALUATION_RESULTS.md
"""

import argparse
import statistics
import sys
import time
from datetime import date, timedelta

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8001/api")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    if ":8000" in args.api:
        print("Refusing to evaluate against port 8000 (your real data).", file=sys.stderr)
        return 1
    c = httpx.Client(base_url=args.api, timeout=300)
    status = c.get("/ai/status").json()
    if not status["available"]:
        print(f"Local AI unavailable: {status['message']}", file=sys.stderr)
        return 1
    today = date.fromisoformat(c.get("/settings").json()["today"])
    tag = str(int(time.time()))[-5:]

    def post(path, body):
        # Respect the app's own AI rate limit instead of tripping it.
        while True:
            t0 = time.monotonic()
            r = c.post(path, json=body)
            if r.status_code != 429:
                return r, time.monotonic() - t0
            time.sleep(5)

    # ---- sample records (clearly fictional) ----
    def task(title, **kw):
        return c.post("/tasks", json={"title": f"{title} [{tag}]", **kw}).json()

    report_task = task("Write the quarterly budget report", estimated_minutes=120, priority="high",
                       description="Summarise spending vs plan for Q3 and flag the two biggest variances.")
    picnic = task("Organise a birthday picnic for Sam next month")
    plan_tasks = [
        task("Prepare slides for Monday review", estimated_minutes=90, priority="high", deadline=(today + timedelta(days=1)).isoformat()),
        task("Reply to landlord about repairs", estimated_minutes=15, priority="medium"),
        task("Renew passport application", estimated_minutes=45, priority="medium", deadline=(today + timedelta(days=10)).isoformat()),
        task("Clean up photo library", estimated_minutes=120, priority="low"),
        task("Call the dentist", estimated_minutes=10, priority="medium"),
        task("Read chapter 4 for book club", estimated_minutes=60, priority="low", deadline=(today + timedelta(days=3)).isoformat()),
    ]
    past = today - timedelta(days=2)
    reasons = ["not_enough_time", "not_enough_time", "too_large", "waiting", "low_energy", "not_enough_time"]
    for i, reason in enumerate(reasons):
        t = task(f"Past task {i + 1}", planned_date=past.isoformat(), estimated_minutes=30)
        plan = next(p for p in c.get(f"/plans/day?date={past}").json()["plans"] if p["task_id"] == t["id"])
        c.put(f"/plans/{plan['id']}/review", json={"outcome": "not_completed", "reason": reason, "reason_note": "Ran out of time before dinner"})
    habit = c.post("/habits", json={"name": f"Evening walk [{tag}]", "start_date": (today - timedelta(days=13)).isoformat(),
                                    "schedule": {"schedule_type": "daily"}}).json()
    for d in (1, 2, 5, 9):
        c.put(f"/habits/{habit['id']}/checkins/{today - timedelta(days=d)}", json={"value": 1})
    jdays = [today - timedelta(days=900 + int(tag) % 50 + i) for i in range(2)]
    for d, text in zip(jdays, ["Long day at work. The walk home in the rain helped me think about the move.",
                               "Spent the afternoon packing boxes. Called Mum. Excited and a bit tired."]):
        cur = c.get(f"/journal/{d}").json()
        c.put(f"/journal/{d}", json={"body": text, "base_version": cur["version"]})

    out = [f"# Local AI evaluation\n\nModel: **{status['model']}** via {status['provider']} · runs per feature: {args.runs} · date: {today}\n"]

    def section(name, results, notes):
        ok_runs = [r for r in results if r["ok"]]
        lat = [r["seconds"] for r in results]
        out.append(f"\n## {name}\n")
        out.append(f"- Valid proposals: {len(ok_runs)}/{len(results)} "
                   f"(rejected after validation + 1 retry: {len(results) - len(ok_runs)})")
        out.append(f"- Latency: median {statistics.median(lat):.1f} s, max {max(lat):.1f} s")
        out.extend(f"- {n}" for n in notes)

    # 1. breakdown
    res, samples = [], []
    for i in range(args.runs):
        src = ("report", report_task["id"]) if i % 2 == 0 else ("picnic", picnic["id"])
        r, s = post("/ai/breakdown", {"task_id": src[1]})
        res.append({"ok": r.status_code == 200, "seconds": s})
        if r.status_code == 200:
            samples.append((src[0], [f"{x['title']} ({x['estimated_minutes']} min)" for x in r.json()["steps"]]))
        else:
            samples.append((src[0], [f"REJECTED: {r.json()['detail']['message']}"]))
    section("1. Break down a task", res, [f"{k}: " + "; ".join(v) for k, v in samples])

    # 2. daily plan
    res, notes = [], []
    for budget in ([120, 60, 240] * args.runs)[: args.runs]:
        r, s = post("/ai/daily-plan", {"date": today.isoformat(), "available_minutes": budget,
                                       "task_ids": [t["id"] for t in plan_tasks]})
        res.append({"ok": r.status_code == 200, "seconds": s})
        if r.status_code == 200:
            j = r.json()
            raw = sum(p["estimated_minutes"] or 0 for p in j["plan"]) + sum(p["estimated_minutes"] or 0 for p in j["left_out"])
            notes.append(f"budget {budget} min → model chose {raw} min "
                         f"({'within' if j['model_respected_budget'] else 'OVER'} budget); app kept {j['planned_minutes']} min: "
                         + ", ".join(p["title"].split(" [")[0] for p in j["plan"])
                         + (f"; dropped by app: {', '.join(p['title'].split(' [')[0] for p in j['left_out'])}" if j["left_out"] else ""))
        else:
            notes.append(f"budget {budget} min → REJECTED: {r.json()['detail']['message']}")
    respected = sum(1 for n in notes if "(within" in n)
    notes.insert(0, f"Model respected the time budget on its own in {respected}/{len(notes)} runs; the app enforces it either way.")
    section("2. Suggest a daily plan", res, notes)

    # 3. reasons summary
    res, notes = [], []
    for _ in range(args.runs):
        r, s = post("/ai/reasons-summary", {"start": (today - timedelta(days=6)).isoformat(), "end": today.isoformat()})
        res.append({"ok": r.status_code == 200, "seconds": s})
        if r.status_code == 200:
            j = r.json()
            notes += [f"Observation: {o['text']} (refs: {', '.join(x['ref'] for x in o['support'])})" for o in j["observations"][:2]]
            notes += [f"Suggestion: {x['text']}" for x in j["suggestions"][:2]]
        else:
            notes.append(f"REJECTED: {r.json()['detail']['message']}")
    section("3. Summarise non-completion reasons", res, notes)

    # 4. habit review
    res, notes = [], []
    for _ in range(args.runs):
        r, s = post("/ai/habit-review", {"start": (today - timedelta(days=13)).isoformat(), "end": today.isoformat()})
        res.append({"ok": r.status_code == 200, "seconds": s})
        if r.status_code == 200:
            j = r.json()
            notes += [f"Observation: {o['text']}" for o in j["observations"][:1]]
            notes += [f"Suggestion ({x['support'][0]['name'].split(' [')[0]}): {x['text']}" for x in j["suggestions"][:2]]
        else:
            notes.append(f"REJECTED: {r.json()['detail']['message']}")
    section("4. Review habit consistency", res, notes)

    # 5. journal
    res, notes = [], []
    for _ in range(args.runs):
        r, s = post("/ai/journal-prompts", {"focus": "day"})
        res.append({"ok": r.status_code == 200, "seconds": s})
        notes.append(" | ".join(r.json()["prompts"]) if r.status_code == 200 else f"REJECTED: {r.json()['detail']['message']}")
    section("5a. Journal prompts (no journal content sent)", res, notes)
    res, notes = [], []
    for _ in range(args.runs):
        r, s = post("/ai/journal-summary", {"dates": [d.isoformat() for d in jdays], "confirm_share": True})
        res.append({"ok": r.status_code == 200, "seconds": s})
        notes.append(r.json()["summary"] if r.status_code == 200 else f"REJECTED: {r.json()['detail']['message']}")
    section("5b. Summarise selected journal entries", res, notes)

    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
