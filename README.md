# GitHub Repository Analytics - Backend

FastAPI backend for analyzing GitHub repository history. See [plan.md](plan.md) and [docs/API.md](docs/API.md).

## Quick start

1. Copy `.env.example` to `.env` and set a secure `SECRET_KEY`
2. `docker compose up -d postgres`
3. `pip install -e ".[dev]"`
4. `alembic upgrade head`
5. `uvicorn app.main:app --reload`

> Background analysis pipelines (clone, parse, analyze) run automatically in-process via a thread pool worker. No separate Celery worker or Redis instance is required!


## Performance (large repos)

Parsing uses a fast `git log --numstat` path by default (`PARSE_USE_GIT_LOG=true`). For huge histories like Brython, you can cap work in `.env`:

```env
ANALYSIS_MAX_COMMITS=10000
```

Progress during parse now reflects real completion (not stuck at 30%). **Multiple Celery workers speed up concurrent repos**, not a single repo — each analysis is one sequential pipeline (clone → parse → analyze).

API docs: http://localhost:8000/docs

## Endpoints

**Auth:** register, login, `/me`

**Repositories:** paste URL → receive `job_id` → poll `GET /jobs/{job_id}` until `result` is populated. See [docs/API.md](docs/API.md) for the full FE contract.

## Tests

`pytest`

## Deploy on Render (free tier)

Pre-deploy commands are paid on Render. Migrations run automatically on API startup via `scripts/start-api.sh`.

**Web service Start Command** (optional override if not using Docker CMD):

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**One-time fix without redeploying code** — run locally against Render's **External** Postgres URL:

```powershell
$env:DATABASE_URL="postgresql+psycopg://USER:PASS@HOST/DB"
alembic upgrade head
```
