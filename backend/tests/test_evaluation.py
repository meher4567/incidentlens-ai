"""Tests for leakage-resistant, service-aware evaluation matching."""

import uuid
from datetime import datetime, timedelta, timezone

from backend.app.models.incidents import Incident
from backend.app.models.truth import IncidentTruth
from backend.app.services.evaluation import (
    match_incidents_to_truth,
    overlap_seconds,
    window_matches_truth,
)


def _truth(service_id, start, *, truth_id=None, split="training"):
    return IncidentTruth(
        truth_incident_id=truth_id or uuid.uuid4(),
        type="test_incident",
        split=split,
        affected_metric="error_rate",
        start_time=start,
        end_time=start + timedelta(minutes=5),
        root_cause_service_id=service_id,
        affected_service_ids=[service_id],
        generator_run_id=uuid.uuid4(),
        seed=42,
        scenario_version="test",
    )


def test_overlap_seconds_normalizes_naive_datetimes() -> None:
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    naive = datetime(2026, 1, 1, 0, 2)

    assert (
        overlap_seconds(aware, aware + timedelta(minutes=5), naive, naive + timedelta(minutes=7))
        == 180
    )
    assert (
        overlap_seconds(
            aware,
            aware + timedelta(minutes=1),
            naive + timedelta(minutes=2),
            naive + timedelta(minutes=3),
        )
        == 0
    )


def test_window_labels_require_time_and_affected_service(seed_services) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    truth = _truth(seed_services["payment-service"].id, start)

    assert window_matches_truth(
        service_id=seed_services["payment-service"].id,
        window_start=start - timedelta(minutes=1),
        window_size_seconds=300,
        truth=truth,
    )
    assert not window_matches_truth(
        service_id=seed_services["auth-service"].id,
        window_start=start,
        window_size_seconds=300,
        truth=truth,
    )
    assert not window_matches_truth(
        service_id=seed_services["payment-service"].id,
        window_start=start + timedelta(minutes=6),
        window_size_seconds=60,
        truth=truth,
    )


def test_matching_is_global_one_to_one_and_respects_minimum_overlap(
    db_session, seed_services
) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    payment_id = seed_services["payment-service"].id
    first_truth = _truth(payment_id, start, truth_id=uuid.UUID(int=1))
    second_truth = _truth(
        payment_id,
        start + timedelta(minutes=10),
        truth_id=uuid.UUID(int=2),
        split="held_out",
    )
    first_incident = Incident(
        start_time=start,
        end_time=start + timedelta(minutes=5),
        closed_at=start + timedelta(minutes=6),
        severity="HIGH",
        affected_services=[payment_id],
    )
    second_incident = Incident(
        start_time=start + timedelta(minutes=10),
        end_time=start + timedelta(minutes=15),
        closed_at=start + timedelta(minutes=16),
        severity="HIGH",
        affected_services=[payment_id],
    )
    too_short = Incident(
        start_time=start + timedelta(minutes=20),
        end_time=start + timedelta(minutes=20, seconds=10),
        closed_at=start + timedelta(minutes=21),
        severity="MEDIUM",
        affected_services=[payment_id],
    )
    db_session.add_all([first_truth, second_truth, first_incident, second_incident, too_short])
    db_session.commit()

    matched = match_incidents_to_truth(db_session)

    assert matched[first_incident.id].truth_incident_id == first_truth.truth_incident_id
    assert matched[second_incident.id].truth_incident_id == second_truth.truth_incident_id
    assert too_short.id not in matched
    assert len(matched) == 2
