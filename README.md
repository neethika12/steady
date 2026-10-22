# Steady

A calm, personal productivity app with five tabs:

| Tab | What it's for |
| --- | --- |
| **To-Do** | Plan tasks by day or week: *Anytime*, *At a time*, or *From – to* a time range (e.g. 9:00–10:30 AM). The Day view shows three coloured columns, **High** (red), **Medium** (amber) and **Low** (green); within each, timed tasks come in time order, then anytime tasks. Drag a task to another column to change its priority with a round check circle to complete; click a task for all its actions. Mark each task **✓ Completed** or **✗ Not completed**; not completed always needs a short written reason. Every day keeps an honest record. A permanent **Inbox** column on the left holds every task without a day. |
| **Calendar** | Your **timed** tasks for the selected day on a calendar (anytime tasks stay in To-Do): blocks sized by their length (side by side when they overlap), with a line for the current time. Drag a task from the Inbox onto a half-hour slot to plan it at that time (length from its estimate, or 1 hour) and drag blocks to move them. **Click** a free spot to create a task there, or **click and drag** for a range. The hours are **yours** (Change / Settings → Timeline hours; presets Early bird, Standard, Night owl); if your day ends after midnight (e.g. 11 AM – 2 AM), it continues past midnight and until then it still counts as the previous day everywhere in the app. |
| **Habit Tracker** | Daily, weekday or "N times per week" habits with dated check-ins, streaks and a consistency calendar. |
| **Journal** | One entry per day with autosave, optional mood/energy and reflection prompts. |
| **Money** | Track daily spending against your accounts. On first use it asks how many **debit accounts** and **credit cards** you have and what's in each (money in a debit account; amount owed on a card, 0 if nothing). Then each day: the **amount**, **what it was for** (category + optional note), and **paid with** (which account). Spending lowers a debit balance or raises what a card owes; *Money in* adds to a debit account; *Card payment* pays a card from a debit account. **Repeating** entries (rent, phone, subscriptions, salary, card autopay) are set up once with a schedule (every week, 2 weeks, month, 3 months or year) and added automatically on their date as normal entries. Future days show what's scheduled. A **Splitwise** card beside your accounts holds the two totals from your Splitwise app (*you should get* / *you should pay*), entered by hand (also asked, optionally, at setup); they count towards Net. **Insights** compare the last three full months and this month so far (against what you usually spent by the same day, not a projection), by category; **Get saving tips with local AI** adds trends, up to three categories to cut back with the saving the app calculates, and saving ideas. Shows balances, the day's entries, and the month by category. AI is used only when you press the button. |

**On phones** the tabs move to a bar at the bottom of the screen, the Inbox opens full screen from the
**Inbox** button on To-Do, and every section fits the screen width. Add it to your home screen to open it like an
app (*iPhone: Safari → Share → Add to Home Screen*; *Android: Chrome → ⋮ → Add to Home screen / Install app*).
Sign in with the same account on your phone and laptop to see the same data.

All tabs share one date selector (Today, Yesterday, previous/next, calendar picker), and the selected day is kept when you switch tabs. In To-Do it sits beside the Day/Week switch, and in Week view the arrows move a whole week.
Task numbers and habit numbers are never combined.

The look is calm and focused: a neutral palette with one indigo accent, a dark Inbox column, and a
**daily affirmation** shown as a quiet quote at the top (*New quote* shows another). A progress ring and short,
supportive messages acknowledge progress without judging unfinished work.

Optional **local AI** (Ollama on your own computer) can suggest task breakdowns, daily plans, summaries of
recorded reasons, habit adjustments and journal prompts/summaries. It only *proposes*; nothing changes until you accept.

