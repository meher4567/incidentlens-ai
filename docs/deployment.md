# Deployment Readiness

IncidentLens AI is packaged as a Docker Compose stack with separate API,
frontend, PostgreSQL, Redis, aggregation worker, detection worker, and Celery
Beat services. The same service boundaries can be moved to a VM, container
platform, or managed app host.

## Runtime Services

| Service | Purpose | Health Signal |
|---|---|---|
| `api` | FastAPI ingestion and dashboard API | `GET /healthz`, `GET /api/health` |
| `frontend` | Vite React dashboard | HTTP 200 on port `5173` |
| `db` | PostgreSQL event and incident store | `pg_isready` |
| `redis` | Celery broker | `redis-cli ping` |
| `worker_aggregate` | Metric window aggregation | Celery worker process healthy |
| `worker_detect` | Detection, alerting, clustering, RCA | Celery worker process healthy |
| `celery_beat` | Scheduled pipeline triggers | Celery Beat process healthy |

Docker Compose defines health checks for PostgreSQL, Redis, the API, and the
frontend so dependent services wait for readiness instead of only container
startup.

## Required Environment

| Variable | Used By | Example |
|---|---|---|
| `APP_NAME` | API | `IncidentLens AI` |
| `APP_VERSION` | API | `0.1.0` |
| `DATABASE_URL` | API, workers, scripts | `postgresql://incidentlens:incidentlens@db:5432/incidentlens` |
| `DATABASE_URL_ASYNC` | API async DB clients | Optional; derived from `DATABASE_URL` when unset |
| `REDIS_URL` | API, workers | `redis://redis:6379/0` |
| `CORS_ALLOWED_ORIGINS` | API | `http://localhost:5173,http://127.0.0.1:5173` |
| `POSTGRES_PORT` | Docker Compose host port | `5432` |
| `REDIS_PORT` | Docker Compose host port | `6379` |
| `API_PORT` | Docker Compose host port | `8000` |
| `FRONTEND_PORT` | Docker Compose host port | `5173` |
| `VITE_API_URL` | Frontend | `http://localhost:8000` |
| `VITE_DEMO_MODE` | Frontend demo preview only | `true` |

The backend accepts comma-separated `CORS_ALLOWED_ORIGINS`. For Docker and most
local runs, setting only `DATABASE_URL` is enough because the async SQLAlchemy
URL is derived with the `postgresql+asyncpg` driver.

If default host ports are already in use, override the Compose port variables in
`.env` before running `docker compose up -d`.

## Release Gate

Run these checks before publishing a release:

```bash
python -m pytest
python -m ruff check backend worker generator benchmarks
python -m mypy backend --ignore-missing-imports

cd frontend
npm test
npm run lint
npm run build
npm audit --audit-level=moderate
```

The GitHub Actions workflow runs backend tests, frontend tests/build/audit,
lint/type-check, an integration test, and benchmark smoke checks on every push
and pull request.

## First Deploy Runbook

```bash
docker compose up -d --build
python -m alembic upgrade head
python -m backend.scripts.seed --skip-truth
```

For a demo or staging environment with generated incident truth:

```bash
make demo
```

## Health Check Commands

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/api/health
curl http://localhost:5173
```

Expected API health response:

```json
{
  "status": "ok"
}
```

The detailed health endpoint should report database and Redis availability.

## Operational Notes

- Generated JSONL logs and benchmark result folders are ignored by Git.
- Benchmarks should be compared on the same machine class and Docker resource
  limits.
- RCA scores are explainable but depend on the generated service topology and
  available incident truth during training.
- The dashboard demo mode is isolated to the frontend and must not be used as
  evidence that backend ingestion or detection ran.
