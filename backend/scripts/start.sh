#!/bin/sh
# Container start: wait for PostgreSQL, apply migrations, then serve the API.
# Migrations only ever move the schema forward; nothing is wiped or reseeded.
set -e
python -m scripts.wait_for_db
alembic upgrade head
# PORT is set by hosts such as Railway; 8000 locally.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
