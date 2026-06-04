# Incident Walkthrough

This walkthrough explains the end-to-end behavior that IncidentLens is built to
surface in the dashboard.

## Scenario

A checkout flow starts failing because `payment-service` latency rises sharply.
The degraded payment calls cause retries in `checkout-service`, which then
raises error rate and latency for user-facing checkout requests. Downstream
services can also show secondary symptoms as the cascade spreads.

## Pipeline Behavior

1. The generator emits timestamped JSONL events across the service graph.
2. The ingestion API writes raw logs and auto-discovers services.
3. Aggregation builds 1-minute and 5-minute windows for request count, error
   rate, p50 latency, p95 latency, and unique messages.
4. Detection records MAD robust z-score anomalies and Isolation Forest
   comparator scores.
5. Alerting debounces repeated anomalies and assigns severity.
6. Deduplication collapses overlapping same-service alerts and trace-related
   cross-service alerts.
7. Clustering groups alerts into an incident using time proximity and service
   graph adjacency.
8. RCA ranks candidate services using timing, graph position, blast radius,
   metric jump magnitude, and alert count.

## What The Dashboard Should Show

| Surface | Expected Signal |
|---|---|
| Overview | Active incident count, affected services, ingestion rate, recent incidents |
| Service Health | p95 latency and error-rate movement around the incident window |
| Incident Detail | Timeline sorted by first observed alert |
| Root Cause Ranking | Highest score on the likely upstream failure point |
| Anomaly Methods | Precision-recall comparison for detector behavior |

## Reviewer Questions The Project Answers

- Can it ingest and normalize high-volume service logs?
- Does it separate normal traffic from incident windows?
- Does it reduce alert noise before incident creation?
- Can it connect symptoms across a dependency graph?
- Does the RCA ranking provide inspectable evidence instead of a black-box
  label?
- Are quality gates reproducible through CI and local commands?

## Known Boundaries

- The data source is synthetic so benchmark numbers should be read as controlled
  evaluation results, not production telemetry claims.
- Isolation Forest is used as a comparator; MAD is the primary operational
  detector in the current pipeline.
- Service topology is static in the demo dataset. A production deployment would
  source dependencies from service metadata, tracing, or a service catalog.
