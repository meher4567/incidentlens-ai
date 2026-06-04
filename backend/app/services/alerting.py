"""
Alert generation service.

Converts anomalies into alerts with debounce (5-min same service+type)
and severity grading. Emits alert rows referencing underlying anomalies.
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.alerts import Alert
from backend.app.models.anomalies import Anomaly

DEBOUNCE_MINUTES = 5

# Anomaly type derivation from (metric, direction)
ANOMALY_TYPE_MAP = {
    ("error_rate", "positive"): "error_rate_spike",
    ("p95_latency_ms", "positive"): "latency_spike",
    ("request_count", "positive"): "traffic_spike",
    ("request_count", "negative"): "traffic_drop",
}


def _derive_anomaly_type(metric: str, score: float) -> str:
    direction = "positive" if score >= 0 else "negative"
    return ANOMALY_TYPE_MAP.get((metric, direction), f"{metric}_anomaly")


def process_new_anomalies(session: Session) -> int:
    """
    Process all anomalies that haven't yet been converted to alerts.
    Debounce: same service + anomaly_type within 5 minutes extends existing alert.
    Returns number of alerts created/updated.
    """
    # Find anomalies not yet referenced by any alert
    # Get all anomaly IDs already assigned to alerts
    exising_alert_rows = session.execute(select(Alert.anomaly_ids)).scalars().all()
    assigned_anomaly_ids: set[int] = set()
    for ids in exising_alert_rows:
        if ids:
            assigned_anomaly_ids.update(ids)

    anomaly_rows = (
        session.execute(
            select(Anomaly).where(
                ~Anomaly.id.in_(assigned_anomaly_ids) if assigned_anomaly_ids else True
            )
        )
        .scalars()
        .all()
    )

    if not anomaly_rows:
        return 0

    alerts_processed = 0

    for anomaly in anomaly_rows:
        anomaly_type = _derive_anomaly_type(anomaly.metric, anomaly.score)
        debounce_cutoff = anomaly.created_at - timedelta(minutes=DEBOUNCE_MINUTES)

        # Find existing open alert for same service + type within debounce window
        existing = (
            session.execute(
                select(Alert)
                .where(
                    Alert.service_id == anomaly.service_id,
                    Alert.anomaly_type == anomaly_type,
                    Alert.end_window >= debounce_cutoff,
                )
                .order_by(Alert.end_window.desc())
            )
            .scalars()
            .first()
        )

        if existing:
            # Extend existing alert
            existing.end_window = max(
                existing.end_window,
                anomaly.window_start + timedelta(seconds=anomaly.window_size_seconds),
            )
            # Update severity to max
            severities = ["MEDIUM", "HIGH", "CRITICAL"]
            existing_sev_idx = severities.index(str(existing.severity).upper())
            new_sev_idx = severities.index(str(anomaly.severity).upper())
            if new_sev_idx > existing_sev_idx:
                existing.severity = anomaly.severity
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
                severity=anomaly.severity.upper(),
                observed_value=anomaly.observed_value,
                baseline_value=anomaly.baseline_value,
                anomaly_ids=[anomaly.id],
            )
            session.add(alert)

        alerts_processed += 1

    session.commit()
    return alerts_processed
