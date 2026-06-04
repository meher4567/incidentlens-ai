"""
Alert deduplication service.

Two rules:
1. Same service + same anomaly_type + overlapping ±5min windows
2. Different services + shared trace_id + overlapping ±2min windows

Stores dedupe relationships in deduplicated_alerts table.
Original alerts preserved; dedupe metadata is a side table.
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.alerts import Alert, DeduplicatedAlert
from backend.app.models.logs import RawLog

settings = get_settings()

SAME_SERVICE_WINDOW_MIN = settings.dedup_same_service_window_minutes  # 5
SHARED_TRACE_WINDOW_MIN = settings.dedup_shared_trace_window_minutes  # 2


def find_duplicates(
    session: Session,
    new_alert: Alert,
) -> list[Alert]:
    """
    Find existing alerts that are duplicates of new_alert.
    Returns list of duplicate alerts (already canonical or candidates).
    """
    candidates: list[Alert] = []

    # Rule 1: Same service + same anomaly_type + overlapping windows
    window_padding = timedelta(minutes=SAME_SERVICE_WINDOW_MIN)
    same_service = (
        session.execute(
            select(Alert).where(
                Alert.id != new_alert.id,
                Alert.service_id == new_alert.service_id,
                Alert.anomaly_type == new_alert.anomaly_type,
                Alert.start_window <= new_alert.end_window + window_padding,
                Alert.end_window >= new_alert.start_window - window_padding,
            )
        )
        .scalars()
        .all()
    )

    candidates.extend(same_service)

    # Rule 2: Different services + shared trace_id + overlapping ±2min windows
    if new_alert.anomaly_ids:
        # Find trace_ids from underlying logs
        trace_ids = set()
        for anomaly_id in new_alert.anomaly_ids:
            # Get logs for this anomaly's time window via anomaly->metric_window relationship
            # Simplified: find all trace_ids in logs around the alert's time window
            logs = (
                session.execute(
                    select(RawLog.trace_id)
                    .where(
                        RawLog.service_id == new_alert.service_id,
                        RawLog.timestamp >= new_alert.start_window,
                        RawLog.timestamp <= new_alert.end_window,
                        RawLog.trace_id.isnot(None),
                    )
                    .distinct()
                )
                .scalars()
                .all()
            )
            trace_ids.update(logs)

        if trace_ids:
            trace_padding = timedelta(minutes=SHARED_TRACE_WINDOW_MIN)
            # Find other alerts with different service_ids that share trace_ids
            other_service_alerts = (
                session.execute(
                    select(Alert).where(
                        Alert.id != new_alert.id,
                        Alert.service_id != new_alert.service_id,
                        Alert.start_window <= new_alert.end_window + trace_padding,
                        Alert.end_window >= new_alert.start_window - trace_padding,
                    )
                )
                .scalars()
                .all()
            )

            for other in other_service_alerts:
                # Check if any underlying logs share trace_ids
                other_logs = (
                    session.execute(
                        select(RawLog.trace_id)
                        .where(
                            RawLog.service_id == other.service_id,
                            RawLog.timestamp >= other.start_window - trace_padding,
                            RawLog.timestamp <= other.end_window + trace_padding,
                            RawLog.trace_id.in_(trace_ids),
                        )
                        .distinct()
                    )
                    .scalars()
                    .all()
                )
                if other_logs:
                    candidates.append(other)

    return candidates


def deduplicate_alerts(session: Session) -> int:
    """
    Run deduplication on all non-deduplicated alerts.
    Returns number of deduplication relationships created.
    """
    # Find alerts not yet appearing as either canonical or duplicate
    processed_ids = set()
    processed_ids.update(
        session.execute(select(DeduplicatedAlert.canonical_alert_id)).scalars().all()
    )
    processed_ids.update(
        session.execute(select(DeduplicatedAlert.duplicate_alert_id)).scalars().all()
    )

    # Get all alerts not yet processed, ordered by start_window (oldest first)
    all_alerts = (
        session.execute(
            select(Alert)
            .where(~Alert.id.in_(processed_ids) if processed_ids else True)
            .order_by(Alert.start_window.asc())
        )
        .scalars()
        .all()
    )

    dedup_count = 0

    for alert in all_alerts:
        duplicates = find_duplicates(session, alert)
        if not duplicates:
            continue

        # Find the canonical alert (oldest by start_window)
        all_candidates = [alert] + duplicates
        canonical = min(all_candidates, key=lambda a: a.start_window)

        for dup in all_candidates:
            if dup.id == canonical.id:
                continue

            # Determine reason
            if dup.service_id == canonical.service_id:
                reason = "same_service_overlap"
            else:
                reason = "shared_trace_id"

            # Check if dedup relationship already exists
            existing = session.execute(
                select(DeduplicatedAlert).where(
                    DeduplicatedAlert.canonical_alert_id == canonical.id,
                    DeduplicatedAlert.duplicate_alert_id == dup.id,
                )
            ).scalar_one_or_none()

            if not existing:
                dedup = DeduplicatedAlert(
                    canonical_alert_id=canonical.id,
                    duplicate_alert_id=dup.id,
                    dedupe_reason=reason,
                )
                session.add(dedup)
                dedup_count += 1

    session.commit()
    return dedup_count
