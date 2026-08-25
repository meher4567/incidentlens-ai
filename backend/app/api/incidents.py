import uuid
from datetime import datetime
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.session import get_sync_session
from backend.app.models.alerts import Alert
from backend.app.models.incidents import Incident, IncidentAlert, IncidentRootCauseScore
from backend.app.models.services import Service
from backend.app.schemas.incidents import (
    IncidentBriefingResponse,
    IncidentDetailResponse,
    IncidentImpact,
    IncidentResponse,
    RootCauseScoreResponse,
    SuspectedRootCause,
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


def _confidence_from_score(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _format_duration_minutes(start_time: datetime, end_time: datetime | None) -> float | None:
    if end_time is None:
        return None
    return round(max((end_time - start_time).total_seconds(), 0) / 60, 1)


def _top_feature_names(score: RootCauseScoreResponse) -> list[str]:
    if not score.feature_contributions:
        return []
    return [
        name.replace("_", " ")
        for name, _ in sorted(
            score.feature_contributions.items(),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[:3]
    ]


def _build_incident_detail(session: Session, incident_id: uuid.UUID) -> IncidentDetailResponse:
    incident = session.execute(
        select(Incident).where(Incident.id == incident_id)
    ).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    alert_links = (
        session.execute(select(IncidentAlert).where(IncidentAlert.incident_id == incident_id))
        .scalars()
        .all()
    )
    alert_ids = [a.alert_id for a in alert_links]

    alerts: list[IncidentAlertPayload] = []
    relevant_service_ids = set(incident.affected_services)
    scores = (
        session.execute(
            select(IncidentRootCauseScore)
            .where(IncidentRootCauseScore.incident_id == incident_id)
            .order_by(IncidentRootCauseScore.rank.asc())
        )
        .scalars()
        .all()
    )
    relevant_service_ids.update(score.service_id for score in scores)

    if alert_ids:
        alerts_objs = session.execute(select(Alert).where(Alert.id.in_(alert_ids))).scalars().all()
        for a in alerts_objs:
            relevant_service_ids.add(a.service_id)

    service_rows = session.execute(
        select(Service.id, Service.name).where(Service.id.in_(relevant_service_ids))
    ).all()
    service_name_map = {service_id: name for service_id, name in service_rows}

    if alert_ids:
        for a in alerts_objs:
            alerts.append(
                {
                    "id": a.id,
                    "service_id": a.service_id,
                    "service_name": service_name_map.get(a.service_id, str(a.service_id)),
                    "anomaly_type": a.anomaly_type,
                    "start_window": a.start_window,
                    "end_window": a.end_window,
                    "severity": str(a.severity),
                    "observed_value": float(a.observed_value),
                    "baseline_value": float(a.baseline_value),
                }
            )

    root_cause_scores = []
    for sc in scores:
        root_cause_scores.append(
            RootCauseScoreResponse(
                service_id=sc.service_id,
                service_name=service_name_map.get(sc.service_id, str(sc.service_id)),
                score=sc.score,
                rank=sc.rank,
                feature_vector=sc.feature_vector,
                feature_contributions=sc.feature_contributions,
            )
        )

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


def _build_markdown_briefing(
    detail: IncidentDetailResponse,
    summary: str,
    suspected_root_cause: SuspectedRootCause,
    evidence: list[str],
    recommended_actions: list[str],
) -> str:
    evidence_lines = "\n".join(f"- {item}" for item in evidence)
    action_lines = "\n".join(f"- {item}" for item in recommended_actions)
    root_service = suspected_root_cause.service_name or "Not enough RCA data"
    return (
        "# Incident Briefing\n\n"
        f"**Incident:** `{detail.id}`\n"
        f"**Severity:** {detail.severity}\n"
        f"**Status:** {'closed' if detail.closed_at else 'active'}\n"
        f"**Affected services:** {', '.join(detail.affected_service_names) or 'unknown'}\n\n"
        f"## Summary\n{summary}\n\n"
        "## Suspected Root Cause\n"
        f"{root_service} ({suspected_root_cause.confidence} confidence). "
        f"{suspected_root_cause.why}\n\n"
        f"## Evidence\n{evidence_lines}\n\n"
        f"## Recommended Actions\n{action_lines}\n"
    )


def _build_incident_briefing(detail: IncidentDetailResponse) -> IncidentBriefingResponse:
    top_score = detail.root_cause_scores[0] if detail.root_cause_scores else None
    confidence = _confidence_from_score(top_score.score if top_score else None)
    affected = detail.affected_service_names
    root_service = top_score.service_name if top_score else None
    status = "closed" if detail.closed_at else "active"
    duration_minutes = _format_duration_minutes(detail.start_time, detail.end_time)

    if top_score:
        summary = (
            f"{detail.severity} incident affecting {len(affected)} service(s); "
            f"{top_score.service_name} is the top RCA candidate with {confidence} confidence."
        )
        top_features = _top_feature_names(top_score)
        why = (
            f"Top contributing signals: {', '.join(top_features)}."
            if top_features
            else "Ranked highest by the RCA model."
        )
    else:
        summary = (
            f"{detail.severity} incident affecting {len(affected)} service(s); "
            "RCA scoring has not run yet."
        )
        why = "No root-cause scores were available for this incident."

    suspected_root_cause = SuspectedRootCause(
        service_name=root_service,
        score=round(top_score.score, 4) if top_score else None,
        confidence=confidence,
        why=why,
    )

    evidence: list[str] = []
    if detail.timeline:
        first_event = detail.timeline[0]
        evidence.append(
            f"Earliest alert: {first_event.service_name} {first_event.anomaly_type} "
            f"at {first_event.start_window.isoformat()}."
        )
    if top_score and top_score.feature_contributions:
        ranked = ", ".join(_top_feature_names(top_score))
        evidence.append(f"RCA feature evidence emphasized: {ranked}.")
    if detail.alert_count:
        evidence.append(f"{detail.alert_count} alert(s) were clustered into this incident.")

    recommended_actions = [
        f"Check {root_service} deploys, saturation, and dependency errors first."
        if root_service
        else "Run the RCA ranking job before assigning ownership.",
        "Inspect earliest correlated traces and logs around the first alert window.",
        "Validate whether downstream services recover after the suspected root cause is mitigated.",
    ]

    impact = IncidentImpact(
        affected_services=affected,
        alert_count=detail.alert_count,
        duration_minutes=duration_minutes,
        status=status,
    )
    title = f"{detail.severity} incident on {root_service or 'unknown service'}"
    markdown = _build_markdown_briefing(
        detail,
        summary,
        suspected_root_cause,
        evidence,
        recommended_actions,
    )

    return IncidentBriefingResponse(
        incident_id=detail.id,
        title=title,
        status=status,
        severity=detail.severity,
        summary=summary,
        suspected_root_cause=suspected_root_cause,
        impact=impact,
        evidence=evidence,
        recommended_actions=recommended_actions,
        markdown=markdown,
    )


@router.get("", response_model=list[IncidentResponse])
def list_incidents(
    severity: str | None = Query(None, pattern="^(MEDIUM|HIGH|CRITICAL)$"),
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

    # Enrich in set-based queries to avoid one query per incident/service.
    result: list[IncidentResponse] = []
    incident_ids = [incident.id for incident in incidents]
    service_ids = {sid for incident in incidents for sid in incident.affected_services}
    service_rows = session.execute(
        select(Service.id, Service.name).where(Service.id.in_(service_ids))
    ).all()
    service_name_map = {service_id: name for service_id, name in service_rows}
    alert_count_rows = session.execute(
        select(IncidentAlert.incident_id, func.count(IncidentAlert.alert_id))
        .where(IncidentAlert.incident_id.in_(incident_ids))
        .group_by(IncidentAlert.incident_id)
    ).all()
    alert_counts = {incident_id: count for incident_id, count in alert_count_rows}

    for inc in incidents:
        result.append(
            IncidentResponse(
                id=inc.id,
                start_time=inc.start_time,
                end_time=inc.end_time,
                severity=inc.severity,
                affected_services=inc.affected_services,
                affected_service_names=[
                    service_name_map.get(service_id, str(service_id))
                    for service_id in inc.affected_services
                ],
                alert_count=alert_counts.get(inc.id, 0),
                closed_at=inc.closed_at,
                created_at=inc.created_at,
            )
        )
    return result


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
def get_incident(
    incident_id: uuid.UUID,
    session: Session = Depends(get_sync_session),
):
    """Get incident detail with alerts, root cause scores, and timeline."""
    return _build_incident_detail(session, incident_id)


@router.get("/{incident_id}/briefing", response_model=IncidentBriefingResponse)
def get_incident_briefing(
    incident_id: uuid.UUID,
    session: Session = Depends(get_sync_session),
):
    """Get an operator-ready incident briefing with RCA evidence and next actions."""
    detail = _build_incident_detail(session, incident_id)
    return _build_incident_briefing(detail)
