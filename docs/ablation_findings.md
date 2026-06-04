# RCA Ranker Methodology

The RCA ranker scores each affected service in a detected incident and returns a
ranked list of likely root causes. The model is intentionally interpretable:
scores are persisted with the feature vector and per-feature contribution.

## Model

- Algorithm: logistic regression
- Class balancing: `class_weight="balanced"`
- Output: per-service probability-like score, rank, feature vector, and feature
  contributions

## Features

| Feature | Meaning |
|---|---|
| `is_earliest` | Whether the service produced the first canonical alert |
| `earliest_seconds_gap` | Time gap from first alert to the next affected service |
| `upstream_position` | Count of affected downstream services in the incident |
| `blast_radius` | Count of all downstream services in the dependency graph |
| `metric_jump_magnitude` | Maximum absolute MAD score for the service |
| `alert_count` | Number of canonical alerts for the service |

## Evaluation

The benchmark script matches detected incidents to generated truth windows and
reports top-1 and top-3 accuracy. Held-out incident types are evaluated
separately from training incident types to make generalization visible.

Run:

```bash
python -m backend.scripts.train_rca
python -m benchmarks.rca_accuracy
```

## Ablation Plan

The ablation workflow retrains the ranker after dropping one feature at a time.
The expected output is a table showing how much each feature changes top-3
accuracy on held-out incidents.

Key questions the ablation should answer:

- How much signal comes from the earliest-alert feature?
- Does graph position improve ranking beyond alert timing alone?
- Does metric magnitude help distinguish noisy downstream symptoms from likely
  root causes?
- Does alert count add useful signal or amplify noisy services?

## Known Limits

- Synthetic topology is intentionally small and inspectable.
- Ground truth comes from generated incidents, not production incidents.
- The feature set is hand-designed and optimized for explainability.
- Larger service graphs would need broader incident generation and more diverse
  training examples before drawing stronger conclusions.
