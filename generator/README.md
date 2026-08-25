# Deterministic Telemetry Generator

The generator creates reproducible microservice logs plus a separate incident
truth file used only by RCA training and benchmark evaluation.

## Run it

```bash
# Default scenario v2, seed 42
python -m generator.generate_logs \
  --events 100000 \
  --output logs.jsonl \
  --truth incidents_truth.jsonl

# Independent deterministic variation
python -m generator.generate_logs \
  --events 100000 --seed 123 \
  --output logs-seed-123.jsonl \
  --truth truth-seed-123.jsonl
```

Configuration lives in `generator/config.yaml`. The event-time interval remains
the same when event count changes, so a 40k CI run and a 100k demo exercise the
same incident placement at different traffic densities.

## Scenario contract

- Fixed eight-hour UTC interval beginning `2026-01-01T00:00:00Z`
- Six services and five caller-to-dependency edges
- 12 training incidents: four each for payment latency, auth errors, and
  inventory traffic drops
- Six held-out incidents: three database-timeout cascades and three
  notification silent failures
- Five-minute incident duration and 20-minute spacing
- Deterministic UUIDs, hosts, regions, traces, messages, and ordering
- Incident effects propagate from a failed dependency back to affected callers

The notification service participates in normal traffic but is a root cause
only in the held-out set, requiring the ranker to generalize to an unseen root
cause service.

## Log output

`logs.jsonl` contains one event per line:

```json
{
  "timestamp": "2026-01-01T00:00:01.000000+00:00",
  "service": "payment-service",
  "level": "INFO",
  "message": "payment-service processed request 1a3d1fa7-bc89-40a9-a3b8-c1e9392456de",
  "request_id": "1a3d1fa7-bc89-40a9-a3b8-c1e9392456de",
  "trace_id": "3eb13b90-4668-4257-bdd6-40fb06671ad1",
  "latency_ms": 46,
  "status_code": 200,
  "host": "payment-service-pod-5",
  "region": "us-west-2"
}
```

Healthy traffic derives `ERROR` level and failing status codes from the
configured error rate; it does not inject unrelated random errors. Request and
trace IDs are propagated across dependency calls to make cross-service evidence
and deduplication testable.

## Truth output

`incidents_truth.jsonl` is a side channel:

```json
{
  "truth_incident_id": "deterministic-uuid",
  "type": "payment_latency_spike",
  "start_time": "2026-01-01T01:00:00+00:00",
  "end_time": "2026-01-01T01:05:00+00:00",
  "root_cause_service": "payment-service",
  "affected_services": ["api-gateway", "checkout-service", "payment-service"],
  "split": "training",
  "seed": 42,
  "scenario_version": "2.0"
}
```

Detection and clustering do not import this file. `backend.scripts.seed` stores
it only for supervised RCA training and evaluation. The benchmark rejects
missing training/held-out slices rather than returning a misleading zero.

## Reproducibility check

```bash
python -m generator.generate_logs --events 5000 --output /tmp/a.jsonl --truth /tmp/a-truth.jsonl
python -m generator.generate_logs --events 5000 --output /tmp/b.jsonl --truth /tmp/b-truth.jsonl
sha256sum /tmp/a.jsonl /tmp/b.jsonl /tmp/a-truth.jsonl /tmp/b-truth.jsonl
```

Each corresponding pair must have the same digest. Use a different seed to
test robustness without changing the train/held-out contract.
