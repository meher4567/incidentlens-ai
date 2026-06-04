# Demo Guide

This guide gives reviewers a repeatable path from an empty database to a useful
IncidentLens dashboard.

## Full Stack Demo

Start the stack, migrate the database, generate incident-shaped traffic, train
the detector comparator, run the pipeline, and train the RCA model:

```bash
make demo
```

Open:

```text
http://localhost:5173
```

The dashboard should show:

- Ingested log volume and recent ingestion rate on the overview screen.
- Active or recently closed incidents grouped from anomaly alerts.
- Service health charts for request count, error rate, and p95 latency.
- Incident detail with timeline and root-cause score explanations.
- MAD vs Isolation Forest precision-recall comparison after benchmarks run.

## Fast Local Demo

Use this when the stack is already running and you want a shorter dataset:

```bash
make quick-demo
```

## Dashboard-Only Preview

The frontend includes an explicit demo data mode for screenshots and quick UI
reviews. It does not replace the real backend path.

PowerShell:

```powershell
cd frontend
$env:VITE_DEMO_MODE="true"
npm run dev -- --host 127.0.0.1 --port 5173
```

Bash:

```bash
cd frontend
VITE_DEMO_MODE=true npm run dev -- --host 127.0.0.1 --port 5173
```

Use this mode only for presentation checks. For pipeline validation, run the
full stack demo.

## Suggested Review Flow

1. Open the overview and confirm the pipeline status, log volume, active
   incident count, and recent incident table.
2. Open an incident and inspect the ordered timeline.
3. Check the root-cause ranking and feature contributions.
4. Open service health and switch between 1-minute and 5-minute windows.
5. Run `make benchmark`, then open anomaly comparison for PR curves.

## Resetting Demo State

```bash
docker compose down -v
docker compose up -d
make demo
```
