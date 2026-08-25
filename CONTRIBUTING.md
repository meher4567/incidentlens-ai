# Contributing to IncidentLens AI

Thanks for improving IncidentLens. Changes should preserve reproducibility,
truth isolation, and fail-closed evaluation.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt

cd frontend
npm ci
cd ..

docker compose up -d db redis
python -m alembic upgrade head
```

Python 3.11 and 3.13 are tested in CI; Node 22 is used for the frontend.

## Before opening a pull request

```bash
make verify
python -m alembic check
```

For changes to generation, aggregation, detection, alerting, deduplication,
clustering, RCA, or evaluation, also reproduce the deterministic quality run
from [docs/benchmark_results.md](docs/benchmark_results.md).

## Engineering rules

- Add or update tests for behavior changes; backend branch coverage must remain
  at or above 80%.
- Keep incident truth out of online detection and clustering paths.
- Preserve event-time processing and deterministic ordering. Do not use the
  current wall clock in the generated scenario or benchmark matcher.
- Keep migrations and ORM models aligned. Never edit an applied migration;
  create a new revision.
- Benchmarks must fail on missing data, request errors, or incomplete slices.
- Do not commit generated logs, model artifacts, `.env`, benchmark outputs, or
  raw browser-audit artifacts.
- Update claims and limitations when changing a measured result.

## Pull request description

Include:

1. The problem and user/operator impact.
2. The implementation and important tradeoffs.
3. Exact verification commands and results.
4. Schema, API, security, or benchmark implications.
5. Screenshots for user-visible changes.

Keep commits focused and never include secrets or production telemetry.
