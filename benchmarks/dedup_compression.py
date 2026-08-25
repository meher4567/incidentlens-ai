"""
Deduplication compression benchmark: % of raw alerts suppressed in cascade incidents.

Usage:
    python -m benchmarks.dedup_compression
"""

import argparse
from datetime import datetime, timezone

from sqlalchemy import func, select

from backend.app.db.session import SyncSessionLocal
from backend.app.models.alerts import Alert, DeduplicatedAlert
from benchmarks.contracts import require
from benchmarks.ingestion_throughput import save_results


def run_benchmark() -> dict:
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print("Deduplication compression benchmark\n")

    session = SyncSessionLocal()
    try:
        total_alerts = session.execute(select(func.count(Alert.id))).scalar() or 0
        require(total_alerts > 0, "deduplication benchmark requires at least one alert")

        # Count deduplicated (suppressed) alerts
        suppressed = (
            session.execute(select(func.count(DeduplicatedAlert.duplicate_alert_id))).scalar() or 0
        )

        canonical = total_alerts - suppressed

        compression_pct = (suppressed / total_alerts * 100) if total_alerts > 0 else 0

        # Count by dedupe reason
        reason_counts = {}
        reason_rows = session.execute(
            select(
                DeduplicatedAlert.dedupe_reason,
                func.count(DeduplicatedAlert.dedupe_reason),
            ).group_by(DeduplicatedAlert.dedupe_reason)
        ).all()
        for reason, cnt in reason_rows:
            reason_counts[reason] = cnt

        metrics = {
            "benchmark": "dedup_compression",
            "run_date": run_date,
            "total_alerts": total_alerts,
            "canonical_alerts": canonical,
            "suppressed_alerts": suppressed,
            "compression_pct": round(compression_pct, 1),
            "dedupe_by_reason": reason_counts,
        }

        print(f"Total alerts: {total_alerts}")
        print(f"Canonical (post-dedup): {canonical}")
        print(f"Suppressed: {suppressed}")
        print(f"Compression: {compression_pct:.1f}%")
        print(f"By reason: {reason_counts}")

        save_results("dedup_compression", metrics, run_date)

    finally:
        session.close()

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Dedup compression benchmark")
    parser.parse_args()
    run_benchmark()


if __name__ == "__main__":
    main()
