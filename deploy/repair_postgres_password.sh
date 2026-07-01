#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/quanlynhansu}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo -E bash deploy/repair_postgres_password.sh"
  exit 1
fi

cd "$APP_DIR"

if [ ! -f .env ]; then
  echo "Missing .env in $APP_DIR"
  exit 1
fi

set -a
. ./.env
set +a

POSTGRES_DB="${POSTGRES_DB:-workflow}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"

if [ -z "$POSTGRES_PASSWORD" ]; then
  echo "POSTGRES_PASSWORD is empty in .env"
  exit 1
fi

bash deploy/ensure_postgres_db.sh

SQL_PASSWORD="${POSTGRES_PASSWORD//\'/\'\'}"
SQL_USER="${POSTGRES_USER//\"/\"\"}"

docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "ALTER USER \"${SQL_USER}\" WITH PASSWORD '${SQL_PASSWORD}';"

docker compose up -d --build web
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py collectstatic --noinput
docker compose restart web

echo "PostgreSQL password repaired for user ${POSTGRES_USER}."
