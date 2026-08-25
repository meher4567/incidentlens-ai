"""RCA feature extraction, training, and model registration contracts."""

import uuid
from datetime import datetime, timedelta, timezone

import networkx as nx
import pytest

from backend.app.models.alerts import Alert
from backend.app.models.anomalies import Anomaly, AnomalyDetector
from backend.app.models.incidents import Incident, IncidentAlert
from backend.app.services import root_cause


def test_feature_extraction_uses_all_deduplicated_evidence(db_session, seed_dependencies):
    services = seed_dependencies
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    incident = Incident(
        start_time=start,
        end_time=start + timedelta(minutes=5),
        severity="CRITICAL",
        affected_services=[services["checkout-service"].id, services["payment-service"].id],
    )
    anomaly = Anomaly(
        service_id=services["payment-service"].id,
        metric="p95_latency_ms",
        window_start=start,
        window_size_seconds=300,
        detector=AnomalyDetector.MAD,
        score=8.0,
        observed_value=900,
        baseline_value=100,
        severity="CRITICAL",
    )
    db_session.add_all([incident, anomaly])
    db_session.flush()
    payment_alert = Alert(
        service_id=services["payment-service"].id,
        anomaly_type="latency_spike",
        start_window=start,
        end_window=start + timedelta(minutes=5),
        severity="CRITICAL",
        observed_value=900,
        baseline_value=100,
        anomaly_ids=[anomaly.id],
    )
    checkout_alert = Alert(
        service_id=services["checkout-service"].id,
        anomaly_type="latency_spike",
        start_window=start + timedelta(minutes=1),
        end_window=start + timedelta(minutes=2),
        severity="HIGH",
        observed_value=300,
        baseline_value=100,
        anomaly_ids=[],
    )
    db_session.add_all([payment_alert, checkout_alert])
    db_session.flush()
    db_session.add_all(
        [
            IncidentAlert(incident_id=incident.id, alert_id=payment_alert.id),
            IncidentAlert(incident_id=incident.id, alert_id=checkout_alert.id),
        ]
    )
    db_session.commit()

    graph = root_cause._build_dep_graph(db_session)
    features = root_cause.extract_features(
        db_session, incident, services["payment-service"].id, graph
    )

    assert features["is_earliest"] == 1.0
    assert features["earliest_seconds_gap"] == 60.0
    assert features["metric_jump_magnitude"] == 8.0
    assert features["alert_count"] == 1.0


def test_ranker_training_contract_and_scoring(monkeypatch, tmp_path):
    service_ids = [uuid.uuid4() for _ in range(4)]
    incidents = [
        Incident(
            id=uuid.uuid4(),
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            severity="HIGH",
            affected_services=service_ids,
        )
        for _ in range(3)
    ]
    truth = {incident.id: service_ids[index] for index, incident in enumerate(incidents)}

    monkeypatch.setattr(root_cause, "MODEL_PATH", tmp_path / "rca.pkl")
    monkeypatch.setattr(root_cause, "_build_dep_graph", lambda session: nx.DiGraph())

    def fake_features(session, incident, service_id, graph):
        is_root = service_id == truth[incident.id]
        return {
            "is_earliest": float(is_root),
            "earliest_seconds_gap": 60.0 if is_root else 0.0,
            "upstream_position": 0.0,
            "blast_radius": 0.0,
            "metric_jump_magnitude": 8.0 if is_root else 1.0,
            "alert_count": 2.0 if is_root else 1.0,
        }

    monkeypatch.setattr(root_cause, "extract_features", fake_features)
    model = root_cause.train_ranker(object(), incidents, truth)
    ranked = root_cause.score_incident(object(), incidents[0], model)

    assert root_cause.MODEL_PATH.exists()
    assert ranked[0]["service_id"] == truth[incidents[0].id]
    assert ranked[0]["rank"] == 1
    assert ranked[0]["feature_contributions"]


def test_ranker_rejects_too_few_positive_candidates(monkeypatch):
    incident = Incident(
        id=uuid.uuid4(),
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        severity="HIGH",
        affected_services=[uuid.uuid4()],
    )
    monkeypatch.setattr(root_cause, "_build_dep_graph", lambda session: nx.DiGraph())
    monkeypatch.setattr(
        root_cause,
        "extract_features",
        lambda session, incident, service_id, graph: {
            name: 0.0 for name in root_cause.FEATURE_NAMES
        },
    )

    with pytest.raises(ValueError, match="at least 10 service candidates"):
        root_cause.train_ranker(object(), [incident], {incident.id: incident.affected_services[0]})


def test_unregistered_rca_file_is_not_loaded(db_session, monkeypatch, tmp_path):
    model_path = tmp_path / "stale.pkl"
    model_path.write_bytes(b"not a model")
    monkeypatch.setattr(root_cause, "MODEL_PATH", model_path)

    assert root_cause.load_model(db_session) is None
    assert root_cause.run_rca_on_closed_incidents(db_session) == 0
