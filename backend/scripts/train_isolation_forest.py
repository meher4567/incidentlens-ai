"""
Train Isolation Forest models on normal (non-incident) traffic windows.

For each service, collects metric windows that fall outside any incident window
(per incident_truth), trains an IsolationForest, and saves to models/if_{service}.pkl.

Usage:
    python -m backend.scripts.train_isolation_forest
"""

import argparse
import pickle
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import SyncSessionLocal
from backend.app.models.metrics import MetricWindow
from backend.app.models.ml_meta import ModelVersion
from backend.app.models.services import Service
from backend.app.models.truth import IncidentTruth
from backend.app.services.detection import IF_WINDOW_SIZE_SECONDS

settings = get_settings()

FEATURE_COLS = [
    "request_count",
    "error_rate",
    "p95_latency_ms",
    "unique_messages",
]


def load_truth_windows(session: Session) -> list[tuple[datetime, datetime]]:
    """
    Load incident time windows from incident_truth table.
    Returns list of (start_time, end_time) tuples.
    """
    truth_rows = session.execute(select(IncidentTruth)).scalars().all()
    windows = []
    for row in truth_rows:
        if row.start_time and row.end_time:
            windows.append((row.start_time, row.end_time))
    return windows


def is_normal_window(
    window_start: datetime,
    window_size_seconds: int,
    incident_windows: list[tuple[datetime, datetime]],
) -> bool:
    """
    A window is 'normal' if it does NOT overlap with any incident window.
    """
    window_end = window_start + timedelta(seconds=window_size_seconds)
    for istart, iend in incident_windows:
        # Check overlap
        if window_start < iend and window_end > istart:
            return False
    return True


def get_normal_windows(
    session: Session,
    service_id: uuid.UUID,
    window_size_seconds: int,
    incident_windows: list[tuple[datetime, datetime]],
) -> list[MetricWindow]:
    """
    Get all metric windows for a service that are outside incident periods.
    """
    all_windows = (
        session.execute(
            select(MetricWindow)
            .where(
                MetricWindow.service_id == service_id,
                MetricWindow.window_size_seconds == window_size_seconds,
            )
            .order_by(MetricWindow.window_start.asc())
        )
        .scalars()
        .all()
    )

    normal = []
    for mw in all_windows:
        if is_normal_window(mw.window_start, mw.window_size_seconds, incident_windows):
            normal.append(mw)
    return normal


def build_feature_matrix(windows: list[MetricWindow]) -> np.ndarray:
    """
    Build feature matrix from metric windows.
    """
    rows = []
    for mw in windows:
        er = float(mw.error_rate) if mw.error_rate is not None else 0.0
        p95 = float(mw.p95_latency_ms) if mw.p95_latency_ms is not None else 0.0
        rows.append(
            [
                float(mw.request_count),
                er,
                p95,
                float(mw.unique_messages),
            ]
        )
    if not rows:
        return np.empty((0, len(FEATURE_COLS)))
    return np.array(rows)


def train_if_for_service(
    session: Session,
    service: Service,
    incident_windows: list[tuple[datetime, datetime]],
    models_dir: Path,
    contamination: float = 0.05,
) -> Optional[dict]:
    """
    Train Isolation Forest for a single service.
    Returns training metadata dict or None if insufficient data.
    """
    # Use 5-minute windows (more stable features)
    windows = get_normal_windows(session, service.id, IF_WINDOW_SIZE_SECONDS, incident_windows)

    if len(windows) < 10:
        print(
            f"  {service.name}: insufficient {IF_WINDOW_SIZE_SECONDS}s normal "
            f"windows ({len(windows)}), skipping"
        )
        return None

    X = build_feature_matrix(windows)
    if X.shape[0] < 10:
        print(f"  {service.name}: insufficient feature rows ({X.shape[0]}), skipping")
        return None

    # Remove rows with NaN/Inf
    valid_mask = np.isfinite(X).all(axis=1)
    X = X[valid_mask]

    if X.shape[0] < 10:
        print(f"  {service.name}: insufficient valid rows after filtering ({X.shape[0]}), skipping")
        return None

    model = IsolationForest(
        n_estimators=100,
        contamination=contamination,
        random_state=settings.seed,
        n_jobs=-1,
    )
    model.fit(X)

    # Save model
    model_path = models_dir / f"if_{service.name}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    # Record model version
    mv = ModelVersion(
        model_name=f"isolation_forest_{service.name}",
        model_type="isolation_forest",
        service_name=service.name,
        file_path=str(model_path),
        training_params={
            "n_estimators": 100,
            "contamination": contamination,
            "random_state": settings.seed,
            "feature_cols": FEATURE_COLS,
            "window_size_seconds": IF_WINDOW_SIZE_SECONDS,
        },
        metrics={
            "n_samples": int(X.shape[0]),
            "n_features": int(X.shape[1]),
        },
    )
    session.add(mv)
    session.commit()

    return {
        "service": service.name,
        "n_samples": X.shape[0],
        "model_path": str(model_path),
    }


def train_models(contamination: float = 0.05) -> list[dict]:
    """Train per-service Isolation Forest models and save to models/."""
    models_dir = Path(settings.models_dir)
    models_dir.mkdir(exist_ok=True)

    session = SyncSessionLocal()
    try:
        print("=== Isolation Forest Training ===\n")

        incident_windows = load_truth_windows(session)
        print(f"Loaded {len(incident_windows)} incident windows from truth data\n")

        if not incident_windows:
            raise RuntimeError("incident truth is required for leakage-safe IF training")

        services = session.execute(select(Service)).scalars().all()
        if not services:
            raise RuntimeError("no services are available for IF training")
        print(f"Training IF models for {len(services)} services:\n")

        results = []
        for svc in services:
            meta = train_if_for_service(
                session,
                svc,
                incident_windows,
                models_dir,
                contamination=contamination,
            )
            if meta:
                results.append(meta)
                print(f"  ✓ {svc.name}: {meta['n_samples']} samples -> {meta['model_path']}")
            else:
                print(f"  ✗ {svc.name}: skipped")

        print(f"\nTrained {len(results)}/{len(services)} models")
        print(f"Models saved to {models_dir}/")
        if len(results) != len(services):
            raise RuntimeError(
                f"IF training contract failed: trained {len(results)}/{len(services)} models"
            )
        return results

    except Exception as exc:
        session.rollback()
        print(f"Training failed: {exc}")
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Train Isolation Forest models")
    parser.add_argument(
        "--contamination",
        type=float,
        default=0.05,
        help="Expected contamination fraction (default: 0.05)",
    )
    args = parser.parse_args()
    train_models(contamination=args.contamination)


if __name__ == "__main__":
    main()
