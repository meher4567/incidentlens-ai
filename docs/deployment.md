# Production Deployment Runbook

`compose.prod.yml` is the supported production-shaped deployment. It separates
schema migration, API, workers, scheduler, frontend proxy, PostgreSQL, Redis,
and shared model artifacts. `docker-compose.yml` is intentionally optimized for
local development and exposes more ports.

## Prerequisites

- Docker Engine with Compose v2
- 4 GB RAM for the complete stack
- Two independently generated secrets

Create a local `.env` without committing it:

```bash
cp .env.example .env
openssl rand -hex 24   # POSTGRES_PASSWORD
openssl rand -hex 32   # API_KEY
```

Set the generated values in `.env`. Keep `VITE_API_URL` empty so the browser
uses the same-origin Nginx proxy. Set `VITE_DEMO_MODE=false` for any real stack.

## Start and verify

```bash
docker compose -f compose.prod.yml config --quiet
docker compose -f compose.prod.yml up -d --build
docker compose -f compose.prod.yml ps

curl --fail http://localhost:8080/healthz
curl --fail http://localhost:8080/api/ready
curl --fail http://localhost:8080/api/health
```

The first start runs `alembic upgrade head` in a one-shot `migrate` container.
The API and workers wait for that job, PostgreSQL, and Redis. The frontend then
waits for API readiness.

Expected readiness response:

```json
{"status":"ready","database":"connected"}
```

Seed only topology in a non-benchmark environment:

```bash
docker compose -f compose.prod.yml exec api python -m backend.scripts.seed --skip-truth
```

## Runtime map

| Service | Exposure | Health signal |
|---|---|---|
| `frontend` | Host `${FRONTEND_PORT:-8080}` | Nginx `/healthz` proxy |
| `api` | Private port 8000 | `/healthz` and `/api/ready` |
| `db` | Private port 5432 | `pg_isready` |
| `redis` | Private port 6379 | `redis-cli ping` |
| `worker_aggregate` | Private | Targeted Celery ping |
| `worker_detect` | Private | Targeted Celery ping |
| `celery_beat` | Private | Restart policy and logs |
| `migrate` | One shot | Exit code 0 |

Mutation example:

```bash
curl --fail \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"logs":[]}' \
  http://localhost:8080/api/logs/batch
```

Requests without the configured key receive 401. Set
`INGEST_RATE_LIMIT_PER_MINUTE` to the maximum accepted ingestion requests per
identity; production Compose defaults to 120. `MAX_REQUEST_BODY_BYTES` defaults
to 5 MB.

## Observability

The private API exposes Prometheus text format at `/metrics`. Scrape the API
container on port 8000 from the Compose network; avoid publishing the endpoint
without authentication. Useful series include:

- `incidentlens_http_requests_total`
- `incidentlens_http_request_duration_seconds`
- `incidentlens_http_requests_in_progress`

Every HTTP response includes `X-Request-ID` and `X-Process-Time-Ms`. Supply your
own `X-Request-ID` to correlate a request across ingress and application logs.

Operational commands:

```bash
docker compose -f compose.prod.yml ps
docker compose -f compose.prod.yml logs --tail=200 api worker_aggregate worker_detect celery_beat
docker compose -f compose.prod.yml exec db pg_isready -U incidentlens
docker compose -f compose.prod.yml exec redis redis-cli ping
```

## Upgrade and rollback

Before an upgrade, back up PostgreSQL and preserve the named `models` volume.
Then:

```bash
docker compose -f compose.prod.yml build
docker compose -f compose.prod.yml run --rm migrate
docker compose -f compose.prod.yml up -d
```

Migrations are forward-only in this project. Roll back application images only
when the previous version is compatible with the upgraded schema. Otherwise,
restore the matching database backup and image set together.

## Backups and recovery

```bash
docker compose -f compose.prod.yml exec -T db \
  pg_dump -U incidentlens -Fc incidentlens > incidentlens.dump

docker compose -f compose.prod.yml exec -T db \
  pg_restore -U incidentlens --clean --if-exists -d incidentlens < incidentlens.dump
```

Treat dumps and model volumes as sensitive operational data. Test restoration
on an isolated stack before relying on it.

## Release gate

```bash
make verify
python -m alembic upgrade head
python -m alembic check
docker compose -f compose.prod.yml config --quiet
docker compose -f compose.prod.yml build api frontend
```

CI adds the complete deterministic 40k-event quality gate and Python 3.11/3.13
test matrix. Benchmark throughput on the target host separately; local numbers
in this repository are evidence of the test environment, not an SLA.

## Security posture and remaining work

The backend image runs as a non-root user with a read-only filesystem,
`no-new-privileges`, all Linux capabilities dropped, PID limits, and a writable
`/tmp` only. Data services have no host ports. Secrets are mandatory Compose
inputs and are never baked into frontend assets.

For an internet-facing or multi-tenant deployment, add TLS termination, secret
manager integration, authenticated read routes/RBAC, centralized logs, alerting,
managed backups, and an ingress-level fail-closed rate limit. See
[SECURITY.md](../SECURITY.md) for reporting and supported-version policy.
