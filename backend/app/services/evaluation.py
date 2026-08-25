"""Leakage-resistant matching helpers for benchmark evaluation.

Evaluation labels are service-aware as well as time-aware. A metric window for
an unrelated service is not considered anomalous merely because some incident
happened elsewhere in the topology at the same time.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.incidents import Incident
from backend.app.models.truth import IncidentTruth


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def overlap_seconds(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> float:
    start = max(_as_utc(left_start), _as_utc(right_start))
    end = min(_as_utc(left_end), _as_utc(right_end))
    return max(0.0, (end - start).total_seconds())


def window_matches_truth(
    *,
    service_id: uuid.UUID,
    window_start: datetime,
    window_size_seconds: int,
    truth: IncidentTruth,
) -> bool:
    if service_id not in set(truth.affected_service_ids or []):
        return False
    window_end = _as_utc(window_start) + timedelta(seconds=window_size_seconds)
    return overlap_seconds(window_start, window_end, truth.start_time, truth.end_time) > 0


def match_incidents_to_truth(
    session: Session,
    *,
    minimum_overlap_seconds: float = 30.0,
) -> dict[uuid.UUID, IncidentTruth]:
    """Return a deterministic one-to-one incident-to-truth assignment.

    Candidate pairs must overlap in event time and share at least one affected
    service. Pairs are assigned globally from strongest to weakest overlap so
    database iteration order cannot change the evaluation result.
    """
    truth_rows = session.execute(select(IncidentTruth)).scalars().all()
    incidents = (
        session.execute(select(Incident).where(Incident.closed_at.isnot(None))).scalars().all()
    )

    candidates: list[tuple[float, float, str, Incident, IncidentTruth]] = []
    for incident in incidents:
        if incident.start_time is None or incident.end_time is None:
            continue
        incident_services = set(incident.affected_services or [])
        for truth in truth_rows:
            shared_services = incident_services & set(truth.affected_service_ids or [])
            if not shared_services:
                continue
            overlap = overlap_seconds(
                incident.start_time,
                incident.end_time,
                truth.start_time,
                truth.end_time,
            )
            if overlap < minimum_overlap_seconds:
                continue
            truth_duration = max(
                1.0,
                (_as_utc(truth.end_time) - _as_utc(truth.start_time)).total_seconds(),
            )
            coverage = overlap / truth_duration
            service_overlap = len(shared_services) / max(
                1,
                len(incident_services | set(truth.affected_service_ids or [])),
            )
            candidates.append(
                (coverage, service_overlap, str(truth.truth_incident_id), incident, truth)
            )

    candidates.sort(key=lambda row: (-row[0], -row[1], row[2], str(row[3].id)))
    matched: dict[uuid.UUID, IncidentTruth] = {}
    used_incidents: set[uuid.UUID] = set()
    used_truth: set[uuid.UUID] = set()
    for _coverage, _service_overlap, _truth_id, incident, truth in candidates:
        if incident.id in used_incidents or truth.truth_incident_id in used_truth:
            continue
        matched[incident.id] = truth
        used_incidents.add(incident.id)
        used_truth.add(truth.truth_incident_id)

    return matched