**Accounts.** Anyone can create an account (email + password) and gets their own private space. Each record
belongs to one account, and PostgreSQL itself enforces it ([row-level security](#accounts-and-privacy)), so one
person can never see or change another's tasks, habits, journal or money. Run it on your own computer, or
[host it](#hosting-railway--vercel) for others. It's open source (MIT): fork it and make it yours.

---

## Contents

1. [Technology and versions](#technology-and-versions)
1. [Accounts and privacy](#accounts-and-privacy)
1. [Hosting (Railway + Vercel)](#hosting-railway--vercel)
2. [Prerequisites](#prerequisites)
3. [First startup](#first-startup)
4. [Opening the app](#opening-the-app)
5. [Routine startup and shutdown](#routine-startup-and-shutdown)
6. [Where your data is stored](#where-your-data-is-stored)
7. [Backup and restore](#backup-and-restore)
8. [Export and import](#export-and-import)
9. [Local AI: setup, model choice and privacy](#local-ai-setup-model-choice-and-privacy)
10. [Commands that can delete data](#commands-that-can-delete-data)
11. [How the data model and daily history work](#how-the-data-model-and-daily-history-work)
12. [Development and tests](#development-and-tests)
13. [Known limitations](#known-limitations)
14. [Project layout](#project-layout)

---

## Technology and versions

| Layer | Technology | Version used and tested |
| --- | --- | --- |
| Frontend | React + TypeScript + Vite | React 19.3.0, TypeScript 7.0.2, Vite 8.3.4 |
| Styling | Tailwind CSS (Vite plugin) | 4.3.3 |
| Frontend server (Docker) | nginx, serving the production build and proxying `/api` | 1.29 (alpine) |
| Backend | Python + FastAPI + Uvicorn | Python 3.12, FastAPI 0.143.0, Uvicorn 0.54.0 |
| Database access / migrations | SQLAlchemy / Alembic, psycopg 3 driver | 2.1.4 / 1.20.0, psycopg 3.3.6 |
| Database | PostgreSQL | 17 (alpine image) |
| Local AI | Ollama on the host computer, model `phi4-mini` | Ollama 0.40.3 |
| Local environment | Docker Compose | Compose 5.6, Docker Engine 29 |
| Browser tests | Playwright | 1.64.1 |

Exact versions are pinned in `backend/requirements*.txt` and `frontend/package-lock.json`.

The architecture is deliberately simple: one React single-page app, one FastAPI service, one PostgreSQL database,
and Ollama called over plain HTTP. There are no microservices, no queue and no vector database.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

```
 Browser ──http://127.0.0.1:5173──▶ nginx (frontend container)
                                       │  /api/*
                                       ▼
                                   FastAPI (backend container, 127.0.0.1:8000) ──▶ PostgreSQL (db container, not exposed)
                                       │
                                       └──▶ Ollama on the host (127.0.0.1:11434), only when you press an AI button
```

---

## Accounts and privacy

- **Create an account** with your name, email and a password (at least 10 characters); you're then taken to
  **Log in** with your email filled in (creating an account doesn't sign you in). Passwords are hashed with scrypt and a
  random salt; the session cookie is random, `HttpOnly`, `SameSite=Lax`, HTTPS-only when hosted, and the database
  stores only its SHA-256. Sessions last 30 days (`SESSION_DAYS`).
- **Every record has an owner** (`user_id`). The app connects to PostgreSQL as the restricted role `steady_app` and
  sets the signed-in user for every transaction; **row-level security** policies then make other people's rows
  invisible and unwritable, even to code that forgets to filter. Tests check this directly
  (`backend/tests/test_accounts.py`), including that every `/api` route refuses requests without a session.
- **Repeated wrong passwords** are slowed down (8 failures per 15 minutes per email and per address), and
  sign-ups are limited per address.
- **Account menu** (the round initial at the top right): change password (signs out other browsers), log out,
  and **delete account**, which permanently removes the account and everything in it (asks for your password).
- **Journal drafts** are kept in the browser per account and removed when you log out.
- **On your own computer**, the *first* account you create takes over any data from before accounts existed
  (`CLAIM_EXISTING_DATA=true` in `compose.yaml`). Later accounts start empty.
- **Forgot password** works without email: creating an account shows a one-time **recovery code** (Copy /
  Download; you confirm you saved it). *Forgot password?* on the log-in screen takes the email, the code and a new
  password (typed twice), signs out other devices and gives a fresh code (each code works once). Only a scrypt hash
  of the code is stored; wrong codes and unknown emails get the same answer, and guesses are rate-limited.
  Accounts made before codes existed see a reminder to set one up (also in the account menu). Password boxes
  have a show/hide (eye) button, and new passwords are typed twice.
- Not built yet: password reset by email, email verification, two-factor login.

---

## Hosting (Railway + Vercel)

> **Live now: Vercel + Neon + Groq, all on free plans.** Website: https://steady-gray-eight.vercel.app.
> Backend: the `backend` folder as a second Vercel project (`backend/main.py`, `backend/vercel.json`), with
> `DATABASE_URL` (Neon, direct connection, not pooled), `MIGRATE_ON_START=true`, `AI_ENABLED=true`,
> `AI_PROVIDER=groq`, `GROQ_API_KEY` (from console.groq.com), `AI_DAILY_LIMIT_PER_USER=20`,
> `AI_TIMEOUT_SECONDS=45`, `AI_REQUESTS_PER_MINUTE=20`. Every push to `main` redeploys both projects.
> Hosted AI goes to Groq, which doesn't keep or train on API data; every AI button says so.

> **Free alternative: Render + Neon + Vercel ($0/month).** Database: create a free project on
> [Neon](https://neon.com) and copy its connection string. Backend: on [Render](https://render.com),
> *New → Blueprint*, pick this repo (it reads `render.yaml`), paste the Neon string as `DATABASE_URL`, apply.
> Then point `frontend/vercel.json` at the Render address (`https://<name>.onrender.com`) and deploy the
> frontend on Vercel as in step 2 below. Render's free plan sleeps after 15 idle minutes; the first visit then
> takes up to about a minute (the app shows "Waking up the server…" and retries by itself).

```
Browser ──HTTPS──▶ Vercel (React build) ──/api/* rewrite──▶ Railway: FastAPI ──private network──▶ Railway: PostgreSQL
```

The browser only talks to the Vercel address; Vercel forwards `/api` to the backend, so the session cookie stays
first-party and no CORS setup is needed. Costs (check their current pricing): Vercel's Hobby plan is free;
Railway's Hobby plan is about $5/month after the trial.

1. **Backend and database on Railway.** *New Project → Deploy from GitHub repo*, pick your fork, then in the
   service's *Settings* set **Root Directory** to `backend` (it builds `backend/Dockerfile`; `backend/railway.json`
   sets the health check). Add a database: *New → Database → PostgreSQL*. In the backend service's *Variables* add:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (Railway fills it in) |
   | `AI_ENABLED` | `false` (a hosted server has no local model; AI buttons are hidden) |
   | `SIGNUP_ENABLED` | `true`, or `false` to stop new sign-ups |

   Then *Settings → Networking → Generate Domain*. Check `https://<that-domain>/api/health` says `{"status":"ok"}`.
   On start the backend runs the migrations; nothing is ever wiped or reseeded.
2. **Frontend on Vercel.** In `frontend/vercel.json`, replace `YOUR-BACKEND.up.railway.app` with your Railway
   domain and commit. Then *Add New → Project*, import the repo and set **Root Directory** to `frontend`. Deploy.
3. **Open your Vercel address and create an account.**

To move your local data to the hosted app: locally, *Settings → Download export*; then, signed in on the hosted
app, *Settings → Import*. Back up the hosted database too (Railway's backups, or `pg_dump` with the connection
string from Railway).

---

## Prerequisites

You need a Docker runtime with Docker Compose. Ollama is only needed for the optional AI features.

### macOS (this is how this computer was set up)

```bash
brew install colima docker docker-compose ollama
```

[Colima](https://github.com/abiosoft/colima) is a free, open-source Docker runtime (no account needed).
**Docker Desktop also works**: install it instead of Colima and skip the Colima steps below.

Tell the Docker CLI where the Compose plugin is (one time; Homebrew prints this hint):

```bash
mkdir -p ~/.docker && echo '{ "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"] }' > ~/.docker/config.json
```

> If `~/.docker/config.json` already exists, add the `cliPluginsExtraDirs` line to it instead of replacing it.

Node.js is **not** required to run the app (the frontend is built inside Docker). You only need it for frontend
development and browser tests: `brew install node`.

### Windows / Linux

Install Docker Desktop (Windows/macOS) or Docker Engine + Compose plugin (Linux), and Ollama from
[ollama.com/download](https://ollama.com/download). On Linux, `host.docker.internal` is provided by the
`extra_hosts` line in `compose.yaml`; Ollama must listen on an address the Docker bridge can reach (see
[AI troubleshooting](#ai-troubleshooting)).

---

## First startup

```bash
colima start --cpu 2 --memory 3     # macOS with Colima: start the Docker runtime (skip with Docker Desktop)
docker compose up --build           # build and start database, backend and frontend
```

What happens:

1. PostgreSQL starts with a **named volume** (`steady_pgdata`) and reports healthy.
2. The backend waits until the database accepts connections, then runs `alembic upgrade head`.
   On an empty database this creates the tables; on an existing one it applies only new migrations.
   **Nothing is ever wiped or reseeded on startup.**
3. The backend becomes healthy, then the frontend (nginx) starts.

Then open the app and **create your account**. On your own computer the first account takes over any data from
before accounts existed.

No `.env` file is needed. To change ports, the database password or AI settings, copy `.env.example` to `.env`
and edit it (`.env` is ignored by Git).

### Optional: demo data

Demo data is never added automatically. To try the app with a few example records (all labelled `[demo]`),
create an account first, then:

```bash
docker compose exec backend python -m scripts.seed_demo you@example.com
```

It refuses to run if that account already contains any tasks, habits, (legacy) inbox items or journal entries, so demo
records can't be mixed into your own. To remove demo data later, start fresh with
[the reset command](#commands-that-can-delete-data), but only if the database holds nothing you want to keep.

---

## Opening the app

Open **http://127.0.0.1:5173** in your browser (or http://localhost:5173).

- On first use, a banner asks which **timezone** defines your calendar days (it suggests your device's timezone).
  You can change the timezone and the **first day of the week** any time in **Settings**.
- API documentation (useful while learning): http://127.0.0.1:8000/docs

---

## Routine startup and shutdown

```bash
colima start                 # macOS + Colima, after a reboot (Docker Desktop: just open it)
docker compose up -d         # start in the background (add --build after pulling code changes)
docker compose ps            # see what is running
docker compose logs -f backend
docker compose stop          # stop the containers; data is kept
docker compose down          # stop and remove containers; data is kept (the volume stays)
colima stop                  # optional: stop the Docker VM to free memory
```

For local AI, Ollama must be running: either `ollama serve` in a terminal, or `brew services start ollama`
to start it automatically at login.

---

## Where your data is stored

- **PostgreSQL is the only authoritative store.** All records live in the Docker named volume
  **`steady_pgdata`**, mounted at `/var/lib/postgresql/data` in the `db` container. With Colima, the volume lives
  inside Colima's virtual machine disk; with Docker Desktop, inside Docker Desktop's disk image.
- The volume survives `docker compose stop`, `docker compose down`, `docker compose up --build`, image rebuilds
  and computer restarts. This was verified: all record counts were identical after `down`, rebuild and `up`.
- PostgreSQL has **no published port**. Only the backend container can reach it.
- The browser keeps only small conveniences in local/session storage: the selected date and view, and a
  **journal draft** while a save is pending or has failed (removed once the server confirms the save).

> **Persistence is not a backup.** A volume protects against restarts, not against deleting the volume,
> resetting Colima/Docker Desktop, disk failure or losing the computer. Make regular backups (below) and keep
> copies somewhere else.

---

## Backup and restore

**Back up** (the stack must be running):

```bash
scripts/backup.sh
# → backups/steady-20261014-120502.dump   (PostgreSQL custom format; includes your journal)
```

Copy the `.dump` file somewhere safe (an external drive or encrypted cloud storage). `backups/` is ignored by Git.

**Restore** (this **replaces all current data** with the backup; you'll be asked to type `restore`):

```bash
scripts/restore.sh backups/steady-20261014-120502.dump
```

Both scripts were tested: a backup was taken, a record was added, the backup was restored, and every record
count matched the backup again.

Equivalent manual commands (what the scripts run):

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > my-backup.dump
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < my-backup.dump
```

---

## Export and import

In the app: **Settings → Export and import**.

- **Export** downloads one JSON file (`steady-export-YYYY-MM-DD.json`) with every record: tasks,
  dated plans and reviews, habits, schedule versions, pauses, check-ins, journal entries and the audit log.
  It contains your journal, so store it carefully. Export files are ignored by Git.
- **Import** first shows a **preview** (a dry run that writes nothing), then imports only after you confirm.

**Duplicate-handling policy for import**

| Situation | What happens |
| --- | --- |
| A record's `id` already exists | Skipped. Existing data is **never overwritten or deleted** by an import. |
| A journal entry for a date that already has an entry (different id) | Skipped and reported as a **conflict**. |
| A habit check-in for a habit + date that already has one | Skipped, reported as a conflict. |
| A task plan for a task + date that already exists | Skipped, reported as a conflict. |
| A record refers to something missing from both the file and the database | The **whole import is rejected**; nothing is written. |
| Unknown fields, wrong format/version, invalid values | Rejected by validation; nothing is written. |
| Settings in the file | Shown in the report, **not applied**. |

An import runs in a single transaction: it is applied completely or not at all.

API equivalents: `GET /api/data/export`, `POST /api/data/import?dry_run=true|false`.

---

## Local AI: setup, model choice and privacy

### Setup

```bash
brew install ollama          # macOS (other systems: https://ollama.com/download)
ollama serve                 # or: brew services start ollama (starts at login)
ollama pull phi4-mini        # one-time download, about 2.5 GB; needs internet
```

After the download, **AI works offline**: inference runs entirely on this computer and no internet is needed.
Open **Settings → Local AI** and press *Check again*; it should say *Local AI ready*.

Configuration lives in backend environment variables (see `.env.example`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | How the backend container reaches Ollama on the host |
| `OLLAMA_MODEL` | `phi4-mini` | Any Ollama model name |
| `AI_TIMEOUT_SECONDS` | `120` | Per-request timeout |
| `AI_MAX_OUTPUT_TOKENS` | `700` | Upper bound on reply length |
| `AI_MAX_RETRIES` | `1` | Retries after an invalid answer (bounded) |
| `AI_REQUESTS_PER_MINUTE` | `6` | Rate limit; also only one AI request runs at a time |

There is no API key: no paid service, subscription or external account is used.

### Why `phi4-mini`

This computer has an Apple M5 with 16 GB of unified memory. A 3–4B-parameter model fits comfortably next to the
browser and the Docker VM (3 GB). `phi4-mini` was chosen because:

- **Size and resources:** 3.8B parameters, 4-bit quantised (Q4_K_M), **about 2.5 GB download**. It uses roughly
  **3.5–4 GB of RAM while loaded**, and Ollama unloads it after 10 minutes idle. On this Mac, replies take about
  1.5–10 s (up to ~18 s when a retry is needed).
- **Licence:** MIT, so personal use (and more) is clearly permitted.
- **Fit:** it is instruction-tuned and follows JSON schemas well. Ollama also constrains its output to the
  schema the backend sends.

Alternatives considered: `llama3.2:3b` (2.0 GB, Llama Community Licence, faster but weaker at following
instructions) and `gemma3:4b` (3.3 GB, Gemma Terms of Use, heavier). Change `OLLAMA_MODEL` to try another.
If you have 8 GB of RAM or less, use a smaller model such as `llama3.2:3b` or `qwen2.5:1.5b`.

### What the AI can do (and nothing else)

| Feature | Where | What is sent to the model |
| --- | --- | --- |
| Break a task into steps | ⋯ menu on a task (in a day or in the Inbox panel) | That task's title, description and estimate |
| Suggest a daily plan | To-Do → *Suggest a plan (AI)* | Title, priority, deadline and estimate of the tasks you tick (max 25) |
| Summarise non-completion reasons | To-Do → Planning insights | Date, task title, tag and your written reason (first 160 characters) of tasks marked not completed (max 60) |
| Suggest habit adjustments | Habit Tracker → Consistency insights | Habit names, schedules and the app's calculated numbers |
| Journal prompts | Journal → *Suggest prompts* | **No journal content at all** |
| Summarise journal entries | Journal → *Summarise entries* | Only the entries you tick, after a preview of exactly what will be shared and a confirmation checkbox |
| Money saving tips | Money → Insights → *Get saving tips with local AI* | Monthly totals, category totals (average, this month, usual by today), repeating bill names and amounts, Splitwise totals. **No entry notes, account names or balances.** The app checks every number the model writes against these figures, calculates each saving itself, never lets it suggest cutting rent or health care by more than 10%, and rejects investing, borrowing, insurance or tax advice |

### Safety and privacy behaviour

- **Proposals only.** Every AI result is labelled *Suggestion from local AI*. Creating, moving or changing records
  happens only when you press an accept button, and goes through the normal non-AI endpoints.
- **Deterministic logic stays in code.** Percentages, streaks, dates, record selection and the **time-budget
  check** are calculated by the app. For daily plans the app walks the AI's order and removes tasks that don't
  fit; if the AI overshoots, it is first asked once to try again.
- **Validation.** Replies must match a JSON schema. Every record reference (T1, R2, H3, dates) must be one that
  was supplied, and every number in an observation must appear in the supplied data. Diagnostic or judgmental
  wording (e.g. "depression", "lazy") is rejected. Habits below 60% consistency never get "do more" suggestions.
  Invalid replies are retried once with feedback, then rejected with a clear message. Nothing is invented to
  fill the gap.
- **Grounding.** Observations show the records they are based on (dates, titles, numbers), and are kept separate
  from suggestions.
- **Never automatic.** No AI call happens on page load, on save, or in the background. Journal text is never sent
  unless you select entries and confirm.
- **Logs** record only the feature name, attempt number, outcome and duration: never prompts, replies,
  titles or journal text. No API keys exist.
- **Limits:** a rate limit (6 per minute by default), one request at a time, a bounded output length, a timeout,
  and at most one retry.
- **When AI is unavailable** (Ollama stopped, model missing, timeout), AI buttons show *Local AI unavailable*
  with the setup steps above. All other features work normally. This was tested by pointing the backend at an
  unreachable address.
- Mock output is never shown as AI output: the canned replies used in automated tests live in
  `backend/tests/fixtures/` and are clearly labelled as test fixtures.

How the model was evaluated, and what it gets wrong: [docs/AI_EVALUATION.md](docs/AI_EVALUATION.md).

### AI troubleshooting

- *"Ollama isn't reachable"*: run `ollama serve` (or `brew services start ollama`), then *Check again*.
- *"model isn't installed"*: `ollama pull phi4-mini` (or whatever `OLLAMA_MODEL` says).
- *Linux*: Ollama listens on `127.0.0.1` by default, which containers can't reach. Start it with
  `OLLAMA_HOST=172.17.0.1:11434 ollama serve` (the Docker bridge address) so it stays private to this machine.
  **Don't use `0.0.0.0` on a laptop that joins public networks.**
- Ollama is accessible only locally by default. Keep it that way: the app doesn't need it exposed.

---

## Commands that can delete data

| Command | Effect |
| --- | --- |
| `docker compose down -v` | ⚠️ **Deletes the `steady_pgdata` volume: all your data.** (`-v` = remove volumes.) |
| `docker volume rm steady_pgdata` / `docker volume prune` / `docker system prune --volumes` | ⚠️ Deletes the data volume (`prune` deletes every unused volume). |
| `colima delete` | ⚠️ Deletes Colima's VM, including **all** Docker volumes in it. |
| Docker Desktop → *Troubleshoot → Clean / Purge data* or *Reset to factory defaults* | ⚠️ Deletes all volumes. |
| `scripts/restore.sh <file>` | ⚠️ Replaces all current data with the backup (asks for confirmation). |
| **Delete task** (⋯ menu in the app) | ⚠️ Permanently removes that task and its records on every day (asks for confirmation). Use *Cancel task* to keep the record instead. |
| `alembic downgrade …` | ⚠️ The initial migration's downgrade drops every table. It is never run automatically. |

Safe: `docker compose stop`, `docker compose down` (without `-v`), `docker compose up --build`, `colima stop`, restarting the computer.

The browser tests use a **separate** stack named `steady-e2e` with its own volume (`steady-e2e_pgdata`).
`docker compose -p steady-e2e down -v` deletes only that test data.

---

## How the data model and daily history work

Full details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). In short:

**A task is stored separately from its dated plans.** `tasks` holds what needs doing (title, priority, estimate,
deadline…). `task_plans` holds one row per day the task was planned for, with that day's **outcome**
(`completed`, `not_completed`, `cancelled`, or empty = **not marked yet**; `partial` exists only in older history),
the written reason (required for not completed) and an optional tag, the optional time or time range (`planned_time`, `planned_end_time`), and the real `completed_at` instant.

**Carrying forward never rewrites the past.** Example:

| Day | Row in `task_plans` |
| --- | --- |
| Monday | "Update resume": outcome **not_completed**, reason **Not enough time**, follow-up *rescheduled* |
| Tuesday | same task, `carried_from` → Monday's row, outcome **completed**, `completed_at` = the real time you ticked it |

Monday stays unfinished; Tuesday records the completion. Rules:

- Rescheduling a plan that is **in the past or already reviewed** keeps it and adds a new, linked row.
  Rescheduling a plan for **today or later that has no outcome yet** just moves it (the day hasn't finished),
  and the move is recorded in the audit log.
- **"Not marked yet" ≠ "not completed".** A past day with no outcome shows *Not marked yet* and still counts in
  that day's total, so unfinished work is never silently dropped from a past denominator.
- Marking a task *Not completed* depends on where the task was created:
  - **captured in the Inbox** (then planned on a day) → it goes back to the **Inbox**, marked, until you plan it again;
  - **created directly on a day** → it stays on that day and the row asks *What should happen to it?*:
    **Move to tomorrow**, **Move to Inbox** or **Leave it here**. Nothing is moved without your choice.
- **Corrections** to a past outcome are allowed and written to an append-only **audit log** (before/after,
  optional note). Archived tasks and past reviews are kept.
- **Cancellation** is tracked separately: a cancelled plan is shown with a "not counted" label and excluded
  from that day's completion percentage. *Restore* undoes a cancellation: a task cancelled from a day goes back to
  that same day (and time), ready to mark; one cancelled from the Inbox goes back to the Inbox. The undo is audited.
- **Delete** is the only way records disappear: it permanently removes one task and all its day records,
  after a confirmation. Smaller tasks split from it are kept.

**Completion calculation (To-Do):**
`completion % = completed ÷ (planned − cancelled)`, rounded half-up to a whole number.
Not completed and not-yet-marked plans stay in the denominator. A day with no plans shows
**"No tasks planned."** (no percentage). *Planned effort* is optional: completed estimated minutes ÷ planned
estimated minutes, ignoring tasks without estimates (their count is shown).

**Habits** keep **versioned schedules** (each change applies from a chosen date, so past days are judged by the
schedule they had), **pauses**, and **one check-in per habit per day** (a database constraint plus "set value"
requests, so repeated clicks can't double-count). Unscheduled and paused days are never failures. Weekly-target
habits are judged per week, never as daily misses. Habit metrics are never combined with task metrics.

**Money:** amounts are stored as whole cents. Balances are never stored; they're calculated as the opening balance
(entered at setup, as of that day) plus every entry: spending lowers a debit account or raises what a card owes, money in
raises a debit account, and a card payment lowers both the debit account and the card's balance. Entries can't be dated
before their account was set up (the opening balance already covers earlier spending) or in the future.

**Repeating entries:** each rule remembers how many of its dates have been added. Whenever the Money tab loads, any
date that has come due (today or earlier) is added as an ordinary entry, linked to its rule; the rule rows are locked
while this happens and each rule can add only one entry per day, so it can't double-post. Missed dates are filled in
(if the app wasn't opened for two months, both bills appear). A monthly rule on the 31st lands on the last day of
shorter months. Deleting an added entry doesn't bring it back. Editing a rule changes future entries only; changing
its schedule or date restarts it from the new date (today or later). **Pause** skips dates until you resume (they're
not filled in later). **Stop** deletes the rule but keeps every entry it already added.

**Splitwise:** only the two totals are stored (one row), copied by hand from the Splitwise app; they don't change any
account balance or your spending figures. Net = money available − owed on cards + Splitwise *get* − Splitwise *pay*.

**Time:** instants are stored in UTC. "Which day is it?" always uses the timezone in Settings, and day arithmetic
uses calendar dates, so 23- and 25-hour daylight-saving days are handled correctly.

---

## Development and tests

```bash
# Backend tests (123): run inside Docker against a separate "<db>_test" database
docker compose --profile test run --rm backend-test

# Frontend type check and production build
cd frontend && npm ci && npm run typecheck && npm run build

# Browser tests (Playwright) against the separate steady-e2e stack, never your data
FRONTEND_PORT=5174 BACKEND_PORT=8001 docker compose -p steady-e2e up -d --build --wait
cd frontend && npx playwright install chromium && npm run test:e2e

# Frontend dev server with hot reload (proxies /api to the backend on :8000)
cd frontend && npm run dev

# Evaluate the local model (uses the steady-e2e stack; needs a local Python environment once)
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements-dev.txt
backend/.venv/bin/python backend/scripts/evaluate_ai.py --runs 3
```

What the backend tests cover: carry-forward preserving earlier outcomes; completion maths and empty days;
missing reviews versus explicit non-completion; corrections and the audit trail; cancellations; habit schedules,
pauses, weekly targets (including partial weeks), schedule changes and duplicate check-ins; timezone, DST and
week-start boundaries; duplicate and simultaneous submissions (4 identical requests → 1 task); the migration that turned old Inbox items into tasks; journal
saving, versions and conflicts; export/import round trip and duplicate policy; that the migrations match the
models; and AI validation, grounding, privacy of prompts and logs, retries, rate limits and provider failures.

Browser tests (24, after a sign-in step; some also at phone size) cover: rapid Inbox capture and *Move to date* (desktop and phone sizes), that there is no separate Inbox tab, dragging from the permanent Inbox panel onto a day, planning a task for a from–to time range (and adding or clearing one later via Edit), dragging anytime tasks onto the timeline, within it and back, creating tasks by clicking or dragging on the timeline, night-owl timeline hours past midnight, marking *Not completed* (reason required) and carrying a task forward with its time, Inbox tasks returning to the Inbox while day tasks ask what to do, that a cancelled task only offers *Restore* (which puts it back on the same day), deleting with confirmation, habit check-in, journal autosave, reload and conflict, first-time Money setup with debit and credit balances moving the right way, a monthly bill added on its day and kept after stopping, Splitwise totals counting towards net, money insights, two accounts seeing only their own tasks plus log out / wrong password / log in, every section fitting a phone screen with the tab bar at the bottom, and an AI daily plan that stays a
proposal until accepted (skipped automatically if Ollama isn't running).

---

## Known limitations

- **Accounts**: no password reset by email, no email verification and no two-factor login yet. Sign-up is open
  unless `SIGNUP_ENABLED=false`. Login rate limits are kept in memory, so they reset when the backend restarts.
- **AI on a hosted server** uses Groq's free tier (`AI_PROVIDER=groq`): its daily allowance is shared by everyone
  on the server, so each person gets `AI_DAILY_LIMIT_PER_USER` requests a day. On your own computer the AI runs
  locally with Ollama instead and nothing leaves the computer.
- **Money** tracks spending and balances you enter; it doesn't connect to banks, has no budgets yet. The AI sees money figures only when you press
  its button, and then only totals (no notes, account names or balances). Importing an export into a *different* database duplicates the starter
  money categories (they're created per database).
- **AI quality is limited by a 3.8B model** (details in [docs/AI_EVALUATION.md](docs/AI_EVALUATION.md)). It can
  cite only some of the records behind a count, and its habit suggestions are sometimes generic or slightly
  off ("reduce to 7 days a week" for a daily habit). Validation blocks invented records, numbers and diagnostic
  language, but cannot guarantee that every suggestion is wise. Treat them as ideas.
- **Weekly-target habits in partial weeks** (start, pause or archive mid-week) use a scaled target:
  `ceil(target × available days ÷ 7)`. A week that contains a schedule change uses the last version in that week.
- **Streaks** stop where a habit's schedule *type* changes (e.g. daily → weekly target).
- **Drag-and-drop** uses the browser's native drag events, which don't work on most touch screens. On phones,
  use **Move to date** / **Time** (available on every task). Timeline tasks are listed in their start slot; a long
  range shows its end time rather than stretching across hours, and overlapping tasks are simply listed together.
- **Journal conflicts** compare whole entries (all fields). There is no line-by-line merge; you choose which
  version to keep, and can copy your text.
- **Changing the timezone** changes which day "today" is from then on. Existing dated records keep their dates.
- The frontend is served as a production build in Docker. Code changes need `docker compose up --build`
  (or use `npm run dev` while developing).
- Not verified on Windows or Linux, or with Docker Desktop: only on macOS with Colima.
- One browser test (*calendar: click or drag on the timeline…*) has occasionally timed out when the whole suite runs
  (about 3 times in 25+ runs); it passes consistently on its own. The cause hasn't been pinned down yet.
- No offline mode for the web app itself: the browser needs the local backend running.

---

## Project layout

```
LICENSE                 MIT
compose.yaml            db + backend + frontend (+ backend-test profile)
.env.example            optional settings (placeholders only)
scripts/                backup.sh, restore.sh
backend/
  app/
    main.py             FastAPI app
    models.py           SQLAlchemy tables (data model)
    schemas.py          request/response validation (Pydantic)
    db.py               restricted role + signed-in user per transaction (row-level security)
    services/           auth, tasks (history rules), habits, journal, insights, finance, transfer
    routers/            HTTP endpoints
    ai/                 provider interface, Ollama adapter, runner (limits/retries), features
  alembic/versions/     migrations (0010: accounts and row-level security)
  railway.json          Railway build and health check
render.yaml             Render Blueprint (free backend)
  scripts/              start.sh, wait_for_db.py, seed_demo.py, evaluate_ai.py
  tests/                pytest suite (+ fixtures/ai_fixtures.py: labelled test-only AI replies)
frontend/
  src/                  React app (features/todo incl. the Inbox panel, habits, journal, ai, settings)
  e2e/                  Playwright browser tests
  nginx.conf, Dockerfile  local Docker serving
  vercel.json           Vercel build, /api rewrite to the backend, security headers
docs/                   ARCHITECTURE.md, AI_EVALUATION.md, AI_EVALUATION_RESULTS.md
.claude/launch.json     dev-server preset used while building (Vite on :5175 against the test stack)
```
