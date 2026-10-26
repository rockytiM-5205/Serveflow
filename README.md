# ServeFlow

Multi-tenant restaurant-ordering platform built around a reusable REST API
(Django, Django REST Framework, PostgreSQL).

**Status:** repository foundation only. There are no models, endpoints or
frontend yet. See [docs/foundation-decisions.md](docs/foundation-decisions.md).

## Prerequisites

- Python 3.12 or newer
- PostgreSQL 14 or newer, with `psql` on your PATH
- Git

## Setup

Run these from the repository root. Commands are PowerShell (Windows) with the
Unix alternative where it differs.

### 1. Virtual environment

```powershell
# Windows (PowerShell)
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
# If activation is blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

```bash
# macOS / Linux
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r backend\requirements\development.txt
```

```bash
pip install -r backend/requirements/development.txt
```

### 3. Environment configuration

```powershell
Copy-Item .env.example .env        # Windows
```

```bash
cp .env.example .env               # macOS / Linux
```

Edit `.env`: set `DJANGO_SECRET_KEY` (generate one with
`python -c "import secrets; print(secrets.token_urlsafe(64))"`) and the
`POSTGRES_*` values. `.env` is git-ignored; never commit it.

### 4. PostgreSQL

Connect as a superuser (`psql -U postgres`; on Windows you can use "SQL Shell
(psql)" from the PostgreSQL install) and run:

```sql
CREATE ROLE serveflow WITH LOGIN PASSWORD 'choose-a-password' CREATEDB;
CREATE DATABASE serveflow OWNER serveflow;
```

Use the same values in `.env`. `CREATEDB` lets pytest create `test_serveflow`.
There is no SQLite fallback: if the variables are missing, startup fails and
names the missing one.

Verify connectivity:

```bash
psql -h localhost -U serveflow -d serveflow -c "select 1"
```

| Symptom | Fix |
|---|---|
| `Missing required environment variable ...` | Set it in `.env` |
| `connection refused` | Start PostgreSQL; check `POSTGRES_HOST` / `POSTGRES_PORT` |
| `password authentication failed` | Check `POSTGRES_USER` / `POSTGRES_PASSWORD` |
| `permission denied to create database` | `ALTER ROLE serveflow CREATEDB;` |

## Checks and tests

Run from `backend/`:

```bash
python manage.py check
pytest
```

> **Current status:** the models, the auth/tenant API, the menu API and the orders API exist, but their migrations
> have not been generated (each needs review first). Generate and review them (see
> below), then `python manage.py check` and `pytest`. CI fails until migrations are
> committed (`makemigrations --check`). Endpoints are listed in [docs/api.md](docs/api.md).

## Migration sequence

1. Implement `accounts.User`, then `python manage.py makemigrations accounts`.
   Review and commit `0001_initial.py`.
2. Only then run `python manage.py migrate` for the first time. Never migrate
   before the accounts migration exists.
3. `makemigrations restaurants`, review.
4. `makemigrations menu`, then **copy** `docs/migrations/menu_0002_composite_category_fk.py` to
   `backend/apps/menu/migrations/0002_composite_category_fk.py` (drop the `menu_` prefix). It is a hand-written
   migration that adds the same-restaurant foreign key Django cannot generate, and it needs `0001_initial` to exist
   first, which is why it is not already in place. Then `makemigrations audit`. Review all of them.
   A test fails if the copy step is skipped.
5. Orders point at menu items, so keep this order: `makemigrations menu` (it adds a small constraint migration,
   `0003`), then `makemigrations orders`, then **copy** `docs/migrations/orders_0002_composite_fks.py` to
   `backend/apps/orders/migrations/0002_composite_fks.py` (drop the `orders_` prefix). It adds the same-restaurant foreign
   keys Django cannot generate. A test fails if the copy step is skipped. Then `migrate`.
6. Optionally schedule `python manage.py purge_idempotency` (daily) to delete stored retry answers older than 48 hours.

## Layout

```
.env.example
.gitignore
README.md
docs/
frontend/          HTML/CSS/vanilla JS (see frontend/README.md)
backend/
  manage.py
  pytest.ini
  config/            settings/{base,development,testing,production}.py, env.py, urls, wsgi, asgi
  apps/accounts/     custom email-login user
  apps/restaurants/  Restaurant and RestaurantMembership models
  requirements/      base.txt, development.txt
  tests/
```

`DJANGO_ENV` (`development`, `testing`, `production`) selects the settings
module. If unset it defaults to `production`, the strictest.

## Troubleshooting

**The page says "Request failed (500)".** Django hit an error. The terminal running `runserver` prints the traceback
(server errors are always logged there). For the full error page in the browser, set `DJANGO_DEBUG=True` in `.env`,
restart `runserver`, and open the failing URL directly, e.g. `http://localhost:8000/api/v1/restaurants/<slug>/`.
Typical causes: a migration not applied (`python manage.py showmigrations` lists unapplied ones with `[ ]`), or a
migration file missing. Turn `DJANGO_DEBUG` back off afterwards.

**"No restaurant access" after signing in.** The account has no restaurant yet. With `DJANGO_SELF_SERVICE=True` the
dashboard offers "Create your restaurant"; otherwise an owner must add you under Team.
