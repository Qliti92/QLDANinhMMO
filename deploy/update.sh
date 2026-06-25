#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/quanlynhansu}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo -E bash deploy/update.sh"
  exit 1
fi

cd "$APP_DIR"
git pull --ff-only
docker compose up -d --build
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py collectstatic --noinput
docker compose restart web

echo "Updated."
