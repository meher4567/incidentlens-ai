# Benchmark methodology and evidence

IncidentLens evaluates detection, noise reduction, and RCA against deterministic
incident truth. Benchmark commands fail with a non-zero exit code when
prerequisites are missing or a result is below its documented threshold; an
empty database is never reported as a successful benchmark.

## Evaluation protocol

The seed-42 scenario spans eight event-time hours and emits 40,000 logs across
six services. It contains:

- 12 training incidents: four each for payment latency, authentication errors,
  and inventory traffic loss.
- 6 held-out incidents: three database-timeout cascades and three notification
  silent failures.
- Volume-independent incident timestamps and deterministic UUIDs, traces, and
  random draws.

Ground truth has a scenario version, seed, generator run ID, split, affected
services, affected metric, and root-cause service. Truth is only consumed by
training/evaluation commands; detection, deduplication, clustering, and online
RCA scoring cannot read it.

Detection uses a shared 300-second comparison granularity. A prediction is
matched to at most one truth window using deterministic, service-aware,
one-to-one matching. This prevents a burst of duplicate predictions from
inflating recall.

## Hard gates

| Measure | Required |
|---|---:|
| MAD recall | ≥80% |
| MAD false-positive rate | ≤5% |
| MAD F1 | ≥75% |
| Isolation Forest recall | ≥75% |
| Isolation Forest false-positive rate | ≤8% |
| Deduplication compression | 40–90% |
| Matched RCA training incidents | ≥10 |
| Matched held-out incidents | all 6 |
| Held-out RCA top-1 | ≥75% |
| Held-out RCA top-3 | ≥90% |
| HTTP ingestion errors | 0 |
| HTTP ingestion throughput | ≥250 logs/s |
| Every measured endpoint p95 | ≤250 ms |

The compression upper bound is deliberate: suppressing almost every alert can
look efficient while actually over-grouping unrelated failures.

## Reproduced result — 20 August 2026

Environment: local Docker Engine, PostgreSQL 16 Alpine, Python 3.13, production
Compose images, seed 42. Throughput and latency vary by host; ML outcomes are
deterministic for this scenario.

### Detection

| Detector | TP | FP | FN | TN | Recall | FPR | Precision | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MAD | 42 | 11 | 8 | 509 | 84.00% | 2.12% | 79.25% | 81.55% |
| Isolation Forest | 42 | 30 | 8 | 490 | 84.00% | 5.77% | 58.33% | 68.85% |

MAD is the primary operational detector; Isolation Forest is the explicitly
reported multivariate comparator.

### Alert reduction and RCA

| Measure | Result |
|---|---:|
| Alerts before deduplication | 264 |
| Suppressed relationships | 173 |
| Canonical alerts | 91 |
| Compression | 65.5% |
| RCA training incidents | 12 |
| RCA held-out incidents | 6 |
| Held-out top-1 | 83.33% |
| Held-out top-3 | 100% |
| Top-1 95% interval | 50–100% |

Per held-out type, top-1 was 2/3 for database-timeout cascades and 3/3 for
notification silent failures. The interval is wide because `n=6`; this is a
promising controlled result, not a claim of production-wide generalization.

### Production HTTP path

| Measure | Result |
|---|---:|
| Events / batch size | 20,000 / 1,000 |
| Successfully ingested | 20,000 |
| Event errors | 0 |
| Throughput | 7,746.6 logs/s |
| Batch latency p50 / p95 | 120.3 / 140.9 ms |
| `/api/metrics` p50 / p95 | 12.85 / 15.0 ms |
| Slowest measured dashboard p95 | 15.0 ms |

The HTTP benchmark ran through the production Nginx reverse proxy with API-key
authentication and the Redis rate limiter enabled.

## Reproduce the deterministic quality gate

Use an empty PostgreSQL database:

```bash
export DATABASE_URL=postgresql://incidentlens:incidentlens@localhost:5432/incidentlens

python -m alembic upgrade head
python -m generator.generate_logs \
  --events 40000 \
  --output /tmp/incidentlens-logs.jsonl \
  --truth /tmp/incidentlens-truth.jsonl
python -m backend.scripts.seed --truth /tmp/incidentlens-truth.jsonl
python -m backend.scripts.import_logs --input /tmp/incidentlens-logs.jsonl --direct-db
python -m backend.scripts.run_pipeline --aggregate-only
python -m backend.scripts.train_isolation_forest
python -m backend.scripts.run_pipeline --process-only
python -m backend.scripts.train_rca
python -m backend.scripts.run_pipeline --score-only
python -m benchmarks.quality_gate
```

For HTTP measurements against a running stack:

```bash
python -m benchmarks.ingestion_throughput \
  --api-url http://localhost:8080 \
  --api-key "$API_KEY" \
  --events 20000
python -m benchmarks.api_latency --api-url http://localhost:8080
```

Raw timestamped JSON/Markdown outputs are written below
`benchmarks/results/YYYY-MM-DD/` and ignored by Git. This document is the
reviewed, committed evidence record.
