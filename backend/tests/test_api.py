"""API contract tests for endpoints used by the dashboard."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import router
from backend.app.db.session import get_sync_session
from backend.app.models.alerts import Alert
from backend.app.models.logs import RawLog


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
    edges = {
        (row["upstream_name"], row["downstream_name"])
        for row in response.json()
    }
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
