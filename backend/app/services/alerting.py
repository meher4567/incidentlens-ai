"""
Alert generation service.

Converts anomalies into alerts with debounce (5-min same service+type)
and severity grading. Emits alert rows referencing underlying anomalies.
"""

import uuid
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.alerts import Alert, IncidentSeverity
from backend.app.models.anomalies import Anomaly

settings = get_settings()
DEBOUNCE_MINUTES = settings.dedup_same_service_window_minutes
MAX_ALERT_DURATION_MINUTES = settings.alert_max_duration_minutes

# Anomaly type derivation from (metric, direction)
ANOMALY_TYPE_MAP = {
    ("error_rate", "positive"): "error_rate_spike",
    ("p95_latency_ms", "positive"): "latency_spike",
    ("request_count", "positive"): "traffic_spike",
    ("request_count", "negative"): "traffic_drop",
}


def _enum_value(value: object) -> str:
    """Return a stable string for SQLAlchemy enums and plain strings."""
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def _derive_anomaly_type(metric: str, score: float) -> str:
    direction = "positive" if score >= 0 else "negative"
    return ANOMALY_TYPE_MAP.get((metric, direction), f"{metric}_anomaly")


def process_new_anomalies(session: Session) -> int:
    """
    Process all anomalies that haven't yet been converted to alerts.
    Debounce: same service + anomaly_type within 5 minutes extends existing alert.
    Returns number of alerts created/updated.
    """
    # Load alerts once. Besides avoiding an N+1 query, keeping new alerts in
    # this cache makes debounce correct when the Session has autoflush=False.
    existing_alerts = list(
        session.execute(select(Alert).order_by(Alert.start_window.asc())).scalars().all()
    )
    assigned_anomaly_ids: set[int] = set()
    alerts_by_key: dict[tuple[uuid.UUID, str], list[Alert]] = defaultdict(list)
    for alert in existing_alerts:
        if alert.anomaly_ids:
            assigned_anomaly_ids.update(alert.anomaly_ids)
        alerts_by_key[(alert.service_id, alert.anomaly_type)].append(alert)

    anomaly_stmt = select(Anomaly)
    if assigned_anomaly_ids:
        anomaly_stmt = anomaly_stmt.where(~Anomaly.id.in_(assigned_anomaly_ids))
    anomaly_rows = (
        session.execute(anomaly_stmt.order_by(Anomaly.window_start.asc(), Anomaly.id.asc()))
        .scalars()
        .all()
    )

    if not anomaly_rows:
        return 0

    alerts_processed = 0

    for anomaly in anomaly_rows:
        anomaly_type = _derive_anomaly_type(anomaly.metric, anomaly.score)
        debounce_cutoff = anomaly.window_start - timedelta(minutes=DEBOUNCE_MINUTES)
        debounce_end = anomaly.window_start + timedelta(minutes=DEBOUNCE_MINUTES)

        # Find the most recent matching alert, including alerts created earlier
        # in this uncommitted batch.
        key = (anomaly.service_id, anomaly_type)
        existing = next(
            (
                alert
                for alert in reversed(alerts_by_key[key])
                if alert.end_window >= debounce_cutoff
                and alert.start_window <= debounce_end
                and anomaly.window_start + timedelta(seconds=anomaly.window_size_seconds)
                <= alert.start_window + timedelta(minutes=MAX_ALERT_DURATION_MINUTES)
            ),
            None,
        )

        if existing:
            # Extend existing alert
            existing.end_window = max(
                existing.end_window,
                anomaly.window_start + timedelta(seconds=anomaly.window_size_seconds),
            )
            # Update severity to max
            severities = ["MEDIUM", "HIGH", "CRITICAL"]
            existing_sev_idx = severities.index(_enum_value(existing.severity).upper())
            new_sev_idx = severities.index(_enum_value(anomaly.severity).upper())
            if new_sev_idx > existing_sev_idx:
                existing.severity = IncidentSeverity(_enum_value(anomaly.severity).upper())
            # Append anomaly_id
            if anomaly.id not in existing.anomaly_ids:
                existing.anomaly_ids = existing.anomaly_ids + [anomaly.id]
        else:
            # Create new alert
            alert = Alert(
                service_id=anomaly.service_id,
                anomaly_type=anomaly_type,
                start_window=anomaly.window_start,
                end_window=anomaly.window_start + timedelta(seconds=anomaly.window_size_seconds),
                severity=IncidentSeverity(str(anomaly.severity).upper()),
                observed_value=anomaly.observed_value,
                baseline_value=anomaly.baseline_value,
                anomaly_ids=[anomaly.id],
            )
            session.add(alert)
            alerts_by_key[key].append(alert)

        alerts_processed += 1

    session.commit()
    return alerts_processed
