"""
Alert deduplication service.

Two rules:
1. Same service + same anomaly_type + overlapping ±5min windows
2. Different services + shared trace_id + overlapping ±2min windows

Stores dedupe relationships in deduplicated_alerts table.
Original alerts preserved; dedupe metadata is a side table.
"""

import uuid
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.alerts import Alert, DeduplicatedAlert
from backend.app.models.logs import RawLog

settings = get_settings()

SAME_SERVICE_WINDOW_MIN = settings.dedup_same_service_window_minutes  # 5
SHARED_TRACE_WINDOW_MIN = settings.dedup_shared_trace_window_minutes  # 2
MAX_COMPONENT_MIN = settings.dedup_max_component_minutes  # 15


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
        # Find trace_ids from logs in the alert's event-time window. The alert
        # may reference several anomaly rows, but the trace query is identical
        # for all of them and must only run once.
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
        trace_ids: set[uuid.UUID] = {trace_id for trace_id in logs if trace_id is not None}

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
    all_alerts = list(
        session.execute(select(Alert).order_by(Alert.start_window.asc(), Alert.id.asc()))
        .scalars()
        .all()
    )
    if not all_alerts:
        return 0

    parent = {alert.id: alert.id for alert in all_alerts}
    component_start = {alert.id: alert.start_window for alert in all_alerts}
    component_end = {alert.id: alert.end_window for alert in all_alerts}

    def find(alert_id: uuid.UUID) -> uuid.UUID:
        while parent[alert_id] != alert_id:
            parent[alert_id] = parent[parent[alert_id]]
            alert_id = parent[alert_id]
        return alert_id

    def union(left: uuid.UUID, right: uuid.UUID) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return

        combined_start = min(component_start[left_root], component_start[right_root])
        combined_end = max(component_end[left_root], component_end[right_root])
        if combined_end - combined_start > timedelta(minutes=MAX_COMPONENT_MIN):
            return

        parent[right_root] = left_root
        component_start[left_root] = combined_start
        component_end[left_root] = combined_end

    existing_rows = session.execute(select(DeduplicatedAlert)).scalars().all()

    # Rule 1: interval sweep within each service/type group. This replaces an
    # alert-by-alert database query with deterministic in-memory comparisons.
    same_service_groups: dict[tuple[uuid.UUID, str], list[Alert]] = defaultdict(list)
    for alert in all_alerts:
        same_service_groups[(alert.service_id, alert.anomaly_type)].append(alert)

    same_service_padding = timedelta(minutes=SAME_SERVICE_WINDOW_MIN)
    for alerts in same_service_groups.values():
        alerts.sort(key=lambda row: (row.start_window, str(row.id)))
        for left_index, left in enumerate(alerts):
            for right in alerts[left_index + 1 :]:
                if right.start_window > left.end_window + same_service_padding:
                    break
                if right.end_window >= left.start_window - same_service_padding:
                    union(left.id, right.id)

    # Rule 2: load trace-bearing logs once, map each trace to nearby alerts,
    # then sweep within each trace. Complexity is driven by actual shared
    # traces instead of every possible pair of alerts.
    trace_padding = timedelta(minutes=SHARED_TRACE_WINDOW_MIN)
    earliest = min(alert.start_window for alert in all_alerts) - trace_padding
    latest = max(alert.end_window for alert in all_alerts) + trace_padding
    log_rows = session.execute(
        select(RawLog.service_id, RawLog.timestamp, RawLog.trace_id)
        .where(
            RawLog.trace_id.isnot(None),
            RawLog.timestamp >= earliest,
            RawLog.timestamp <= latest,
        )
        .order_by(RawLog.service_id, RawLog.timestamp)
    ).all()

    service_log_times: dict[uuid.UUID, list[datetime]] = defaultdict(list)
    service_log_traces: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for service_id, timestamp, trace_id in log_rows:
        if trace_id is not None:
            service_log_times[service_id].append(timestamp)
            service_log_traces[service_id].append(trace_id)

    trace_to_alerts: dict[uuid.UUID, list[Alert]] = defaultdict(list)
    for alert in all_alerts:
        timestamps = service_log_times.get(alert.service_id, [])
        traces = service_log_traces.get(alert.service_id, [])
        start_index = bisect_left(timestamps, alert.start_window)
        end_index = bisect_right(timestamps, alert.end_window)
        for trace_id in set(traces[start_index:end_index]):
            trace_to_alerts[trace_id].append(alert)

    for trace_alerts in trace_to_alerts.values():
        unique_alerts = list({alert.id: alert for alert in trace_alerts}.values())
        unique_alerts.sort(key=lambda row: (row.start_window, str(row.id)))
        for left_index, left in enumerate(unique_alerts):
            for right in unique_alerts[left_index + 1 :]:
                if right.start_window > left.end_window + trace_padding:
                    break
                if (
                    right.service_id != left.service_id
                    and right.end_window >= left.start_window - trace_padding
                ):
                    union(left.id, right.id)

    components: dict[uuid.UUID, list[Alert]] = {}
    for alert in all_alerts:
        components.setdefault(find(alert.id), []).append(alert)

    expected: dict[tuple[uuid.UUID, uuid.UUID], str] = {}
    for members in components.values():
        if len(members) < 2:
            continue
        canonical = min(members, key=lambda row: (row.start_window, str(row.id)))
        for duplicate in members:
            if duplicate.id == canonical.id:
                continue
            reason = (
                "same_service_overlap"
                if duplicate.service_id == canonical.service_id
                and duplicate.anomaly_type == canonical.anomaly_type
                else "shared_trace_id"
            )
            expected[(canonical.id, duplicate.id)] = reason

    existing_by_pair = {
        (row.canonical_alert_id, row.duplicate_alert_id): row for row in existing_rows
    }
    for pair, row in existing_by_pair.items():
        if pair not in expected:
            session.delete(row)

    dedup_count = 0
    for pair, reason in expected.items():
        if pair in existing_by_pair:
            existing_by_pair[pair].dedupe_reason = reason
            continue
        session.add(
            DeduplicatedAlert(
                canonical_alert_id=pair[0],
                duplicate_alert_id=pair[1],
                dedupe_reason=reason,
            )
        )
        dedup_count += 1

    session.commit()
    return dedup_count
