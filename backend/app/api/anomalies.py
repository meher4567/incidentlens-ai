from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import get_sync_session
from backend.app.models.anomalies import Anomaly
from backend.app.schemas.anomalies import AnomalyResponse

router = APIRouter()


@router.get("", response_model=list[AnomalyResponse])
async def list_anomalies(
    service_id: str | None = Query(None),
    metric: str | None = Query(None),
    detector: str | None = Query(None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_sync_session),
):
    """List anomalies with optional filters."""
    stmt = select(Anomaly)
    if service_id:
        stmt = stmt.where(Anomaly.service_id == service_id)
    if metric:
        stmt = stmt.where(Anomaly.metric == metric)
    if detector:
        stmt = stmt.where(Anomaly.detector == detector)

    stmt = stmt.order_by(Anomaly.created_at.desc()).offset(offset).limit(limit)
    return session.execute(stmt).scalars().all()
