"""
Anomaly detection service.

Implements two methods:
1. MAD robust z-score (primary, interpretable)
2. Isolation Forest (comparator, multi-metric)

Both detectors record scores per (service, metric, window) for PR-curve comparison.
"""
import pickle
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
from sklearn.ensemble import IsolationForest  # noqa: F401 - used in type annotations
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.anomalies import Anomaly, AnomalyDetector
from backend.app.models.metrics import MetricWindow

if TYPE_CHECKING:
    from sklearn.ensemble import IsolationForest as IsolationForestType
else:
    IsolationForestType = IsolationForest

settings = get_settings()

MAD_SCALE = 0.6745  # Scale MAD to be comparable to standard deviation
DEFAULT_THRESHOLD = settings.mad_threshold_default  # 4.0


def compute_mad_zscore(observed: float, median: float, mad: float) -> Optional[float]:
    """Compute robust z-score = 0.6745 * (observed - median) / MAD."""
    if mad is None or mad == 0 or observed is None or median is None:
        return None
    return MAD_SCALE * (float(observed) - float(median)) / float(mad)


def detect_mad(
    session: Session,
    metric_window: MetricWindow,
) -> list[dict]:
    """
    Run MAD detection on a single metric window.
    Returns list of anomaly dicts ready for insertion.
    """
    anomalies = []
    mw = metric_window

    # Define metrics to check: (metric_name, observed_value, baseline_median, baseline_mad, positive_only)
    metrics_to_check = [
        (
            "request_count",
            mw.request_count,
            mw.baseline_request_count_median,
            mw.baseline_request_count_mad,
            False,
        ),
        (
            "error_rate",
            float(mw.error_rate) if mw.error_rate is not None else None,
            mw.baseline_error_rate_median,
            mw.baseline_error_rate_mad,
            True,
        ),
        (
            "p95_latency_ms",
            mw.p95_latency_ms,
            mw.baseline_p95_latency_median,
            mw.baseline_p95_latency_mad,
            True,
        ),
    ]

    for metric_name, observed, median, mad, positive_only in metrics_to_check:
        if observed is None or median is None or mad is None or mad == 0:
            continue

        z_score = compute_mad_zscore(observed, median, mad)
        if z_score is None:
            continue

        # Direction handling & threshold
        if positive_only:
            # For error_rate and p95_latency, only positive spikes are anomalies
            if z_score < DEFAULT_THRESHOLD:
                continue
        else:
            # For request_count, both positive spikes and negative drops are anomalous
            if abs(z_score) < DEFAULT_THRESHOLD:
                continue

        # Severity
        abs_z = abs(z_score)
        if abs_z >= 6.0:
            severity = "CRITICAL"
        elif abs_z >= 4.0:
            severity = "HIGH"
        else:
            severity = "MEDIUM"

        anomalies.append(
            {
                "service_id": mw.service_id,
                "metric": metric_name,
                "window_start": mw.window_start,
                "window_size_seconds": mw.window_size_seconds,
                "detector": AnomalyDetector.MAD.value,
                "score": round(z_score, 4),
                "observed_value": round(float(observed), 4),
                "baseline_value": round(float(median), 4),
                "severity": severity,
            }
        )

    return anomalies


