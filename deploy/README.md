# Deploy nhanh

## Cai lan dau tren server Linux

```bash
sudo apt update
sudo apt install -y git
git clone <repo-url> /tmp/quanlynhansu
cd /tmp/quanlynhansu
sudo REPO_URL=<repo-url> DOMAIN=manager.phulinhmedia.com bash deploy/install.sh
```

Tao tai khoan admin:

```bash
cd /opt/quanlynhansu
sudo docker compose exec web python manage.py createsuperuser
```

## Update sau nay

```bash
cd /opt/quanlynhansu
sudo bash deploy/update.sh
```

Co the doi duong dan:

```bash
sudo APP_DIR=/opt/quanlynhansu bash deploy/update.sh
```
