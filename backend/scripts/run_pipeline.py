"""
Run one or more stages of the incident detection pipeline.

Usage:
    python -m backend.scripts.run_pipeline --full
    python -m backend.scripts.run_pipeline --aggregate-only
    python -m backend.scripts.run_pipeline --process-only
    python -m backend.scripts.run_pipeline --score-only

The split-stage commands make the required ML lifecycle explicit: aggregate
features before training Isolation Forest models, then detect and cluster,
then train the RCA ranker before scoring incidents.
"""

import argparse
import sys

from backend.app.db.session import SyncSessionLocal
from backend.app.services.aggregation import run_aggregation_all_services
from backend.app.services.alerting import process_new_anomalies
from backend.app.services.clustering import cluster_alerts
from backend.app.services.deduplication import deduplicate_alerts
from backend.app.services.detection import run_detection_all
from backend.app.services.root_cause import run_rca_on_closed_incidents


def run_aggregation() -> int:
    """Aggregate raw logs into metric windows."""
    session = SyncSessionLocal()
    try:
        print("Aggregation...")
        windows = run_aggregation_all_services(session)
        print(f"  => {windows} metric windows computed")
        return windows
    except Exception as exc:
        session.rollback()
        print(f"\nAggregation failed: {exc}", file=sys.stderr)
        raise
    finally:
        session.close()


def run_processing_pipeline() -> dict[str, int]:
    """Detect anomalies, create alerts, deduplicate, and cluster incidents."""
    session = SyncSessionLocal()
    try:
        print("Detection (MAD + Isolation Forest)...")
        anomalies = run_detection_all(session)
        print(f"  => {anomalies} anomalies detected")

        print("Alerting (debounce + severity)...")
        alerts = process_new_anomalies(session)
        print(f"  => {alerts} alerts processed")

        print("Deduplication...")
        dedup = deduplicate_alerts(session)
        print(f"  => {dedup} deduplication relationships")

        print("Incident clustering...")
        incidents = cluster_alerts(session)
        print(f"  => {incidents} incidents created/updated")

        return {
            "anomalies": anomalies,
            "alerts": alerts,
            "deduplication_relationships": dedup,
            "incidents": incidents,
        }
    except Exception as exc:
        session.rollback()
        print(f"\nProcessing failed: {exc}", file=sys.stderr)
        raise
    finally:
        session.close()


def run_scoring() -> int:
    """Score closed incidents using an already-trained RCA ranker."""
    session = SyncSessionLocal()
    try:
        print("RCA ranking...")
        scored = run_rca_on_closed_incidents(session)
        print(f"  => {scored} incidents scored")
        return scored
    except Exception as exc:
        session.rollback()
        print(f"\nScoring failed: {exc}", file=sys.stderr)
        raise
    finally:
        session.close()


def run_full_pipeline() -> None:
    """Execute every runtime stage using models that have already been trained."""
    print("=" * 60)
    print("IncidentLens AI — Pipeline Runner")
    print("=" * 60)

    run_aggregation()
    run_processing_pipeline()
    run_scoring()

    print("\n" + "=" * 60)
    print("Pipeline complete! Check /api/incidents for results.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Run IncidentLens detection pipeline")
    stages = parser.add_mutually_exclusive_group(required=True)
    stages.add_argument(
        "--full",
        action="store_true",
        help="Run all runtime stages using already-trained models",
    )
    stages.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Aggregate raw logs into metric windows, then stop for model training",
    )
    stages.add_argument(
        "--process-only",
        action="store_true",
        help="Detect, alert, deduplicate, and cluster using existing feature windows",
    )
    stages.add_argument(
        "--score-only",
        action="store_true",
        help="Score closed incidents using an already-trained RCA model",
    )
    args = parser.parse_args()

    if args.full:
        run_full_pipeline()
    elif args.aggregate_only:
        run_aggregation()
    elif args.process_only:
        run_processing_pipeline()
    elif args.score_only:
        run_scoring()


if __name__ == "__main__":
    main()