def upsert_anomaly(session: Session, anomaly_dict: dict) -> None:
    """UPSERT an anomaly row (idempotent by unique constraint)."""
    if session.get_bind().dialect.name != "postgresql":
        existing = session.execute(
            select(Anomaly).where(
                Anomaly.service_id == anomaly_dict["service_id"],
                Anomaly.metric == anomaly_dict["metric"],
                Anomaly.window_start == anomaly_dict["window_start"],
                Anomaly.window_size_seconds == anomaly_dict["window_size_seconds"],
                Anomaly.detector == anomaly_dict["detector"],
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(Anomaly(**anomaly_dict))
        else:
            for key in ("score", "observed_value", "baseline_value", "severity"):
                setattr(existing, key, anomaly_dict[key])
        return

    stmt = pg_insert(Anomaly).values(**anomaly_dict)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_anomaly",
        set_={
            "score": stmt.excluded.score,
            "observed_value": stmt.excluded.observed_value,
            "baseline_value": stmt.excluded.baseline_value,
            "severity": stmt.excluded.severity,
        },
    )
    session.execute(stmt)


def detect_isolation_forest(
    session: Session,
    metric_window: MetricWindow,
    if_models: dict[uuid.UUID, "IsolationForest"],
) -> list[dict]:
    """
    Run Isolation Forest detection on a single metric window.
    Uses per-service IF model. Returns list of anomaly dicts.
    """

    anomalies = []
    mw = metric_window

    if_model = if_models.get(mw.service_id)
    if if_model is None:
        return anomalies

    # Build feature vector
    er = float(mw.error_rate) if mw.error_rate is not None else 0.0
    p95 = float(mw.p95_latency_ms) if mw.p95_latency_ms is not None else 0.0
    X = np.array(
        [
            [
                float(mw.request_count),
                er,
                p95,
                float(mw.unique_messages),
            ]
        ]
    )

    # Check for NaN/Inf
    if not np.isfinite(X).all():
        return anomalies

    try:
        score = float(if_model.decision_function(X)[0])
        pred = int(if_model.predict(X)[0])
    except Exception:
        return anomalies

    # IF returns -1 for anomaly, 1 for normal
    if pred != -1:
        return anomalies

    # Convert score to anomaly score (negative = more anomalous)
    # Invert so higher = more anomalous (consistent with z-score)
    anomaly_score = -score

    # Determine severity based on score percentile
    if anomaly_score > 0.2:
        severity = "CRITICAL"
    elif anomaly_score > 0.1:
        severity = "HIGH"
    else:
        severity = "MEDIUM"

    # Record an anomaly for each metric type (for comparison)
    metrics_to_check = [
        (
            "request_count",
            mw.request_count,
            mw.baseline_request_count_median,
            mw.baseline_request_count_mad,
        ),
        (
            "error_rate",
            float(mw.error_rate) if mw.error_rate is not None else None,
            mw.baseline_error_rate_median,
            mw.baseline_error_rate_mad,
        ),
        (
            "p95_latency_ms",
            mw.p95_latency_ms,
            mw.baseline_p95_latency_median,
            mw.baseline_p95_latency_mad,
        ),
    ]

    for metric_name, observed, median, mad in metrics_to_check:
        if observed is None or median is None or mad is None or mad == 0:
            continue

        z_score = compute_mad_zscore(observed, median, mad)
        if z_score is None:
            z_score = anomaly_score  # fallback

        anomalies.append(
            {
                "service_id": mw.service_id,
                "metric": metric_name,
                "window_start": mw.window_start,
                "window_size_seconds": mw.window_size_seconds,
                "detector": AnomalyDetector.ISOLATION_FOREST.value,
                "score": round(anomaly_score, 4),
                "observed_value": round(float(observed), 4),
                "baseline_value": round(float(median), 4),
                "severity": severity,
            }
        )

    return anomalies


def load_if_models(session: Session | None = None) -> dict[uuid.UUID, "IsolationForest"]:
    """
    Load all saved Isolation Forest models.
    Returns dict mapping service_id -> IF model.
    """

    from backend.app.db.session import SyncSessionLocal
    from backend.app.models.ml_meta import ModelVersion
    from backend.app.models.services import Service

    models_dir = Path(settings.models_dir)
    if not models_dir.exists():
        return {}

    owns_session = session is None
    db_session = session or SyncSessionLocal()
    try:
        if_versions = (
            db_session.execute(
                select(ModelVersion)
                .where(ModelVersion.model_type == "isolation_forest")
                .order_by(ModelVersion.trained_at.desc())
            )
            .scalars()
            .all()
        )

        if not if_versions:
            return {}

        services = db_session.execute(select(Service)).scalars().all()
        name_to_id = {s.name: s.id for s in services}
    finally:
        if owns_session:
            db_session.close()

    models: dict[uuid.UUID, "IsolationForest"] = {}
    for mv in if_versions:
        model_path = Path(mv.file_path)
        if not model_path.exists():
            continue
        try:
            with open(model_path, "rb") as f:
                model = pickle.load(f)
            if mv.service_name and mv.service_name in name_to_id:
                models[name_to_id[mv.service_name]] = model
        except Exception:
            continue

    return models


def run_detection_all(session: Session) -> int:
    """
    Run detection (MAD + IF) on all metric windows
    that haven't been scored yet. Returns count of anomalies detected.
    """
    # Load IF models
    if_models = load_if_models(session)
    if not if_models:
        print("[warning] No IF models found, running MAD only. Run 'make train-if' first.")

    # Find windows that haven't been scored yet
    windows = (
        session.execute(
            select(MetricWindow)
            .where(
                MetricWindow.closed_at.isnot(None),
            )
            .order_by(MetricWindow.window_start.asc())
        )
        .scalars()
        .all()
    )

    total_anomalies = 0

    for mw in windows:
        # Run MAD detection - UPSERT handles idempotency
        mad_anomalies = detect_mad(session, mw)
        for a in mad_anomalies:
            upsert_anomaly(session, a)
            total_anomalies += 1

        # IF detection (separate detector) - UPSERT handles idempotency
        if if_models:
            if_anomalies = detect_isolation_forest(session, mw, if_models)
            for a in if_anomalies:
                upsert_anomaly(session, a)
                total_anomalies += 1

    session.commit()
    return total_anomalies
