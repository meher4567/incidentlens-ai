# IncidentLens AI — Architecture

## System Overview

IncidentLens AI is an ML-powered observability platform that ingests synthetic microservice logs, aggregates metrics, detects anomalies, deduplicates alerts, clusters related alerts into incidents, reconstructs incident timelines, and ranks likely root causes using an interpretable learned RCA model.

## Architecture Diagram

```
┌──────────────┐    JSONL     ┌────────────────┐
│  Synthetic   │─────────────▶│ POST /logs/batch│
│  Generator   │              │  (FastAPI)      │
│ (5 services) │              └───────┬────────┘
└──────────────┘                      │
       │                              ▼
       │ truths.jsonl          ┌──────────────┐
       │ (benchmarks only)    │  PostgreSQL 16│
       │                      │  - raw_logs   │
       │                      │  - metric_win │
       │                      │  - anomalies  │
       │                      │  - alerts     │
       │                      │  - incidents  │
       │                      │  - rca_scores │
       │                      └──────┬───────┘
       │                             │
       ▼                             ▼
┌──────────────┐    ┌───────────────────────────┐
│  Benchmark   │    │  Celery Workers            │
│  Scripts     │    │  ┌─────────────────────┐   │
│  - throughput│    │  │ Aggregation (30s)   │   │
│  - detection │    │  │ → metric_windows    │   │
│  - dedup     │    │  └─────────┬───────────┘   │
│  - rca       │    │            ▼               │
│  - api_lat   │    │  ┌─────────────────────┐   │
│  - anomaly_pr│    │  │ Detection           │   │
└──────────────┘    │  │ → MAD + IF scores   │   │
                    │  └─────────┬───────────┘   │
                    │            ▼               │
                    │  ┌─────────────────────┐   │
                    │  │ Alerting + Dedupe   │   │
                    │  │ → alerts            │   │
                    │  └─────────┬───────────┘   │
                    │            ▼               │
                    │  ┌─────────────────────┐   │
                    │  │ Clustering + RCA    │   │
                    │  │ → incidents, scores │   │
                    │  └─────────────────────┘   │
                    └───────────────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  React Dashboard │
                    │  (4 screens)     │
                    │  - Overview      │
                    │  - Service Health│
                    │  - Incident View │
                    │  - Anomaly Comp  │
                    └──────────────────┘
```

## Service Topology

```
api-gateway
   ├──▶ auth-service
   └──▶ checkout-service
            ├──▶ payment-service
            └──▶ inventory-service

[Held-out only]
checkout-service
   └──▶ notification-service
```

## Component Contracts

### Generator → Ingestion API
- **Format:** JSONL (one log event per line)
- **Log schema:** `{timestamp, service, level, message, request_id, trace_id, latency_ms, status_code, host, region}`
- **Truth side-channel:** `incidents_truth.jsonl` — only read by benchmark scripts

### Ingestion API → Database
- **Batch endpoint:** `POST /api/logs/batch` — up to 1000 events
- **Auto-creates unknown services**
- **Indexes:** `(service_id, timestamp)`, `(trace_id)`

### Aggregation Worker
- **Schedule:** Every 30 seconds (Celery Beat)
- **Windows:** 1-minute and 5-minute
- **Metrics:** request_count, error_count, error_rate, p50/p95_latency_ms, unique_messages
- **Baselines:** Rolling median + MAD over 30 closed windows
- **MAD floors:** error_rate=0.001, p95_latency=5ms, request_count=1
- **Idempotent:** UPSERT on (service_id, window_start, window_size_seconds)

### Detection Worker
- **Triggered by:** Aggregation completion
- **Methods:** MAD robust z-score (primary) + Isolation Forest (comparator)
- **MAD formula:** z = 0.6745 × (observed − median) / MAD
- **IF features:** [request_count, error_rate, p95_latency_ms, unique_messages]
- **Both detectors record per window** for PR-curve comparison

### Alert Engine
- **Debounce:** Same service + anomaly_type within 5 minutes
- **Severity:** medium (|z|≥3), high (|z|≥4), critical (|z|≥6 or IF top 5%)
- **Anomaly types:** error_rate_spike, latency_spike, traffic_spike, traffic_drop

### Deduplication Engine
- **Rule 1:** Same service + same anomaly_type + overlapping ±5min windows
- **Rule 2:** Different services + shared trace_id + overlapping ±2min windows
- **Output:** canonical alerts + deduplicated_alerts table

### Incident Clusterer
- **Signals:** Time proximity (5 min) + graph adjacency
- **Close:** After 10 minutes with no new alert
- **Merge:** Multiple matching incidents → oldest

### RCA Ranker
- **Model:** Logistic regression with class_weight='balanced'
- **Features (per service per incident):**
  1. is_earliest — first alert in incident
  2. earliest_seconds_gap — gap to second alert
  3. upstream_position — downstream count in incident
  4. blast_radius — downstream count in full graph
  5. metric_jump_magnitude — max |z-score|
  6. alert_count — total alerts in incident
- **Training:** 60 incidents (3 types × 20 each)
- **Evaluation:** 40 held-out incidents (2 types × 20 each)
- **Explainability:** feature_contributions JSONB on root_cause_scores

## Database Schema

| Table | Key | Purpose |
|---|---|---|
| services | id (UUID) | Service registry |
| service_dependencies | (upstream, downstream) | Directed dep graph |
| raw_logs | id (bigserial) | Immutable log storage |
| metric_windows | (service, window_start, size) | Aggregated metrics |
| anomalies | (service, metric, window, detector) | Detection results |
| alerts | id (UUID) | Coalesced anomaly alerts |
| deduplicated_alerts | (canonical, duplicate) | Dedup relationships |
| incidents | id (UUID) | Clustered incident groups |
| incident_alerts | (incident, alert) | Alert-to-incident join |
| incident_root_cause_scores | (incident, service) | RCA ranking |
| incident_truth | truth_incident_id (UUID) | Ground truth (benchmarks only) |
| watermark | (service_id, window_size_seconds) | Last closed window tracking |
| internal_metrics | id (bigserial) | Platform self-observability |

## API Endpoints

### Ingestion
- `POST /api/logs/batch` — batch ingest up to 1000 events
- `GET /api/logs` — query with filters
- `GET /api/logs/counts` — total log count

### Services
- `GET /api/services` — list
- `POST /api/services/dependencies` — create edge
- `GET /api/services/{id}/health` — time-series metrics

### Anomalies, Alerts, Incidents
- `GET /api/anomalies` — list with detector filter
- `GET /api/alerts` — canonical (deduped) alerts
- `GET /api/incidents` — list
- `GET /api/incidents/{id}` — detail with timeline + RCA scores

### Health
- `GET /healthz` — lightweight database health check
- `GET /api/health` — database and Redis health check
