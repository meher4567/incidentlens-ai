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
- MAD floors prevent division by near-zero baselines.
- Default detection threshold is configured by `mad_threshold_default`.
- Severity is derived from absolute score: high at 4+, critical at 6+.

## Isolation Forest Comparator

Isolation Forest is used as a comparator for multi-metric drift. It is trained
per service from normal traffic and scores each metric window using:

```text
[request_count, error_rate, p95_latency_ms, unique_messages]
```

The comparator is intentionally kept separate from MAD scoring so benchmark
reports can compare precision-recall curves without hiding detector behavior.

## Evaluation

The benchmark suite compares detections against generated incident-truth
windows and reports precision, recall, F1, and PR-curve points.

Run:

```bash
python -m benchmarks.anomaly_pr
python -m benchmarks.detection_rate
```

Generated results are written under `benchmarks/results/YYYY-MM-DD/`.
