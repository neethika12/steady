#!/bin/sh
# Back up the Steady database to ./backups/steady-<date-time>.dump (custom pg_dump format).
# The stack must be running. Backups contain your journal: store them somewhere safe.
set -e
cd "$(dirname "$0")/.."
mkdir -p backups
file="backups/steady-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$file"
echo "Backup written to $file ($(du -h "$file" | cut -f1))"
