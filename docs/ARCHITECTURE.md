# Architecture and data model

## Components

| Part | Responsibility |
| --- | --- |
| **React app** (`frontend/src`) | UI only. Holds no authoritative data. Keeps the selected date/view in session storage and an unsaved journal draft in local storage. |
| **nginx** (frontend container) | Serves the built app and forwards `/api/*` to the backend, so the browser talks to one origin (no CORS needed). |
| **FastAPI** (`backend/app`) | Validation, all business rules, all calculations, transactions, AI orchestration. |
| **PostgreSQL** | The only authoritative store. Not reachable from outside the Docker network. |
| **Ollama** (host) | Local model inference over HTTP, called only by the backend, only on explicit user action. |

Request flow for a change (for example, reviewing a task):
browser → `PUT /api/plans/{id}/review` → the router opens one DB transaction → `services/tasks.review_plan`
locks the rows, applies the history rules, writes an audit row → commit → JSON response.
If anything fails, the whole transaction rolls back.

## Calendar days and time

* Instants (`created_at`, `completed_at`, `reviewed_at` …) are `timestamptz`, stored in UTC.
* Dated records (`plan_date`, `checkin_date`, `entry_date`, schedule ranges) are plain `date` values.
* "Today" is computed on the server from the configured timezone (`app_settings.timezone`) and returned by
  `GET /api/settings`. The browser never computes "today" from its own clock.
* Day arithmetic is done on dates, never by adding 24 h, so DST days (23 h / 25 h) are correct.
  `timeutil.local_day_bounds_utc` returns the real UTC bounds of a local day when needed.
* Week start is configurable (0 = Monday … 6 = Sunday).
* **Timeline hours** (`app_settings.timeline_start` / `timeline_end`, default 07:00–22:00) set the Day timeline.
  If the end is earlier than the start (e.g. 11:00–02:00), the user's day runs past midnight: until `timeline_end`
  "today" is still the previous date (`timeutil.logical_today`), times before `timeline_end` sort after 23:59, and a
  planned range may run past midnight (end earlier than start). With a normal timeline that is refused.

## Tables

| Table | Key columns | Notes |
| --- | --- | --- |
| `app_settings` | `timezone`, `timezone_confirmed`, `week_start` | Single row (`id = 1`). |
| `inbox_items` | `text`, `status`, `converted_to_type`, `converted_to_id`, `converted_at` | **Legacy.** The Inbox used to hold free text that could become a task, habit or journal note. Migration 0002 turned every open item into an undated task (text kept, linked by `tasks.source_inbox_item_id`). Kept for history and export/import; nothing new is written here. |
| `tasks` | `title`, `description`, `priority`, `category`, `estimated_minutes`, `actual_minutes`, `deadline`, `planned_date`, `status` (active/completed/cancelled/split), `completed_at`, `cancelled_at`, `archived_at`, `parent_task_id`, `source_inbox_item_id` | `planned_date` = the day of the task's open plan, or NULL when unscheduled. |
| `task_plans` | `task_id`, `plan_date`, `outcome`, `reason`, `reason_note`, `reviewed_at`, `completed_at`, `follow_up`, `carried_from_plan_id` | **One row per task per day** (unique). `outcome IS NULL` = not reviewed. |
| `habits` | `name`, `kind` (boolean/duration/count), `unit`, `start_date`, `archived_on`, `source_inbox_item_id` | |
| `habit_schedules` | `habit_id`, `effective_from`, `effective_to`, `schedule_type` (daily/weekdays/weekly_target), `weekdays`, `weekly_target`, `target_value` | Versioned: a change closes the current version and starts a new one. |
| `habit_pauses` | `habit_id`, `start_date`, `end_date` (NULL = until resumed) | Overlapping pauses are refused. |
| `habit_checkins` | `habit_id`, `checkin_date`, `value` | Unique per habit + date. Written with an upsert ("set value"), so repeats can't double-count. |
| `journal_entries` | `entry_date` (unique), `body`, `mood`, `energy`, `went_well`, `was_difficult`, `on_mind`, `version` | `version` increases on each save (optimistic concurrency). |
| `finance_accounts` | `name`, `type` (debit/credit), `opening_balance_cents`, `opened_on`, `archived_at` | Balance = opening + entries (calculated, never stored). |
| `finance_categories` | `name`, `kind` (expense/income), `sort_order`, `archived_at` | Starter set inserted by migration 0007. |
| `finance_transactions` | `occurred_on`, `kind` (expense/income/payment), `amount_cents` (> 0), `account_id`, `to_account_id` (payments), `category_id`, `note` | Checked: payments debit → credit; money in → debit only; not before the account's `opened_on`; not in the future. |
| `finance_recurring` | `name`, `kind`, `amount_cents`, accounts/category as for entries, `frequency` (weekly/monthly/yearly), `interval` (1-12), `anchor_on`, `posted_count`, `paused_at` | Occurrence *n* = `anchor_on` + *n* × interval (month-end clamped). Due ones become `finance_transactions` with `recurring_id` (unique per rule per day; `ON DELETE SET NULL`). |
| `finance_splitwise` | `get_cents`, `pay_cents` (both ≥ 0) | Single row (`id = 1`): Splitwise totals entered by hand. Counted in Net only. |
| `users` | `email` (unique, lower-case), `password_hash` (scrypt), `last_login_at` | No row-level security (needed to log in); never returned except your own email. |
| `auth_sessions` | `user_id`, `token_hash` (SHA-256 of the cookie), `expires_at`, `last_seen_at` | Deleted on log-out; all but the current one deleted on password change. |
| `audit_log` | `entity_type`, `entity_id`, `action`, `before`, `after`, `note`, `created_at` | Append-only: reviews, corrections, moves, carry-forwards, cancellations, splits, schedule changes, pauses. |

