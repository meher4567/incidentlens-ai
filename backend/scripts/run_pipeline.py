"""
Run the full detection pipeline: aggregate -> detect -> alert -> dedupe -> cluster -> rank.

Usage:
    python -m backend.scripts.run_pipeline --full
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


def run_full_pipeline():
    """Execute the end-to-end pipeline."""
    session = SyncSessionLocal()
    try:
        print("=" * 60)
        print("IncidentLens AI — Pipeline Runner")
        print("=" * 60)

        print("\n[1/6] Aggregation...")
        windows = run_aggregation_all_services(session)
        print(f"  => {windows} metric windows computed")

        print("\n[2/6] Detection (MAD robust z-score)...")
        anomalies = run_detection_all(session)
        print(f"  => {anomalies} anomalies detected")

        print("\n[3/6] Alerting (debounce + severity)...")
        alerts = process_new_anomalies(session)
        print(f"  => {alerts} alerts processed")

        print("\n[4/6] Deduplication...")
        dedup = deduplicate_alerts(session)
        print(f"  => {dedup} deduplication relationships")

        print("\n[5/6] Incident Clustering...")
        incidents = cluster_alerts(session)
        print(f"  => {incidents} incidents created/updated")

        print("\n[6/6] RCA Ranking...")
        scored = run_rca_on_closed_incidents(session)
        print(f"  => {scored} incidents scored")

        print("\n" + "=" * 60)
        print("Pipeline complete! Check /api/incidents for results.")
        print("=" * 60)

    except Exception as exc:
        session.rollback()
        print(f"\nPipeline failed: {exc}", file=sys.stderr)
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Run IncidentLens detection pipeline")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full pipeline (aggregate -> detect -> alert -> dedupe -> cluster -> rank)",
    )
    args = parser.parse_args()

    if args.full:
        run_full_pipeline()
    else:
        print("Specify --full to run the complete pipeline.")
        print("Example: python -m backend.scripts.run_pipeline --full")


if __name__ == "__main__":
    main()
