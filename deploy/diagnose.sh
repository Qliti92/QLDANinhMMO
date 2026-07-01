#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/quanlynhansu}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo -E bash deploy/diagnose.sh"
  exit 1
fi

cd "$APP_DIR"

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

echo "== time =="
date -Is

echo
echo "== git =="
git rev-parse --short HEAD || true
git status --short || true

echo
echo "== docker compose ps =="
docker compose ps

echo
echo "== web health endpoint =="
curl -fsS -I --max-time 10 http://127.0.0.1:8000/login/ || true

echo
echo "== django check =="
docker compose exec -T web python manage.py check || true

echo
echo "== migrations =="
docker compose exec -T web python manage.py showmigrations workflow | tail -n 30 || true

echo
echo "== database ready =="
docker compose exec -T db pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-workflow}" || true

echo
echo "== recent web logs =="
docker compose logs --tail=200 web

echo
echo "== recent db logs =="
docker compose logs --tail=120 db

echo
echo "== nginx errors =="
tail -n 120 /var/log/nginx/error.log || true
