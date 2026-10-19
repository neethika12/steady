#!/bin/sh
# Restore a backup made by scripts/backup.sh.
# WARNING: this REPLACES everything currently in the Steady database with the backup.
# Usage: scripts/restore.sh backups/steady-YYYYMMDD-HHMMSS.dump
set -e
cd "$(dirname "$0")/.."
[ -f "$1" ] || { echo "Usage: $0 <backup file>"; exit 1; }
printf "This replaces ALL current Steady data with %s. Type 'restore' to continue: " "$1"
read answer
[ "$answer" = "restore" ] || { echo "Cancelled."; exit 1; }
docker compose stop backend frontend
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$1"
docker compose start backend frontend
echo "Restored from $1"
