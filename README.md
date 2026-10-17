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

> **Expected until Stage 2:** `AUTH_USER_MODEL` already points to
> `accounts.User`, which is implemented in the next stage. Until then every
> Django command, including `check` and `pytest`, fails with
> `AUTH_USER_MODEL refers to model 'accounts.User' that has not been installed`.

## Migration sequence

1. Implement `accounts.User`, then `python manage.py makemigrations accounts`.
   Review and commit `0001_initial.py`.
2. Only then run `python manage.py migrate` for the first time. Never migrate
   before the accounts migration exists.
3. Implement `restaurants` models, then `makemigrations restaurants` and review.
4. Add later apps (`menu`, `orders`, `audit`) one at a time, each with its own
   reviewed migration.

## Layout

```
.env.example
.gitignore
README.md
docs/
backend/
  manage.py
  pytest.ini
  config/            settings/{base,development,testing,production}.py, env.py, urls, wsgi, asgi
  apps/accounts/     custom user model (next stage)
  apps/restaurants/  restaurant and membership models (after accounts)
  requirements/      base.txt, development.txt
  tests/
```

`DJANGO_ENV` (`development`, `testing`, `production`) selects the settings
module. If unset it defaults to `production`, the strictest.
