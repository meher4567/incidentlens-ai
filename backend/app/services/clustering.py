"""
Incident clustering service.

Clusters canonical alerts into incidents using:
1. Time proximity within 5 minutes
2. Same service or graph-adjacent service

Closes incidents after 10 minutes with no new alert.
If multiple candidate incidents match, merges into oldest.
"""
import uuid
from datetime import datetime, timedelta, timezone

import networkx as nx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.alerts import Alert, DeduplicatedAlert
from backend.app.models.incidents import Incident, IncidentAlert
from backend.app.models.services import ServiceDependency

settings = get_settings()

PROXIMITY_MINUTES = settings.incident_proximity_minutes  # 5
CLOSE_MINUTES = settings.incident_close_minutes  # 10


def _get_canonical_alerts(session: Session) -> list[Alert]:
    """Get alerts that are not marked as duplicates."""
    dup_ids = session.execute(select(DeduplicatedAlert.duplicate_alert_id)).scalars().all()
    dup_set = set(dup_ids)

    stmt = (
        select(Alert)
        .where(~Alert.id.in_(dup_set) if dup_set else True)
        .order_by(Alert.start_window.asc())
    )

    return session.execute(stmt).scalars().all()


def _build_dep_graph(session: Session) -> nx.DiGraph:
    """Load service dependency graph into NetworkX."""
    G = nx.DiGraph()
    deps = session.execute(select(ServiceDependency)).scalars().all()
    for dep in deps:
        G.add_edge(dep.upstream_id, dep.downstream_id)
    return G


def _is_graph_adjacent(
    G: nx.DiGraph,
    service_a: uuid.UUID,
    service_b: uuid.UUID,
) -> bool:
    """Check if two services share an edge in either direction."""
    return G.has_edge(service_a, service_b) or G.has_edge(service_b, service_a)


def _is_connected_to_incident(
    G: nx.DiGraph,
    alert: Alert,
    incident: Incident,
) -> bool:
    """Check if an alert's service is graph-adjacent to any service in the incident."""
    for sid in incident.affected_services:
        if sid == alert.service_id:
            return True
        if _is_graph_adjacent(G, sid, alert.service_id):
            return True
    return False


def cluster_alerts(session: Session) -> int:
    """
    Run incident clustering on canonical alerts.
    Returns number of incidents created/updated.
    """
    G = _build_dep_graph(session)
    canonical_alerts = _get_canonical_alerts(session)

    # Get existing open incidents
    open_incidents = (
        session.execute(select(Incident).where(Incident.closed_at.is_(None))).scalars().all()
    )

    # Track which alerts have been attached
    attached_alert_ids: set[uuid.UUID] = set()
    for inc in open_incidents:
        attached = (
            session.execute(select(IncidentAlert).where(IncidentAlert.incident_id == inc.id))
            .scalars()
            .all()
        )
        attached_alert_ids.update(a.alert_id for a in attached)

    incidents_created = 0
    now = datetime.now(timezone.utc)

    for alert in canonical_alerts:
        if alert.id in attached_alert_ids:
            continue

        # Find candidate open incidents
        proximity_window = timedelta(minutes=PROXIMITY_MINUTES)
        candidates = []
        for inc in open_incidents:
            # Time proximity check
            latest_alert_time = inc.start_time
            if inc.end_time:
                latest_alert_time = inc.end_time

            time_proximate = (
                alert.start_window <= latest_alert_time + proximity_window
                and alert.start_window >= inc.start_time - proximity_window
            )

            if not time_proximate:
                continue

            # Graph adjacency check
            if _is_connected_to_incident(G, alert, inc):
                candidates.append(inc)

        if len(candidates) == 1:
            # Attach to single candidate
            inc = candidates[0]
            _attach_alert_to_incident(session, inc, alert)
        elif len(candidates) > 1:
            # Merge into oldest, attach alert
            oldest = min(candidates, key=lambda i: i.start_time)
            for other in candidates:
                if other.id != oldest.id:
                    _merge_incidents(session, oldest, other)
            _attach_alert_to_incident(session, oldest, alert)
            # Refresh open incidents after merge
            open_incidents = (
                session.execute(select(Incident).where(Incident.closed_at.is_(None)))
                .scalars()
                .all()
            )
        else:
            # Create new incident
            inc = Incident(
                start_time=alert.start_window,
                severity=alert.severity,
                affected_services=[alert.service_id],
            )
            session.add(inc)
            session.flush()
            _attach_alert_to_incident(session, inc, alert)
            open_incidents.append(inc)
            incidents_created += 1

    # Close incidents with no recent alerts
    close_cutoff = now - timedelta(minutes=CLOSE_MINUTES)
    for inc in open_incidents:
        if inc.closed_at is not None:
            continue
        # Find latest alert in incident
        latest = session.execute(
            select(func.max(IncidentAlert.attached_at)).where(IncidentAlert.incident_id == inc.id)
        ).scalar()

        if latest and latest < close_cutoff:
            inc.closed_at = now
            # Set end_time to last alert's end_window
            last_alert = (
                session.execute(
                    select(Alert)
                    .join(IncidentAlert, IncidentAlert.alert_id == Alert.id)
                    .where(IncidentAlert.incident_id == inc.id)
                    .order_by(Alert.end_window.desc())
                )
                .scalars()
                .first()
            )
            if last_alert:
                inc.end_time = last_alert.end_window

    session.commit()
    return incidents_created


