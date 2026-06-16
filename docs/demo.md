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
- Incident detail with an operator briefing, timeline, root-cause score
  explanations, and a copyable Markdown handoff.
- MAD vs Isolation Forest precision-recall comparison after benchmarks run.

## Fast Local Demo

Use this when the stack is already running and you want a shorter dataset:

```bash
make quick-demo
```

## Dashboard-Only Preview

The frontend includes an explicit demo data mode for screenshots and quick UI
checks. It does not replace the real backend path.

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

Use this mode only for visual checks. For pipeline validation, run the
full stack demo.

## Suggested Validation Flow

1. Open the overview and confirm the pipeline status, log volume, active
   incident count, and recent incident table.
2. Open an incident and read the Incident Briefing at the top of the detail
   page: summary, suspected root cause, impact, evidence, and recommended
   actions.
3. Use **Copy Markdown** to produce an incident handoff that could be pasted
   into Slack, Jira, or a post-incident review.
4. Inspect the ordered timeline and compare it against the briefing evidence.
5. Check the root-cause ranking and feature contributions.
6. Open service health and switch between 1-minute and 5-minute windows.
7. Run `make benchmark`, then open anomaly comparison for PR curves.

## Operational Design Notes

- The briefing is deterministic and explainable; it does not hide the pipeline
  behind an LLM-generated paragraph.
- It converts low-level observability artifacts into an operator workflow:
  evidence, suspected owner, impact, and immediate next actions.
- The Markdown export demonstrates practical handoff integration without
  requiring external Slack or Jira workspace credentials.
- The feature reuses the same incident detail contract as the dashboard, so
  tests protect both API serialization and UI behavior.

## Resetting Demo State

```bash
docker compose down -v
docker compose up -d
make demo
```
