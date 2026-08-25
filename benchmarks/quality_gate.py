"""Hard quality gate for the reproducible ML evaluation pipeline.

Unlike a smoke test, this command exits non-zero when measured behavior falls
below the documented project bar.
"""

import json

from benchmarks.anomaly_pr import run_benchmark as run_anomaly_pr
from benchmarks.contracts import require
from benchmarks.dedup_compression import run_benchmark as run_dedup_compression
from benchmarks.detection_rate import run_benchmark as run_detection_rate
from benchmarks.rca_accuracy import run_benchmark as run_rca_accuracy


def run_quality_gate() -> dict:
    detection = run_detection_rate()
    precision_recall = run_anomaly_pr()
    dedup = run_dedup_compression()
    rca = run_rca_accuracy()

    require(detection["MAD"]["tpr"] >= 0.80, "MAD recall must be at least 80%")
    require(detection["MAD"]["fpr"] <= 0.05, "MAD false-positive rate must be at most 5%")
    require(
        detection["ISOLATION_FOREST"]["tpr"] >= 0.75,
        "Isolation Forest recall must be at least 75%",
    )
    require(
        detection["ISOLATION_FOREST"]["fpr"] <= 0.08,
        "Isolation Forest false-positive rate must be at most 8%",
    )
    require(precision_recall["mad"]["f1"] >= 0.75, "MAD F1 must be at least 75%")

    compression = float(dedup["compression_pct"]) / 100.0
    require(compression >= 0.40, "deduplication must suppress at least 40% of alerts")
    require(compression <= 0.90, "deduplication above 90% indicates likely over-grouping")

    require(rca["training_n"] >= 10, "at least ten matched training incidents are required")
    require(rca["held_out_n"] >= 6, "all six held-out incidents must be matched")
    require(rca["held_out_top1_accuracy"] >= 0.75, "held-out RCA top-1 must be at least 75%")
    require(rca["held_out_top3_accuracy"] >= 0.90, "held-out RCA top-3 must be at least 90%")

    summary = {
        "status": "passed",
        "mad": detection["MAD"],
        "isolation_forest": detection["ISOLATION_FOREST"],
        "mad_f1": precision_recall["mad"]["f1"],
        "dedup_compression_ratio": compression,
        "rca_held_out_n": rca["held_out_n"],
        "rca_top1": rca["held_out_top1_accuracy"],
        "rca_top3": rca["held_out_top3_accuracy"],
    }
    print("\nQUALITY GATE PASSED")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    run_quality_gate()


if __name__ == "__main__":
    main()
