#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/quanlynhansu}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo -E bash deploy/repair_login_500.sh"
  exit 1
fi

cd "$APP_DIR"

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

POSTGRES_DB="${POSTGRES_DB:-workflow}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"

echo "== ensure database exists and containers are running =="
docker compose up -d db
bash deploy/ensure_postgres_db.sh
docker compose up -d --build web

echo
echo "== apply migrations =="
docker compose exec -T web python manage.py migrate --noinput

echo
echo "== applied workflow migrations =="
docker compose exec -T web python manage.py showmigrations workflow

echo
echo "== workflow_user columns =="
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'workflow_user'
ORDER BY ordinal_position;
"

echo
echo "== collect static and restart web =="
docker compose exec -T web python manage.py collectstatic --noinput
docker compose restart web

echo
echo "== login post smoke test =="
docker compose exec -T web python manage.py shell -c "
from django.test import Client
c = Client(HTTP_HOST='manager.phulinhmedia.com')
r = c.get('/login/')
print('GET /login/', r.status_code)
r = c.post('/login/', {'username': 'codex_invalid_user', 'password': 'invalid_password'})
print('POST /login/ invalid credentials', r.status_code)
if r.status_code >= 500:
    raise SystemExit('Login POST still returns server error')
"

echo
echo "Done. If the smoke test prints POST /login/ invalid credentials 200, login 500 is repaired."
