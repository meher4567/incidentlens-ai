# Anomaly Detection Methods

IncidentLens records anomaly scores from two detector families so the dashboard
and benchmarks can compare interpretable single-metric detection against a
multi-metric model.

## MAD Robust Z-Score

MAD detection is the primary detector because it is simple to explain during an
incident review and robust to outliers in the baseline window.

Formula:

```text
z = 0.6745 * (observed - median) / MAD
```

Metrics scored per service/window:

| Metric | Direction |
|---|---|
| `request_count` | Positive spikes and negative drops |
| `error_rate` | Positive spikes |
| `p95_latency_ms` | Positive spikes |

Default behavior:

- Baselines use rolling median and MAD over previous closed windows.
- MAD floors prevent division by near-zero baselines: 0.01 error rate, 5 ms
  p95 latency, and one request.
- Default detection threshold is configured by `mad_threshold_default`.
- Severity is derived from absolute score: high at 4+, critical at 6+.

## Isolation Forest Comparator

Isolation Forest is used as a comparator for multi-metric drift. It is trained
per service from normal traffic and scores each metric window using:

```text
[request_count, error_rate, p95_latency_ms, unique_messages]
```

The comparator records one `multivariate` anomaly score per service for each
300-second window. MAD remains metric-specific and runs on both configured
window sizes. Keeping those records distinct lets benchmarks compare detector
families without double-counting the four Isolation Forest inputs as four
independent detections.

## Evaluation

The benchmark suite converts detections into service/time windows, then uses a
deterministic global one-to-one match against generated incident truth. This
prevents a long or duplicated detection from satisfying multiple incidents.
It reports precision, recall, false-positive rate, F1, and PR-curve points.

Run:

```bash
python -m benchmarks.anomaly_pr
python -m benchmarks.detection_rate
```

Generated results are written under `benchmarks/results/YYYY-MM-DD/`.

The enforced 40k-event result and dataset limitations are documented in
[benchmark_results.md](benchmark_results.md).
