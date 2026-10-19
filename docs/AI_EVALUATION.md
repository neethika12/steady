# Local AI evaluation (phi4-mini)

## Hardware and model choice

* **Machine:** Apple M5, 10 cores, 16 GB unified memory, macOS. Docker VM (Colima) uses 2 CPU / 3 GB.
* **Model:** `phi4-mini` (Microsoft Phi-4-mini-instruct, 3.8B parameters, Q4_K_M), **2.5 GB download**,
  about 3.5–4 GB RAM while loaded, **MIT licence**. Served by Ollama 0.40.3 on the host at `127.0.0.1:11434`.
* Chosen over `llama3.2:3b` (smaller, weaker at instructions) and `gemma3:4b` (heavier) as the best balance
  for 16 GB. See the README for alternatives on smaller machines.

## Method

(Note: these runs happened when the Inbox still held free-text items; breakdown now works on tasks only, with the same prompt and checks.)

`backend/scripts/evaluate_ai.py` runs against the separate **test** stack (never real data). It creates
representative fictional records (a report task, a picnic-planning task, six tasks with deadlines and estimates, six
unfinished tasks with reasons, a habit with gaps, two journal entries) and calls each AI feature 3 times
through the real API, so every reply passes through the same validation the app uses. It records validity,
latency, whether daily plans fit the time budget before the app's own check, and the actual text, which was read
by hand for intent, grounding and tone.

The latest raw output is in [AI_EVALUATION_RESULTS.md](AI_EVALUATION_RESULTS.md). (That run used the test
database after earlier test runs, so it contains extra test records such as "Stretch …" habits.)

## What the evaluation found, and what was changed

Three evaluation rounds were run; each found problems that led to fixes:

| Round | Problem found in real output | Fix |
| --- | --- | --- |
| 1 | Journal prompts came back labelled "T1:", "R2:", "H3:" (the model copied the ref style) | Prompt says "no numbering or labels"; labels are stripped deterministically |
| 1 | Reason observations repeated "(refs: …)" in the text, said "the person", and leaned judgmental ("struggles") | Second-person, describe-the-records prompt; inline refs stripped; sources shown by the app |
| 1 | **Habit review stated a false fact** ("completed once in 7 days" when 1 day was scheduled) | **Numeric grounding check:** every number in an observation must appear in the supplied data, or the answer is rejected and retried |
| 1 | Daily plan exceeded the time budget in 1 of 3 runs | Over-budget plans are sent back once with the exact overrun; the app still trims deterministically |
| 2 | Habit review suggested *increasing* a habit at 31% consistency (2 of 3 runs), contrary to instructions | Deterministic rule: "do more" suggestions for habits under 60% are rejected (retry) or dropped |
| 2 | Refs written into text ("H1, H2 and H4") | Refs are replaced by the record's real name |

## Results of the final round (3 runs per feature)

| Feature | Valid | Latency (median / max) | Observations |
| --- | --- | --- | --- |
| Break down a task | 3/3 | 3.5 s / 3.9 s | Concrete verb-first steps that keep the user's wording ("Identify the two biggest variances"). Steps often add up to more than the original estimate; the UI shows this. |
| Daily plan | 3/3 | 2.7 s / 4.4 s | **Respected the time budget 3/3 times** (after round 1 changes). Chose the deadline-tomorrow, high-priority task first; reasons refer only to priority, deadline and estimate. |
| Reasons summary | 2/3 (1 rejected by the number check) | 10.4 s / 18 s | Counts match the app's counts; suggestions are practical but generic ("break larger tasks down"). Citations can list only some of the records behind a count. |
| Habit review | 3/3 | 5.5 s / 15 s | After the rules, suggestions for the low-consistency habit always make it easier ("reduce the number of scheduled days"). One run produced a contradictory "reduce to 7 days a week" for a daily habit. |
| Journal prompts | 3/3 | 1.4 s / 1.4 s | Gentle open questions; no labels after the fix. No journal text is sent. |
| Journal summary | 3/3 | 3.2 s / 3.3 s | Faithful second-person summary of only the two selected entries; no invented details, no advice or diagnosis. |

## Does it…

* **respect available time?** The app guarantees it (it trims and shows what was removed). On its own, the model
  respected the budget in 3/3 runs in the final round and 2/3 before the retry-with-feedback change.
* **preserve user intent?** Yes for breakdowns and summaries: steps and summaries stay on the supplied item
  and add no new goals. Wording is sometimes repetitive across runs.
* **refer only to supplied records?** Yes. Record refs are constrained by an enum in the JSON schema and
  re-checked by the backend; invented numbers are caught by the grounding check. Any reply that fails is never
  shown.

## Honest limitations

* Suggestions are often **generic**. A 3.8B model doesn't reason deeply about someone's week.
* Citations behind a count can be **incomplete** (e.g. 10 of 15 records listed). The count itself always comes
  from the app.
* Occasional **contradictory phrasing** in habit suggestions slips past the rules ("reduce to 7 days a week").
* Retries add latency (up to ~18 s). Every request is bounded by the timeout, output limit and rate limit.
* The language guard is a word list. It blocks common diagnostic or judgmental terms, not every possible phrasing.
* Results vary between runs (temperature 0.2). Re-running a request can give a different, also-validated proposal.
