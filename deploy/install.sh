#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-manager.phulinhmedia.com}"
APP_DIR="${APP_DIR:-/opt/quanlynhansu}"
REPO_URL="${REPO_URL:-}"
EMAIL="${EMAIL:-admin@${DOMAIN}}"

if [ -z "$REPO_URL" ]; then
  echo "Missing REPO_URL."
  echo "Usage: REPO_URL=https://github.com/your/repo.git DOMAIN=${DOMAIN} bash deploy/install.sh"
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo -E bash deploy/install.sh"
  exit 1
fi

apt-get update
apt-get install -y git nginx certbot python3-certbot-nginx ca-certificates curl gnupg

if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

systemctl enable --now docker

if [ ! -d "$APP_DIR/.git" ]; then
  mkdir -p "$(dirname "$APP_DIR")"
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git pull --ff-only || true

if [ ! -f .env ]; then
  SECRET_KEY="$(openssl rand -base64 48 | tr -d '\n')"
  cat > .env <<ENV
DJANGO_SECRET_KEY=${SECRET_KEY}
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=${DOMAIN},localhost,127.0.0.1
DATABASE_URL=postgresql://postgres:postgres@db:5432/workflow
CSRF_TRUSTED_ORIGINS=https://${DOMAIN}
DJANGO_SECURE_SSL_REDIRECT=false
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false
DJANGO_SECURE_HSTS_PRELOAD=false
ENV
fi

docker compose up -d --build
docker compose exec -T web python manage.py migrate

cat > "/etc/nginx/sites-available/${DOMAIN}" <<NGINX
server {
    server_name ${DOMAIN};

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX

ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
nginx -t
systemctl reload nginx

certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect || {
  echo "Certbot failed. App should still be available via HTTP if DNS/firewall are correct."
}

echo "Installed."
echo "Open: https://${DOMAIN}"
echo "Create admin user with:"
echo "cd ${APP_DIR} && docker compose exec web python manage.py createsuperuser"