def _attach_alert_to_incident(
    session: Session,
    incident: Incident,
    alert: Alert,
) -> None:
    """Attach an alert to an incident, updating incident metadata."""
    # Create join
    ia = IncidentAlert(
        incident_id=incident.id,
        alert_id=alert.id,
    )
    session.add(ia)

    # Update incident fields
    if alert.service_id not in incident.affected_services:
        incident.affected_services = list(incident.affected_services) + [alert.service_id]

    # Update severity to max
    severities = ["MEDIUM", "HIGH", "CRITICAL"]
    inc_sev_idx = severities.index(incident.severity) if incident.severity in severities else 0
    alert_sev_idx = severities.index(alert.severity) if alert.severity in severities else 0
    if alert_sev_idx > inc_sev_idx:
        incident.severity = alert.severity

    # Extend end_time
    if incident.end_time is None or alert.end_window > incident.end_time:
        incident.end_time = alert.end_window


def _merge_incidents(
    session: Session,
    target: Incident,
    source: Incident,
) -> None:
    """Merge source incident into target. Reassign all alerts and close source."""
    # Move all alert joins from source to target
    source_alerts = (
        session.execute(select(IncidentAlert).where(IncidentAlert.incident_id == source.id))
        .scalars()
        .all()
    )

    for sa in source_alerts:
        # Check if already in target
        existing = session.execute(
            select(IncidentAlert).where(
                IncidentAlert.incident_id == target.id,
                IncidentAlert.alert_id == sa.alert_id,
            )
        ).scalar_one_or_none()
        if not existing:
            sa.incident_id = target.id

    # Merge affected services
    merged_services = list(set(target.affected_services + source.affected_services))
    target.affected_services = merged_services

    # Merge time range
    if source.start_time < target.start_time:
        target.start_time = source.start_time
    if source.end_time and (target.end_time is None or source.end_time > target.end_time):
        target.end_time = source.end_time

    # Take max severity
    severities = ["MEDIUM", "HIGH", "CRITICAL"]
    target_sev = severities.index(target.severity) if target.severity in severities else 0
    source_sev = severities.index(source.severity) if source.severity in severities else 0
    if source_sev > target_sev:
        target.severity = source.severity

    # Close source
    source.closed_at = datetime.now(timezone.utc)
    source.end_time = source.end_time or source.start_time
