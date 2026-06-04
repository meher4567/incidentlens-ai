# IncidentLens AI

IncidentLens AI is an end-to-end observability and incident-analysis system for
microservice logs. It ingests service events, builds rolling health metrics,
detects anomalies, deduplicates noisy alerts, clusters related alerts into
incidents, and ranks likely root causes with an interpretable model.

## Highlights

- FastAPI ingestion API with batch log writes and service auto-discovery.
- Event-time aggregation into 1-minute and 5-minute metric windows.
- Median + MAD baselines for robust anomaly detection.
- Isolation Forest comparator for multi-metric anomaly detection experiments.
- Alert debounce, deduplication, and dependency-aware incident clustering.
- Logistic-regression RCA ranker with persisted feature contributions.
- React dashboard for overview metrics, service health, incidents, and PR curves.
- Reproducible quality gates for backend tests, frontend tests, build, lint, and audit.

## Architecture

```text
Synthetic logs
    |
    v
FastAPI ingestion API
    |
    v
PostgreSQL
    |
    +--> Aggregation worker -> metric_windows
    +--> Detection worker   -> anomalies
    +--> Alerting worker    -> alerts + deduplicated_alerts
    +--> Clustering/RCA     -> incidents + root_cause_scores
    |
    v
React dashboard
```

Service dependency graph used by the generator and incident clusterer:

```text
api-gateway
  |-- auth-service
  `-- checkout-service
        |-- payment-service
        |-- inventory-service
        `-- notification-service
```

## Stack

- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.x, Pydantic, Celery
- Database/cache: PostgreSQL 16, Redis
- ML/data: scikit-learn, NumPy, pandas, NetworkX
- Frontend: React, Vite, TypeScript, TanStack Query, Recharts
- Tooling: Docker Compose, Alembic, pytest, ruff, mypy, Vitest

## Quick Start

```bash
git clone https://github.com/meher4567/incidentlens-ai.git
cd incidentlens-ai

docker compose up -d
make seed
make generate
make detect
```

Open the dashboard at `http://localhost:5173`.

For a smaller local demo:

```bash
make quick-demo
```

## Quality Gates

Backend:

```bash
python -m pytest
python -m ruff check backend worker generator benchmarks
python -m mypy backend --ignore-missing-imports
```

Frontend:

```bash
cd frontend
npm test
npm run build
npm audit --audit-level=moderate
```

## Benchmarking

Benchmark scripts live in `benchmarks/` and write timestamped results under
`benchmarks/results/YYYY-MM-DD/`.

```bash
make benchmark
```

Covered benchmark areas:

| Area | Script |
|---|---|
| Ingestion throughput | `benchmarks/ingestion_throughput.py` |
| Detection TPR/FPR | `benchmarks/detection_rate.py` |
| Dedup compression | `benchmarks/dedup_compression.py` |
| RCA accuracy | `benchmarks/rca_accuracy.py` |
| API latency | `benchmarks/api_latency.py` |
| Anomaly PR curves | `benchmarks/anomaly_pr.py` |

Benchmark reports are intentionally generated artifacts and are not committed by
default. See [docs/benchmark_results.md](docs/benchmark_results.md) for the
methodology and acceptance targets.

## Project Layout

```text
backend/      FastAPI app, SQLAlchemy models, pipeline services, scripts, tests
worker/       Celery app and scheduled task wrappers
frontend/     React dashboard, API client, frontend tests
generator/    Synthetic microservice log and incident generator
benchmarks/   Measurement scripts for ingestion, detection, RCA, latency
docs/         Architecture and method notes
alembic/      Database migrations
```

## Documentation

- [Architecture](docs/architecture.md)
- [Anomaly Methods](docs/anomaly_methods.md)
- [RCA Ablation Notes](docs/ablation_findings.md)
- [Benchmark Methodology](docs/benchmark_results.md)
- [Generator Specification](generator/README.md)

## License

MIT
