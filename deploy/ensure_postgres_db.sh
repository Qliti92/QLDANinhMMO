#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/quanlynhansu}"

cd "$APP_DIR"

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

POSTGRES_DB="${POSTGRES_DB:-workflow}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"

docker compose up -d db

for attempt in $(seq 1 30); do
  if docker compose exec -T db pg_isready -U "$POSTGRES_USER" -d postgres >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "PostgreSQL is not ready after 30 seconds."
    exit 1
  fi
  sleep 1
done

docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -v db="$POSTGRES_DB" <<'SQL'
SELECT format('CREATE DATABASE %I', :'db')
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = :'db'
)\gexec
SQL
