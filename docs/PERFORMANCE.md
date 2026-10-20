# Performance measurements

Measured on 2026-10-20 against the separate `steady-e2e` test stack (never real data), signed in as the
test account. Hardware: Apple M5 Mac, Docker in a Colima VM limited to **2 vCPUs and 3 GB RAM**.
The backend runs **one Uvicorn worker**; requests go through nginx, as in normal use.
Tool: ApacheBench 2.3 with keep-alive (`ab -k`). Numbers will differ on other hardware and on Railway.

## Throughput and latency

| Endpoint (authenticated unless noted) | Concurrency | Requests | Req/s | p50 | p95 | p99 | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /api/health` (no auth, no DB) | 50 | 5,000 | 553 | 86 ms | 136 ms | 228 ms | 0 |
| `GET /api/auth/session` | 50 | 3,000 | 433 | 110 ms | 191 ms | 236 ms | 0 |
| `GET /api/tasks?view=inbox` | 1 | 1,000 | 289 | 3 ms | 4 ms | 7 ms | 0 |
| `GET /api/tasks?view=inbox` | 10 | 3,000 | 276 | 33 ms | 60 ms | 74 ms | 0 |
| `GET /api/tasks?view=inbox` | 50 | 3,000 | 291 | 162 ms | 286 ms | 356 ms | 0 |
| `GET /api/plans/day` | 10 | 3,000 | 299 | 31 ms | 53 ms | 67 ms | 0 |
| `GET /api/plans/week` | 10 | 2,000 | 154 | 61 ms | 95 ms | 113 ms | 0 |
| `GET /api/habits/day` | 10 | 3,000 | 174 | 54 ms | 85 ms | 98 ms | 0 |
| `GET /api/finance/overview` | 10 | 3,000 | 225 | 40 ms | 72 ms | 100 ms | 0 |
| `GET /api/finance/day` | 10 | 3,000 | 247 | 38 ms | 62 ms | 76 ms | 0 |
| `POST /api/tasks` (write) | 10 | 1,000 | 263 | 35 ms | 60 ms | 71 ms | 0 |

**Sustained mixed load:** four endpoints (inbox, day plan, money overview, habits) at the same time,
8 connections each (32 total) for 60 seconds: **9,443 requests (about 157 req/s combined), 0 errors**,
p95 between 293 and 339 ms.

**Total: 39,443 requests across all runs, 0 failed.** Every request passes the session check and
row-level security.

Resource use when idle afterwards: backend about 96 MB RAM, PostgreSQL about 35 MB, nginx about 6 MB.

## Deployment and recovery time

| Step | Time |
| --- | --- |
| Cold build, no cache (backend and frontend images) | 28.4 s |
| Rebuild after a code change (dependencies cached) | 5.3 s |
| Recreate containers after that rebuild, until healthy | 7.2 s |
| Start the stopped stack (database, backend, frontend) until healthy | 10.0 s |
| Restart the backend until healthy | 6.2 s |
| All 11 database migrations on an empty database | 0.92 s |

On Railway, `backend/railway.json` adds a health check on `/api/health` and restarts the backend on
failure (up to 5 times). Real hosted deploy times will be added once it's deployed.

## Size

| | |
| --- | --- |
| Frontend build stage (Node and dependencies) | 462 MB |
| Frontend image that's actually served (nginx and the built files) | 92.8 MB, 80% smaller |
| App download (JavaScript and CSS) | 449 KB raw, about 123 KB gzipped |
| Backend image | 344 MB |

## Local AI usage (phi4-mini via Ollama)

Tokens per use, as reported by Ollama (second run of each, so the model was already loaded):

| Feature | Input tokens | Output tokens | Time |
| --- | --- | --- | --- |
| Break down a task | 199 | 55 | 2.9 s |
| Daily plan | 953 | 104 | 5.2 s |
| Habit review | 1,182 | 343 | 19.0 s |
| Journal prompts | 163 | 55 | 3.5 s |
| Money saving tips | 1,125 | 301 | 15–20 s (5 runs on 2026-10-18) |
| **One use of each** | **3,622** | **858** | |

These run on the computer itself, so there's no per-request API charge and the data never leaves it.
The first run after the model loads is slower (for example 22 s instead of 5 s for a daily plan).
Timings taken while the Mac was asleep were thrown away.

## Not measured yet

- **Availability (uptime %)**: needs the hosted app and a monitor running over weeks.
- **Hosted throughput and deploy times on Railway/Vercel**: to be measured after deployment.
