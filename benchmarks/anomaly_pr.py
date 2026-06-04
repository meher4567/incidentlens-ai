"""
Anomaly PR curve benchmark: MAD vs Isolation Forest comparison.

Computes per-detector Precision and Recall using incident_truth time windows
as ground truth for anomalous vs normal windows.

Usage:
    python -m benchmarks.anomaly_pr
"""
import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.db.session import SyncSessionLocal
from backend.app.models.anomalies import Anomaly, AnomalyDetector
from backend.app.models.metrics import MetricWindow
from backend.app.models.truth import IncidentTruth
from benchmarks.ingestion_throughput import save_results


def run_benchmark() -> dict:
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print("Anomaly PR curve benchmark: MAD vs IF\n")

    session = SyncSessionLocal()
    try:
        # Load truth windows
        truth_rows = session.execute(select(IncidentTruth)).scalars().all()
        incident_windows = [
            (t.start_time, t.end_time) for t in truth_rows if t.start_time and t.end_time
        ]
        print(f"Truth incident windows: {len(incident_windows)}")

        # Classify each metric window
        windows = (
            session.execute(select(MetricWindow).where(MetricWindow.closed_at.isnot(None)))
            .scalars()
            .all()
        )

        print(f"Total metric windows: {len(windows)}")

        results = {}

        for detector in [AnomalyDetector.MAD, AnomalyDetector.ISOLATION_FOREST]:
            # Get anomalies with scores
            anomalies = (
                session.execute(select(Anomaly).where(Anomaly.detector == detector)).scalars().all()
            )

            if not anomalies:
                results[detector.value] = {
                    "precision": 0,
                    "recall": 0,
                    "f1": 0,
                    "n_anomalies": 0,
                    "note": "no anomalies detected",
                }
                continue

            anom_set = set()
            for a in anomalies:
                anom_set.add((a.service_id, a.window_start, a.window_size_seconds))

            tp = 0
            fp = 0
            fn = 0

            for mw in windows:
                window_end = mw.window_start + timedelta(seconds=mw.window_size_seconds)
                key = (mw.service_id, mw.window_start, mw.window_size_seconds)
                is_anomalous = key in anom_set

                in_incident = False
                for istart, iend in incident_windows:
                    if mw.window_start < iend and window_end > istart:
                        in_incident = True
                        break

                if in_incident:
                    if is_anomalous:
                        tp += 1
                    else:
                        fn += 1
                else:
                    if is_anomalous:
                        fp += 1

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

            results[detector.value] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "n_anomalies": len(anomalies),
            }

            print(f"\n{detector.value}:")
            print(f"  TP={tp}, FP={fp}, FN={fn}")
            print(f"  Precision={precision:.4f}, Recall={recall:.4f}, F1={f1:.4f}")

        # Save data for frontend PR curve rendering
        pr_data = {"mad": [], "isolation_forest": []}
        for detector in [AnomalyDetector.MAD, AnomalyDetector.ISOLATION_FOREST]:
            detector_anomalies = (
                session.execute(
                    select(Anomaly)
                    .where(Anomaly.detector == detector)
                    .order_by(Anomaly.score.desc())
                )
                .scalars()
                .all()
            )

            if detector_anomalies:
                # Sort by score descending, compute cumulative PR
                scores = []
                labels = []
                for a in detector_anomalies:
                    window_end = a.window_start + timedelta(seconds=a.window_size_seconds)
                    in_incident = False
                    for istart, iend in incident_windows:
                        if a.window_start < iend and window_end > istart:
                            in_incident = True
                            break
                    scores.append(float(a.score))
                    labels.append(1 if in_incident else 0)

                # Create points for PR curve
                sorted_pairs = sorted(zip(scores, labels), key=lambda x: x[0], reverse=True)
                points = []
                for threshold_idx in range(0, len(sorted_pairs), max(1, len(sorted_pairs) // 100)):
                    thresh_pairs = sorted_pairs[: threshold_idx + 1]
                    if not thresh_pairs:
                        continue
                    tp_th = sum(1 for _, l in thresh_pairs if l == 1)
                    fp_th = sum(1 for _, l in thresh_pairs if l == 0)
                    fn_th = sum(1 for _, l in sorted_pairs[threshold_idx + 1 :] if l == 1)
                    p = tp_th / (tp_th + fp_th) if (tp_th + fp_th) > 0 else 1.0
                    r = tp_th / (tp_th + fn_th) if (tp_th + fn_th) > 0 else 0.0
                    points.append({"precision": round(p, 4), "recall": round(r, 4)})

                pr_data[detector.value] = points

        metrics = {
            "benchmark": "anomaly_pr",
            "run_date": run_date,
            "results": results,
            "pr_curve_data": pr_data,
        }

        save_results("anomaly_pr", metrics, run_date)

    finally:
        session.close()

    return results


def main():
    parser = argparse.ArgumentParser(description="Anomaly PR curve benchmark")
    parser.parse_args()
    run_benchmark()


if __name__ == "__main__":
    main()