All primary keys are UUIDs. The client generates the id for create requests, so a retried request (double click,
flaky network) returns the existing record instead of creating a duplicate.

## Daily history rules (To-Do)

1. **Scheduling** an active task for day D:
   * If its open plan is dated today or later and has no outcome → the plan row is **moved** to D (audited as `moved`).
   * Otherwise → a **new** plan row for D is created, with `carried_from_plan_id` pointing at the most recent
     earlier unfinished or unreviewed plan. The earlier row is never modified, except that an unfinished
     earlier row with no follow-up gets `follow_up = rescheduled`.
   * A task can't get a second record on a day where it already has one (409 with an explanation).
2. **Marking** a task sets the outcome for one plan (only for days that have started). The UI offers only
   *Completed* and *Not completed*; **Not completed requires a written reason** (`reason_note`, ≥ 3 characters;
   the category `reason` is an optional tag). `partial` is accepted only in older history and imports.
   * `completed` → the task becomes completed; the plan's `completed_at` is the real instant. Any later open
     plan dated today or later is removed (audited).
   * `not_completed` → the task loses its day. Where it shows next depends on `tasks.origin`:
     `inbox` (captured in the Inbox) → it is listed in the Inbox again with a "Not completed · date" badge;
     `day` (created directly on a day) → it stays visible only on that day, which asks *Move to tomorrow*,
     *Move to Inbox* (sets `origin = inbox`, follow-up `unscheduled`) or *Leave it here* (follow-up `left`).
     Nothing else happens automatically. Moving any task to the Inbox explicitly also sets `origin = inbox`.
   * Clearing the outcome returns the plan to "not reviewed".
   * Changing an existing outcome is a **correction**, audited with before/after and an optional note.
3. **Follow-ups** (always explicit): reschedule (rule 1), split (creates child tasks with `parent_task_id`, the
   original becomes `split`), leave unscheduled, or cancel.
