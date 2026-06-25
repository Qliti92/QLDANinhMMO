# Project Workflow Management System

Web-based workflow management system for MMO teams, built with Django 5, PostgreSQL, Bootstrap 5, HTMX-ready templates, and service-layer business logic.

## Implemented Scope

- Role-based access for Admin, Manager, and Staff.
- Project CRUD with search, filters, pagination, soft delete, and database indexes.
- Excel `.xlsx` import with duplicate detection against database and inside the uploaded file.
- Import history, import summary, duplicate table, invalid table, and duplicate report Excel export.
- Bulk actions: assign employee, mark profit/loss, change status, delete.
- Assignment history and current assignee tracking.
- Activity logs with metadata and IP address support.
- Dashboard, KPI page, reports, charts, export Excel, and basic JSON API endpoints.
- Admin user management page for creating and editing application users.
- Docker, seed data command, and unit tests for core workflow rules.

## Business Rules

- Staff can only see projects currently assigned to them.
- Admin and Manager can manage projects, import Excel, assign projects, export, view KPI/reports/logs.
- Admin can also use Django admin and manage users.
- Current employee is stored on the project and updated from the latest assignment action.
- Assigning a project updates status to `ASSIGNED`.
- Staff can update assigned projects with status/note only.
- Only Admin and Manager can update result to `PROFIT` or `LOSS`.
- Deletes are soft deletes using `deleted_at`.

## Local Setup

```bash
cp .env.example .env
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Demo accounts created by `seed_demo`:

- `admin` / `admin123`
- `manager` / `manager123`
- `staff` / `staff123`

## Docker Setup

```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
```

Open `http://localhost:8000`.

## Deploy nhanh lên Linux

Xem chi tiết trong `deploy/README.md`.

Cài lần đầu:

```bash
sudo apt update
sudo apt install -y git
git clone <repo-url> /tmp/quanlynhansu
cd /tmp/quanlynhansu
sudo REPO_URL=<repo-url> DOMAIN=manager.phulinhmedia.com bash deploy/install.sh
```

Update sau này:

```bash
cd /opt/quanlynhansu
sudo bash deploy/update.sh
```

## Excel Import Format

Only `.xlsx` is accepted. Required column:

- `Link`

`Tên dự án` is optional. When it is missing, the system generates the project name from the link. Empty rows are skipped. Rows missing link are counted as invalid. Duplicate links are not imported.

## API Endpoints

- `GET /api/projects/`
- `POST /api/projects/<id>/status/`
- `POST /api/projects/<id>/result/`

The API currently uses Django session authentication and CSRF protection. It is intentionally simple so token authentication can be added later for mobile clients.

## Tests

```bash
python manage.py test
```
