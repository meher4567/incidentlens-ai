"""API contract tests for endpoints used by the dashboard."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import router
from backend.app.db.session import get_sync_session
from backend.app.models.alerts import Alert
from backend.app.models.anomalies import Anomaly, AnomalyDetector
from backend.app.models.incidents import Incident, IncidentAlert, IncidentRootCauseScore
from backend.app.models.logs import RawLog
from backend.app.models.metrics import MetricWindow


@pytest.fixture
def api_client(db_session):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def override_session():
        yield db_session

    app.dependency_overrides[get_sync_session] = override_session
    return TestClient(app)


def test_list_dependencies_returns_upstream_and_downstream_names(api_client, seed_dependencies):
    response = api_client.get("/api/services/dependencies")

    assert response.status_code == 200
    edges = {(row["upstream_name"], row["downstream_name"]) for row in response.json()}
    assert ("api-gateway", "auth-service") in edges
    assert ("checkout-service", "payment-service") in edges


def test_create_dependency_rejects_self_and_duplicates(api_client, seed_dependencies):
    self_response = api_client.post(
        "/api/services/dependencies",
        json={"upstream": "api-gateway", "downstream": "api-gateway"},
    )
    duplicate_response = api_client.post(
        "/api/services/dependencies",
        json={"upstream": "api-gateway", "downstream": "auth-service"},
    )

    assert self_response.status_code == 400
    assert duplicate_response.status_code == 409


def test_empty_log_batch_is_rejected(api_client):
    response = api_client.post("/api/logs/batch", json={"events": []})

    assert response.status_code == 422


def test_log_batch_persists_metadata(api_client, db_session):
    response = api_client.post(
        "/api/logs/batch",
        json={
            "events": [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "service": "api-gateway",
                    "level": "INFO",
                    "message": "request completed",
                    "latency_ms": 42,
                    "status_code": 200,
                    "host": "api-gateway-pod-1",
                    "region": "us-west-2",
                }
            ]
        },
    )

    assert response.status_code == 201
    log = db_session.query(RawLog).one()
    assert log.extra_data == {"host": "api-gateway-pod-1", "region": "us-west-2"}


def test_pr_curves_use_dashboard_response_keys(api_client):
    response = api_client.get("/api/metrics/pr-curves")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"mad", "isolation_forest", "summary"}
    assert set(body["summary"]) == {"mad", "isolation_forest"}


def test_metrics_overview_counts_logs_services_and_active_incidents(
    api_client, db_session, seed_services
):
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            RawLog(
                service_id=seed_services["api-gateway"].id,
                timestamp=now,
                ingested_at=now,
                level="INFO",
                message="request completed",
            ),
            RawLog(
                service_id=seed_services["checkout-service"].id,
                timestamp=now,
                ingested_at=now,
                level="ERROR",
                message="checkout failed",
                status_code=500,
            ),
            Incident(
                start_time=now,
                severity="HIGH",
                affected_services=[seed_services["checkout-service"].id],
            ),
        ]
    )
    db_session.commit()

    response = api_client.get("/api/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["total_logs"] == 2
    assert body["recent_errors"] == 1
    assert body["total_services"] == len(seed_services)
    assert body["active_incidents"] == 1


def test_service_health_returns_ordered_metric_windows(api_client, db_session, seed_services):
    service = seed_services["api-gateway"]
    later = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
    earlier = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            MetricWindow(
                service_id=service.id,
                window_start=later,
                window_size_seconds=60,
                request_count=20,
                error_count=1,
                error_rate=0.05,
                p50_latency_ms=100,
                p95_latency_ms=250,
                unique_messages=5,
            ),
            MetricWindow(
                service_id=service.id,
                window_start=earlier,
                window_size_seconds=60,
                request_count=10,
                error_count=0,
                error_rate=0.0,
                p50_latency_ms=80,
                p95_latency_ms=120,
                unique_messages=3,
            ),
        ]
    )
    db_session.commit()

    response = api_client.get(f"/api/services/{service.id}/health")

    assert response.status_code == 200
    body = response.json()
    assert body["service_name"] == "api-gateway"
    assert [window["request_count"] for window in body["windows"]] == [10, 20]


def test_service_health_returns_404_for_unknown_service(api_client):
    response = api_client.get(f"/api/services/{uuid.uuid4()}/health")

    assert response.status_code == 404
    assert response.json()["detail"] == "Service not found"


def test_incident_detail_returns_timeline_and_ranked_root_cause_scores(
    api_client, db_session, seed_services
):
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    checkout = seed_services["checkout-service"]
    payment = seed_services["payment-service"]
    incident = Incident(
        start_time=start,
        severity="HIGH",
        affected_services=[checkout.id, payment.id],
    )
    db_session.add(incident)
    db_session.flush()

    later_alert = Alert(
        service_id=payment.id,
        anomaly_type="error_rate_spike",
        start_window=start + timedelta(minutes=2),
        end_window=start + timedelta(minutes=3),
        severity="HIGH",
        observed_value=0.25,
        baseline_value=0.02,
        anomaly_ids=[2],
    )
    early_alert = Alert(
        service_id=checkout.id,
        anomaly_type="latency_spike",
        start_window=start,
        end_window=start + timedelta(minutes=1),
        severity="HIGH",
        observed_value=900.0,
        baseline_value=120.0,
        anomaly_ids=[1],
    )
    db_session.add_all([later_alert, early_alert])
    db_session.flush()

    db_session.add_all(
        [
            IncidentAlert(incident_id=incident.id, alert_id=later_alert.id),
            IncidentAlert(incident_id=incident.id, alert_id=early_alert.id),
            IncidentRootCauseScore(
                incident_id=incident.id,
                service_id=checkout.id,
                score=0.91,
                rank=1,
                feature_vector={"is_earliest": 1.0},
                feature_contributions={"is_earliest": 0.4},
            ),
            IncidentRootCauseScore(
                incident_id=incident.id,
                service_id=payment.id,
                score=0.44,
                rank=2,
                feature_vector={"is_earliest": 0.0},
                feature_contributions={"is_earliest": -0.1},
            ),
        ]
    )
    db_session.commit()

    response = api_client.get(f"/api/incidents/{incident.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["affected_service_names"] == ["checkout-service", "payment-service"]
    assert body["alert_count"] == 2
    assert [event["service_name"] for event in body["timeline"]] == [
        "checkout-service",
        "payment-service",
    ]
    assert [score["service_name"] for score in body["root_cause_scores"]] == [
        "checkout-service",
        "payment-service",
    ]
    assert body["root_cause_scores"][0]["feature_contributions"] == {"is_earliest": 0.4}


def test_incident_briefing_turns_rca_and_alerts_into_operator_summary(
    api_client, db_session, seed_services
):
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    checkout = seed_services["checkout-service"]
    payment = seed_services["payment-service"]
    incident = Incident(
        start_time=start,
        severity="CRITICAL",
        affected_services=[checkout.id, payment.id],
    )
    db_session.add(incident)
    db_session.flush()

    alert = Alert(
        service_id=payment.id,
        anomaly_type="latency_spike",
        start_window=start,
        end_window=start + timedelta(minutes=1),
        severity="CRITICAL",
        observed_value=1482.0,
        baseline_value=214.0,
        anomaly_ids=[1],
    )
    db_session.add(alert)
    db_session.flush()
    db_session.add_all(
        [
            IncidentAlert(incident_id=incident.id, alert_id=alert.id),
            IncidentRootCauseScore(
                incident_id=incident.id,
                service_id=payment.id,
                score=0.87,
                rank=1,
                feature_vector={"metric_jump_magnitude": 6.8},
                feature_contributions={"metric_jump": 0.34, "blast_radius": 0.22},
            ),
        ]
    )
    db_session.commit()

    response = api_client.get(f"/api/incidents/{incident.id}/briefing")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == str(incident.id)
    assert body["suspected_root_cause"]["service_name"] == "payment-service"
    assert body["suspected_root_cause"]["confidence"] == "high"
    assert body["impact"]["affected_services"] == ["checkout-service", "payment-service"]
    assert body["evidence"][0].startswith("Earliest alert: payment-service latency_spike")
    assert "Check payment-service deploys" in body["recommended_actions"][0]
    assert "# Incident Briefing" in body["markdown"]
    assert "payment-service" in body["markdown"]


def test_anomaly_list_filters_by_detector(api_client, db_session, seed_services):
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    service = seed_services["api-gateway"]
    db_session.add_all(
        [
            Anomaly(
                service_id=service.id,
                metric="error_rate",
                window_start=start,
                window_size_seconds=60,
                detector=AnomalyDetector.MAD,
                score=5.2,
                observed_value=0.2,
                baseline_value=0.01,
                severity="HIGH",
            ),
            Anomaly(
                service_id=service.id,
                metric="p95_latency_ms",
                window_start=start,
                window_size_seconds=60,
                detector=AnomalyDetector.ISOLATION_FOREST,
                score=0.91,
                observed_value=900,
                baseline_value=120,
                severity="MEDIUM",
            ),
        ]
    )
    db_session.commit()

    response = api_client.get("/api/anomalies", params={"detector": "MAD"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["detector"] == "MAD"
    assert body[0]["metric"] == "error_rate"


def test_alert_list_serializes_integer_anomaly_ids(api_client, db_session, seed_services):
    start = datetime.now(timezone.utc)
    alert = Alert(
        service_id=seed_services["checkout-service"].id,
        anomaly_type="latency_spike",
        start_window=start,
        end_window=start + timedelta(minutes=1),
        severity="HIGH",
        observed_value=500.0,
        baseline_value=100.0,
        anomaly_ids=[1, 2],
    )
    db_session.add(alert)
    db_session.commit()

    response = api_client.get("/api/alerts")

    assert response.status_code == 200
    assert response.json()[0]["anomaly_ids"] == [1, 2]
