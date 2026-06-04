import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.session import get_sync_session
from backend.app.models.anomalies import Anomaly, AnomalyDetector
from backend.app.models.incidents import Incident
from backend.app.models.logs import RawLog
from backend.app.models.metrics import MetricWindow
from backend.app.models.services import Service
from backend.app.models.truth import IncidentTruth
from backend.app.schemas.metrics import MetricWindowResponse, ServiceHealthResponse

router = APIRouter()

DETECTOR_RESPONSE_KEYS = {
    AnomalyDetector.MAD: "mad",
    AnomalyDetector.ISOLATION_FOREST: "isolation_forest",
}


@router.get("/services/{service_id}/health", response_model=ServiceHealthResponse)
async def get_service_health(
    service_id: uuid.UUID,
    window_size_seconds: int = Query(default=60, ge=60, le=300),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_sync_session),
):
    """Get service health metrics as time-series windows."""
    service = session.execute(select(Service).where(Service.id == service_id)).scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    stmt = select(MetricWindow).where(
        MetricWindow.service_id == service_id,
        MetricWindow.window_size_seconds == window_size_seconds,
    )
    if start_time:
        stmt = stmt.where(MetricWindow.window_start >= start_time)
    if end_time:
        stmt = stmt.where(MetricWindow.window_start <= end_time)

    stmt = stmt.order_by(MetricWindow.window_start.asc()).limit(limit)
    windows = session.execute(stmt).scalars().all()

    return ServiceHealthResponse(
        service_id=service.id,
        service_name=service.name,
        windows=[MetricWindowResponse.model_validate(w) for w in windows],
        window_size_seconds=window_size_seconds,
    )


@router.get("/")
async def get_metrics_overview(
    session: Session = Depends(get_sync_session),
):
    """Get system-wide overview metrics."""
    now = datetime.now(timezone.utc)

    # Total logs
    total_logs = session.execute(select(func.count(RawLog.id))).scalar() or 0

    # Recent ingestion rate (logs in last 5 minutes)
    five_min_ago = now - timedelta(minutes=5)
    recent_events = (
        session.execute(
            select(func.count(RawLog.id)).where(RawLog.ingested_at >= five_min_ago)
        ).scalar()
        or 0
    )

    # Queue depth (estimate: logs not yet in metric windows)
    queue_depth = (
        session.execute(
            select(func.count(RawLog.id)).where(RawLog.ingested_at >= now - timedelta(minutes=15))
        ).scalar()
        or 0
    )

    # Recent errors
    recent_errors = (
        session.execute(
            select(func.count(RawLog.id)).where(
                RawLog.level.in_(["ERROR", "CRITICAL"]),
                RawLog.ingested_at >= now - timedelta(minutes=15),
            )
        ).scalar()
        or 0
    )

    # Total services
    total_services = session.execute(select(func.count(Service.id))).scalar() or 0

    # Active incidents
    active_incidents = (
        session.execute(
            select(func.count()).select_from(Incident).where(Incident.closed_at.is_(None))
        ).scalar()
        or 0
    )

    return {
        "total_logs": total_logs,
        "recent_events_per_min": round(recent_events / 5.0, 1) if recent_events > 0 else 0,
        "queue_depth": queue_depth,
        "recent_errors": recent_errors,
        "total_services": total_services,
        "active_incidents": active_incidents,
    }


@router.get("/pr-curves")
async def get_pr_curves(
    session: Session = Depends(get_sync_session),
):
    """Get PR curve data for MAD vs Isolation Forest comparison."""
    truth_rows = session.execute(select(IncidentTruth)).scalars().all()
    incident_windows = [
        (t.start_time, t.end_time) for t in truth_rows if t.start_time and t.end_time
    ]

    result: dict[str, list[dict[str, float]]] = {}

    for detector in [AnomalyDetector.MAD, AnomalyDetector.ISOLATION_FOREST]:
        detector_key = DETECTOR_RESPONSE_KEYS[detector]
        anomalies = (
            session.execute(
                select(Anomaly).where(Anomaly.detector == detector).order_by(Anomaly.score.desc())
            )
            .scalars()
            .all()
        )

        # Build PR curve points
        scores = []
        labels = []
        for a in anomalies:
            window_end = a.window_start + timedelta(seconds=a.window_size_seconds)
            in_incident = False
            for istart, iend in incident_windows:
                if a.window_start < iend and window_end > istart:
                    in_incident = True
                    break
            scores.append(float(a.score))
            labels.append(1 if in_incident else 0)

        points = []
        sorted_pairs = sorted(zip(scores, labels), key=lambda x: x[0], reverse=True)
        step = max(1, len(sorted_pairs) // 100)

        for threshold_idx in range(0, len(sorted_pairs), step):
            thresh_pairs = sorted_pairs[: threshold_idx + 1]
            if not thresh_pairs:
                continue
            tp_th = sum(1 for _, l in thresh_pairs if l == 1)
            fp_th = sum(1 for _, l in thresh_pairs if l == 0)
            fn_th = sum(1 for _, l in sorted_pairs[threshold_idx + 1 :] if l == 1)
            p = tp_th / (tp_th + fp_th) if (tp_th + fp_th) > 0 else 1.0
            r = tp_th / (tp_th + fn_th) if (tp_th + fn_th) > 0 else 0.0
            points.append({"precision": round(p, 4), "recall": round(r, 4)})

        result[detector_key] = points

    # Summary stats
    summary: dict[str, dict[str, float]] = {}
    for detector in [AnomalyDetector.MAD, AnomalyDetector.ISOLATION_FOREST]:
        detector_key = DETECTOR_RESPONSE_KEYS[detector]
        anomalies = (
            session.execute(select(Anomaly).where(Anomaly.detector == detector)).scalars().all()
        )
        if anomalies:
            anom_set = set()
            for a in anomalies:
                anom_set.add((a.service_id, a.window_start, a.window_size_seconds))
            tp = fp = fn = 0
            windows = session.execute(select(MetricWindow)).scalars().all()
            for mw in windows:
                window_end = mw.window_start + timedelta(seconds=mw.window_size_seconds)
                key = (mw.service_id, mw.window_start, mw.window_size_seconds)
                is_anom = key in anom_set
                in_inc = any(
                    mw.window_start < iend and window_end > istart
                    for istart, iend in incident_windows
                )
                if in_inc:
                    if is_anom:
                        tp += 1
                    else:
                        fn += 1
                else:
                    if is_anom:
                        fp += 1
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0
            summary[detector_key] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
            }
        else:
            summary[detector_key] = {"precision": 0, "recall": 0, "f1": 0}

    return {
        "mad": result.get(DETECTOR_RESPONSE_KEYS[AnomalyDetector.MAD], []),
        "isolation_forest": result.get(
            DETECTOR_RESPONSE_KEYS[AnomalyDetector.ISOLATION_FOREST],
            [],
        ),
        "summary": summary,
    }
