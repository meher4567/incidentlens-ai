# IncidentLens AI

[![CI](https://github.com/meher4567/incidentlens-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/meher4567/incidentlens-ai/actions/workflows/ci.yml)

IncidentLens AI is an end-to-end observability and incident-analysis system for
microservice logs. It ingests service events, builds rolling health metrics,
detects anomalies, deduplicates noisy alerts, clusters related alerts into
incidents, and ranks likely root causes with an interpretable model.

![IncidentLens dashboard overview](docs/assets/dashboard-overview.png)

## Highlights

- FastAPI ingestion API with batch log writes and service auto-discovery.
- Event-time aggregation into 1-minute and 5-minute metric windows.
- Median + MAD baselines for robust anomaly detection.
- Isolation Forest comparator for multi-metric anomaly detection experiments.
- Alert debounce, deduplication, and dependency-aware incident clustering.
- Logistic-regression RCA ranker with persisted feature contributions.
- React dashboard for overview metrics, service health, incidents, and PR curves.
- Reproducible quality gates for backend tests, frontend tests, build, lint, and audit.

## What This Demonstrates

- A full incident pipeline, not just a dashboard mock.
- Clear service boundaries across API, workers, database, frontend, and generator.
- ML-backed anomaly detection with a benchmarkable comparator.
- Noise reduction before incident creation through debounce and deduplication.
- Explainable RCA scoring that stores feature-level evidence for each candidate.
- CI-backed quality gates for backend, frontend, integration, and benchmark smoke checks.

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

make demo
```

Open the dashboard at `http://localhost:5173`.

For a smaller local demo:

```bash
make quick-demo
```

For a frontend-only preview with deterministic sample data:

```bash
cd frontend
VITE_DEMO_MODE=true npm run dev -- --host 127.0.0.1 --port 5173
```

Use the demo mode for UI review only. Use `make demo` for the real ingestion,
detection, incident, and RCA pipeline.

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

## Deployment Readiness

- Docker Compose defines the API, frontend, PostgreSQL, Redis, workers, and scheduler.
- `/healthz` and `/api/health` expose API health checks.
- GitHub Actions runs lint, type-check, frontend build/test/audit, backend tests,
  integration tests, and benchmark smoke checks.
- See [docs/deployment.md](docs/deployment.md) for the runbook, environment
  variables, health checks, and release gate.

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
- [Demo Guide](docs/demo.md)
- [Incident Walkthrough](docs/incident_walkthrough.md)
- [Deployment Readiness](docs/deployment.md)
- [RCA Ablation Notes](docs/ablation_findings.md)
- [Benchmark Methodology](docs/benchmark_results.md)
- [Generator Specification](generator/README.md)

## License

MIT
