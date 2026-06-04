# Synthetic Log Generator

Reproducible generator for IncidentLens AI that produces labeled microservice logs and incident truth data.

## Usage

```bash
# Default: 100K events, seed=42
python -m generator.generate_logs --events 100000 --output logs.jsonl --truth incidents_truth.jsonl

# Custom seed
python -m generator.generate_logs --events 100000 --seed 123 --output logs.jsonl --truth incidents_truth.jsonl

# 1M event mode
python -m generator.generate_logs --events 1000000 --output logs.jsonl --truth incidents_truth.jsonl
```

## Configuration

Edit `generator/config.yaml` to change:
- Service topology and normal traffic parameters
- Dependency graph
- Incident types, counts, and timing

## Output Files

### logs.jsonl
One JSON object per line:
```json
{
  "timestamp": "2026-01-01T00:00:01.000Z",
  "service": "api-gateway",
  "level": "INFO",
  "message": "api-gateway processed request ...",
  "request_id": "uuid",
  "trace_id": "uuid",
  "latency_ms": 150,
  "status_code": 200,
  "host": "api-gateway-pod-3",
  "region": "us-west-2"
}
```

### incidents_truth.jsonl
One JSON object per line:
```json
{
  "truth_incident_id": "uuid",
  "type": "payment_latency_spike",
  "start_time": "2026-01-01T01:00:00.000Z",
  "end_time": "2026-01-01T01:10:00.000Z",
  "root_cause_service": "payment-service",
  "affected_services": ["payment-service", "checkout-service", "api-gateway"],
  "training": true
}
```

## Service Topology

```
api-gateway → auth-service
            → checkout-service → payment-service
                               → inventory-service
```

For held-out evaluation, `notification-service` is introduced as a downstream of `checkout-service`.

## Incident Types

### Training (used to train RCA ranker)
1. **payment_latency_spike** — payment-service p95 latency jumps from 100ms to 1500ms
2. **auth_error_spike** — auth-service error rate jumps from 0.3% to 30%
3. **inventory_traffic_drop** — inventory-service request count drops 80%

### Held-Out (used for RCA evaluation only)
4. **db_timeout_cascade** — payment-service DB timeouts cascade through checkout to gateway
5. **notification_silent_fail** — notification-service fails silently; downstream looks healthy

## Normal Traffic

- Poisson-distributed request rates
- Log-normal latency distributions
- Trace ID propagation across service calls
- Some natural noise: warnings, retries, expected errors

## Reproducibility

- Default seed: 42
- Same seed + same config = byte-identical output
- Override with `--seed` flag