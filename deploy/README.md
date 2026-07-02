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

## Sua loi PostgreSQL sai mat khau

Neu log co dong `password authentication failed for user "postgres"`, thuong la `.env`
va mat khau dang luu trong volume PostgreSQL bi lech nhau. Chay lenh nay de dat lai
mat khau trong database theo gia tri `POSTGRES_PASSWORD` hien tai trong `.env`:

```bash
cd /opt/quanlynhansu
sudo bash deploy/repair_postgres_password.sh
```

Lenh nay khong xoa volume va khong mat du lieu.

## Sua loi login bi 500

Neu trang `/login/` mo duoc nhung bam dang nhap la loi `500 Internal Server Error`,
thuong la database tren server chua chay het migration. Chay:

```bash
cd /opt/quanlynhansu
sudo bash deploy/repair_login_500.sh
```

Script se migrate database, restart web, va test POST `/login/`. Neu van loi, xem log:

```bash
cd /opt/quanlynhansu
sudo docker compose logs --tail=200 web
```
