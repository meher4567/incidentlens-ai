import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import get_sync_session
from backend.app.models.alerts import Alert, DeduplicatedAlert
from backend.app.schemas.alerts import AlertResponse

router = APIRouter()


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    service_id: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_sync_session),
):
    """List canonical (non-duplicate) alerts."""
    # Get canonical alerts (those NOT in deduplicated_alerts as duplicate)
    subquery = select(DeduplicatedAlert.duplicate_alert_id)
    stmt = select(Alert).where(Alert.id.not_in(subquery))

    if service_id:
        stmt = stmt.where(Alert.service_id == service_id)
    if severity:
        stmt = stmt.where(Alert.severity == severity)

    stmt = stmt.order_by(Alert.created_at.desc()).offset(offset).limit(limit)
    return session.execute(stmt).scalars().all()


@router.get("/all", response_model=list[AlertResponse])
async def list_all_alerts(
    service_id: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_sync_session),
):
    """List all alerts including duplicates."""
    stmt = select(Alert)
    if service_id:
        stmt = stmt.where(Alert.service_id == service_id)
    if severity:
        stmt = stmt.where(Alert.severity == severity)

    stmt = stmt.order_by(Alert.created_at.desc()).offset(offset).limit(limit)
    return session.execute(stmt).scalars().all()


@router.get("/{alert_id}")
async def get_alert(
    alert_id: uuid.UUID,
    session: Session = Depends(get_sync_session),
):
    """Get an alert with its duplicate information."""
    alert = session.execute(select(Alert).where(Alert.id == alert_id)).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Get duplicates (alerts deduped against this one as either canonical or duplicate)
    canonical_for = (
        session.execute(
            select(DeduplicatedAlert).where(DeduplicatedAlert.canonical_alert_id == alert_id)
        )
        .scalars()
        .all()
    )
    duplicated_to = (
        session.execute(
            select(DeduplicatedAlert).where(DeduplicatedAlert.duplicate_alert_id == alert_id)
        )
        .scalars()
        .all()
    )

    return {
        "alert": alert,
        "duplicates_of": canonical_for,
        "is_duplicate_of": duplicated_to,
    }
