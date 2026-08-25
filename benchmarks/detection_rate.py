"""
Detection rate benchmark: TPR/FPR using incident_truth ground truth.

Computes True Positive Rate and False Positive Rate by comparing
detected anomalies against incident truth time windows.

Usage:
    python -m benchmarks.detection_rate
"""

import argparse
from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.db.session import SyncSessionLocal
from backend.app.models.anomalies import Anomaly, AnomalyDetector
from backend.app.models.metrics import MetricWindow
from backend.app.models.truth import IncidentTruth
from backend.app.services.detection import IF_WINDOW_SIZE_SECONDS
from backend.app.services.evaluation import window_matches_truth
from benchmarks.contracts import require
from benchmarks.ingestion_throughput import save_results


def run_benchmark() -> dict:
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print("Detection rate benchmark: TPR/FPR\n")

    session = SyncSessionLocal()
    try:
        # Load truth windows
        truth_rows = session.execute(select(IncidentTruth)).scalars().all()
        require(len(truth_rows) >= 5, "at least five truth incidents are required")
        print(f"Truth incidents: {len(truth_rows)}")

        # Classify each metric window as incident or normal
        windows = (
            session.execute(
                select(MetricWindow).where(
                    MetricWindow.closed_at.isnot(None),
                    MetricWindow.window_size_seconds == IF_WINDOW_SIZE_SECONDS,
                )
            )
            .scalars()
            .all()
        )

        print(f"Total metric windows: {len(windows)}")
        require(len(windows) >= 100, "at least 100 closed metric windows are required")

        results = {}
        for detector in [AnomalyDetector.MAD, AnomalyDetector.ISOLATION_FOREST]:
            # Get anomalies for this detector
            anomalies = (
                session.execute(
                    select(Anomaly).where(
                        Anomaly.detector == detector,
                        Anomaly.window_size_seconds == IF_WINDOW_SIZE_SECONDS,
                    )
                )
                .scalars()
                .all()
            )

            anom_windows = set()
            for a in anomalies:
                anom_windows.add((a.service_id, a.window_start, a.window_size_seconds))

            tp = 0  # Anomaly detected during incident
            fp = 0  # Anomaly detected during normal period
            fn = 0  # No anomaly detected during incident
            tn = 0  # No anomaly detected during normal period

            for mw in windows:
                is_anomalous = (
                    mw.service_id,
                    mw.window_start,
                    mw.window_size_seconds,
                ) in anom_windows

                in_incident = any(
                    window_matches_truth(
                        service_id=mw.service_id,
                        window_start=mw.window_start,
                        window_size_seconds=mw.window_size_seconds,
                        truth=truth,
                    )
                    for truth in truth_rows
                )

                if in_incident:
                    if is_anomalous:
                        tp += 1
                    else:
                        fn += 1
                else:
                    if is_anomalous:
                        fp += 1
                    else:
                        tn += 1

            total_incident_windows = tp + fn
            total_normal_windows = fp + tn
            require(total_incident_windows > 0, "no positive service-aware windows were found")
            require(total_normal_windows > 0, "no normal windows were found")
            require(len(anomalies) > 0, f"{detector.value} produced no anomalies")

            tpr = tp / total_incident_windows if total_incident_windows > 0 else 0
            fpr = fp / total_normal_windows if total_normal_windows > 0 else 0

            results[detector.value] = {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "tpr": round(tpr, 4),
                "fpr": round(fpr, 4),
                "total_anomalies": len(anomalies),
            }

            print(f"\n{detector.value}:")
            print(f"  TP={tp}, FP={fp}, FN={fn}")
            print(f"  TPR={tpr:.4f}, FPR={fpr:.4f}")

        # Save
        output = {
            "benchmark": "detection_rate",
            "run_date": run_date,
            "n_truth_incidents": len(truth_rows),
            "n_metric_windows": len(windows),
            "evaluation_window_size_seconds": IF_WINDOW_SIZE_SECONDS,
            "results": results,
        }
        save_results("detection_rate", output, run_date)

    finally:
        session.close()

    return results


def main():
    parser = argparse.ArgumentParser(description="Detection rate benchmark")
    parser.parse_args()
    run_benchmark()


if __name__ == "__main__":
    main()
