# GitHub Repository Analytics - Backend

FastAPI backend for analyzing GitHub repository history. See [plan.md](plan.md) and [docs/API.md](docs/API.md).

## Quick start

1. Copy `.env.example` to `.env` and set a secure `SECRET_KEY`
2. `docker compose up -d postgres redis`
3. `pip install -e ".[dev]"`
4. `alembic upgrade head`
5. `uvicorn app.main:app --reload`
6. `celery -A app.workers.celery_app worker --loglevel=info` (separate terminal)

   On **Windows**, if you still see `PermissionError` / `prefork` errors, use:
   `celery -A app.workers.celery_app worker --loglevel=info --pool=solo`

API docs: http://localhost:8000/docs

## Endpoints

**Auth:** register, login, `/me`

**Repositories:** paste URL → receive `job_id` → poll `GET /jobs/{job_id}` until `result` is populated. See [docs/API.md](docs/API.md) for the full FE contract.

## Tests

`pytest`
