# Benchmark Methodology

IncidentLens includes benchmark scripts for validating the pipeline under a
repeatable synthetic workload. Results are generated locally because throughput
and latency depend heavily on machine size, Docker resource limits, and database
configuration.

Generated benchmark artifacts are written to:

```text
benchmarks/results/YYYY-MM-DD/
```

The generated result files are intentionally ignored by Git so that committed
documentation stays environment-neutral.

## Benchmark Suite

| Benchmark | Script | What It Measures |
|---|---|---|
| Ingestion throughput | `benchmarks/ingestion_throughput.py` | Batch ingest rate and batch latency |
| Detection rate | `benchmarks/detection_rate.py` | TPR/FPR against incident truth windows |
| Dedup compression | `benchmarks/dedup_compression.py` | Alert-volume reduction during cascades |
| RCA accuracy | `benchmarks/rca_accuracy.py` | Top-1/top-3 root-cause ranking accuracy |
| API latency | `benchmarks/api_latency.py` | p50/p95/p99 dashboard endpoint latency |
| Anomaly PR | `benchmarks/anomaly_pr.py` | Precision-recall comparison for detectors |

## Acceptance Targets

These are engineering targets for a local Docker Compose run on generated data,
not hard-coded claims.

| Area | Target |
|---|---|
| Ingestion throughput | At least 500 logs/sec |
| Detection recall | At least 85% on incident windows |
| Detection false positive rate | Less than 15% on normal windows |
| Dedup compression | At least 40% alert reduction on cascades |
| RCA ranking | At least 70% top-3 accuracy on held-out incident types |
| Incident detail API | p95 below 300 ms |

## Reproducing Results

```bash
docker compose up -d
make seed
make generate
make train-if
make detect
python -m backend.scripts.train_rca
make benchmark
```

For a smaller smoke run, reduce generated events and run selected benchmark
scripts directly.

## Interpreting Results

- Throughput should be evaluated with the same batch size across runs.
- Detection metrics should be read together; high recall with excessive false
  positives is not a useful operational result.
- RCA accuracy is measured on matched detected incidents, so poor clustering can
  reduce the effective evaluation sample.
- API latency should be measured after the database is seeded and the dashboard
  endpoints have representative data to query.
