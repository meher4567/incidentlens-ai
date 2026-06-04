import uuid
from datetime import datetime
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import get_sync_session
from backend.app.models.alerts import Alert
from backend.app.models.incidents import Incident, IncidentAlert, IncidentRootCauseScore
from backend.app.models.services import Service
from backend.app.schemas.incidents import (
    IncidentDetailResponse,
    IncidentResponse,
    RootCauseScoreResponse,
    TimelineEvent,
)

router = APIRouter()


class IncidentAlertPayload(TypedDict):
    id: uuid.UUID
    service_id: uuid.UUID
    service_name: str
    anomaly_type: str
    start_window: datetime
    end_window: datetime
    severity: str
    observed_value: float
    baseline_value: float


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    severity: str | None = Query(None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_sync_session),
):
    """List incidents."""
    stmt = select(Incident)
    if severity:
        stmt = stmt.where(Incident.severity == severity)

    stmt = stmt.order_by(Incident.created_at.desc()).offset(offset).limit(limit)
    incidents = session.execute(stmt).scalars().all()

    # Enrich with service names and alert counts
    result: list[IncidentResponse] = []
    service_name_map: dict[uuid.UUID, str] = {}
    for inc in incidents:
        # Resolve service names
        for sid in inc.affected_services:
            if sid not in service_name_map:
                svc = session.execute(
                    select(Service.name).where(Service.id == sid)
                ).scalar_one_or_none()
                service_name_map[sid] = svc or str(sid)

        # Count attached alerts
        alert_count = session.execute(
            select(IncidentAlert).where(IncidentAlert.incident_id == inc.id)
        ).fetchall()
        count = len(alert_count)

        result.append(
            IncidentResponse(
                id=inc.id,
                start_time=inc.start_time,
                end_time=inc.end_time,
                severity=inc.severity,
                affected_services=inc.affected_services,
                affected_service_names=[service_name_map[s] for s in inc.affected_services],
                alert_count=count,
                closed_at=inc.closed_at,
                created_at=inc.created_at,
            )
        )
    return result


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
async def get_incident(
    incident_id: uuid.UUID,
    session: Session = Depends(get_sync_session),
):
    """Get incident detail with alerts, root cause scores, and timeline."""
    incident = session.execute(
        select(Incident).where(Incident.id == incident_id)
    ).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Get attached alerts
    alert_links = (
        session.execute(select(IncidentAlert).where(IncidentAlert.incident_id == incident_id))
        .scalars()
        .all()
    )
    alert_ids = [a.alert_id for a in alert_links]

    alerts: list[IncidentAlertPayload] = []
    service_name_map: dict[uuid.UUID, str] = {}
    if alert_ids:
        alerts_objs = session.execute(select(Alert).where(Alert.id.in_(alert_ids))).scalars().all()
        for a in alerts_objs:
            if a.service_id not in service_name_map:
                svc = session.execute(
                    select(Service.name).where(Service.id == a.service_id)
                ).scalar_one_or_none()
                service_name_map[a.service_id] = svc or str(a.service_id)
            alerts.append(
                {
                    "id": a.id,
                    "service_id": a.service_id,
                    "service_name": service_name_map[a.service_id],
                    "anomaly_type": a.anomaly_type,
                    "start_window": a.start_window,
                    "end_window": a.end_window,
                    "severity": str(a.severity),
                    "observed_value": float(a.observed_value),
                    "baseline_value": float(a.baseline_value),
                }
            )

    # Get root cause scores
    scores = (
        session.execute(
            select(IncidentRootCauseScore)
            .where(IncidentRootCauseScore.incident_id == incident_id)
            .order_by(IncidentRootCauseScore.rank.asc())
        )
        .scalars()
        .all()
    )

    root_cause_scores = []
    for sc in scores:
        if sc.service_id not in service_name_map:
            svc = session.execute(
                select(Service.name).where(Service.id == sc.service_id)
            ).scalar_one_or_none()
            service_name_map[sc.service_id] = svc or str(sc.service_id)
        root_cause_scores.append(
            RootCauseScoreResponse(
                service_id=sc.service_id,
                service_name=service_name_map[sc.service_id],
                score=sc.score,
                rank=sc.rank,
                feature_vector=sc.feature_vector,
                feature_contributions=sc.feature_contributions,
            )
        )

    # Build timeline: sort alerts by start_window, note upstream/downstream
    timeline: list[TimelineEvent] = []
    for alert_data in sorted(alerts, key=lambda x: x["start_window"]):
        timeline.append(
            TimelineEvent(
                alert_id=alert_data["id"],
                service_name=alert_data["service_name"],
                anomaly_type=alert_data["anomaly_type"],
                start_window=alert_data["start_window"],
                severity=alert_data["severity"],
            )
        )

    return IncidentDetailResponse(
        id=incident.id,
        start_time=incident.start_time,
        end_time=incident.end_time,
        severity=incident.severity,
        affected_services=incident.affected_services,
        affected_service_names=[
            service_name_map.get(s, str(s)) for s in incident.affected_services
        ],
        alert_count=len(alerts),
        closed_at=incident.closed_at,
        created_at=incident.created_at,
        alerts=[dict(alert) for alert in alerts],
        root_cause_scores=root_cause_scores,
        timeline=timeline,
    )