4. **Cancelling** a task: an unreviewed plan for today or a past day gets outcome `cancelled` (excluded from that
   day's denominator, shown separately); a future plan is removed.
5. **Restoring** a cancelled task undoes the cancellation on its latest plan: the plan's outcome goes back to empty
   and the task is planned for that same day and time again (a past day shows *Not marked yet*). A task cancelled
   from the Inbox (no plan) returns to the Inbox. The undo is audited as `cancellation_undone`. **Deleting** (explicit, confirmed) removes the
   task, its day records and its audit entries, leaving one content-free "deleted" audit entry.
6. **Time of day** (`task_plans.planned_time`, NULL = anytime, plus an optional `planned_end_time` for a range;
   the end must differ from the start; it may be earlier than the start only when the user's timeline runs past
   midnight) belongs to the dated plan. Changing only the time
   updates that plan (audited as `time_changed`); carrying a task forward copies the time unless a new one is given.

### Plan states shown in the UI

| `outcome` | Day | Shown as |
| --- | --- | --- |
| NULL | before today | **Not marked yet** (counts in the denominator) |
| NULL | today or later | Planned / still open |
| completed / not_completed (or older `partial`) | any | as recorded, with the written reason |
| cancelled | any | Cancelled · not counted |

### Completion calculation

```
counted        = plans on the day − cancelled plans
completion_pct = round_half_up(100 × completed ÷ counted)       (none when counted = 0)
effort_pct     = round_half_up(100 × est. minutes of completed ÷ est. minutes of counted plans)
```

Range insights (week / 4 weeks) sum the daily counts through today. Future days are not evaluated.
Reasons are reported only for plans explicitly reviewed as unfinished, and the UI states how many unfinished
plans have no recorded reason ("missing data" is never mixed with "recorded outcome").

## Habit rules

* A day is judged by the schedule version in force on that day, so schedule changes never rewrite history.
  Changes may start today or later, but not earlier than the current version's start.
* Day statuses: `done`, `pending` (today, not yet), `missed` (past scheduled day, not done), `not_scheduled`,
  `extra` (done on an unscheduled day), `paused`, `inactive` (before start / after archive), `future`, and for
  weekly-target habits `open` (any non-done day; never a failure).
* **Daily progress** = done ÷ scheduled habits for that day (daily/weekday types only).
* **Weekly targets**: sessions this week ÷ required, where
  `required = ceil(target × available days ÷ 7)` when part of the week is unavailable (start, pause, archive).
* **Streaks**: daily/weekday habits count consecutive done scheduled days, skipping unscheduled and paused days;
  today not done yet doesn't break the streak. Weekly-target habits count consecutive weeks that met the
  target; the current week counts once met and never breaks the streak while in progress.
* **Consistency** = done ÷ (done + missed) over finished days. Today's pending check-in is left out.

## Journal saving and conflicts

* The editor autosaves about 1 s after typing stops, and immediately when you switch day or tab.
* Every save sends `base_version`. If the server's version differs, it returns **409** with the newer entry;
  nothing is overwritten. The editor shows both versions; *Keep my version* resubmits on top of the newer one,
  and *Use the saved version* discards local edits.
* Every keystroke is mirrored into a **local draft** (browser storage) until the server confirms the save. On
  reload, a draft based on the current version is restored and saved; a draft based on an older version opens
  the conflict view.

## The Inbox (tasks without a day)

The Inbox is not a separate kind of record: it is the list of **active tasks whose `planned_date` is NULL**

with `origin = 'inbox'` (`GET /api/tasks?view=inbox`), shown as a permanent column on the left of the app.

* Quick capture creates a task with only a title. The client sends its own `id`, so a double click, a retry or
  several identical requests at the same moment store exactly one task (a racing duplicate hits the primary key,
  and the endpoint returns the task that was saved).
* Dragging a task onto a day (or *Move to date*) calls the normal scheduling endpoint, so carry-forward rules apply.
* Tasks reviewed as unfinished land back in the Inbox with a badge ("Not completed · Mon 12 Oct") until you plan
  them again, split them, cancel them, or choose *Keep for later*.

## AI pipeline

```
user clicks an AI button
  → router → features.<feature>()  selects records with ordinary queries, assigns refs (T1, R1, H1, dates), minimal fields
  → runner.run()                   rate limit + one-at-a-time → provider.generate_json(schema) → Pydantic validation
                                   → feature validator (refs exist, numbers grounded, language guard, time budget)
                                   → on failure: one retry with the reason, then 502 with a clear message
  → proposal JSON (nothing written)
  → user edits/accepts → normal endpoints (split, convert, batch schedule)
```

`ai/provider.py` defines the two-method interface (`status`, `generate_json`). `ai/ollama.py` implements it
with plain `httpx` calls to `/api/tags` and `/api/chat`. Another provider can be added without touching features.


## Accounts and row-level security

Every data table has `user_id` (default: the signed-in user, `current_setting('app.user_id')`), and a policy
`owner_only` that allows reading and writing only rows whose `user_id` matches it. `app.db` makes every app
connection `SET ROLE steady_app` (not a superuser, so policies apply, and `FORCE ROW LEVEL SECURITY` covers the
table owner too) and sets `app.user_id` at the start of every transaction from the session cookie. With no user,
data tables look empty and can't be written. Migrations run with the normal credentials. Deleting a user removes
their rows through `ON DELETE CASCADE`.
