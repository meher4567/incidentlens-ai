"""Test database models and schema validation."""

from datetime import datetime, timezone

import pytest

from backend.app.models.alerts import Alert, IncidentSeverity
from backend.app.models.logs import LogLevel, RawLog
from backend.app.models.services import Service, ServiceDependency


def test_service_creation(db_session):
    svc = Service(name="test-service")
    db_session.add(svc)
    db_session.commit()

    assert svc.id is not None
    assert svc.name == "test-service"
    assert svc.created_at is not None


def test_service_dependency(db_session, seed_services):
    dep = ServiceDependency(
        upstream_id=seed_services["api-gateway"].id,
        downstream_id=seed_services["auth-service"].id,
    )
    db_session.add(dep)
    db_session.commit()

    assert dep.upstream_id == seed_services["api-gateway"].id


def test_raw_log_creation(db_session, seed_services):
    log = RawLog(
        service_id=seed_services["payment-service"].id,
        timestamp=datetime.now(timezone.utc),
        level=LogLevel.ERROR,
        message="Payment failed",
        request_id=None,
        trace_id=None,
        latency_ms=150,
        status_code=500,
    )
    db_session.add(log)
    db_session.commit()

    assert log.id is not None
    assert log.level == LogLevel.ERROR
    assert log.latency_ms == 150


def test_alert_creation(db_session, seed_services):
    alert = Alert(
        service_id=seed_services["checkout-service"].id,
        anomaly_type="latency_spike",
        start_window=datetime.now(timezone.utc),
        end_window=datetime.now(timezone.utc),
        severity=IncidentSeverity.HIGH,
        observed_value=450.0,
        baseline_value=100.0,
    )
    db_session.add(alert)
    db_session.commit()

    assert alert.id is not None
    assert alert.severity == IncidentSeverity.HIGH


def test_unique_service_constraint(db_session):
    svc1 = Service(name="duplicate-test")
    db_session.add(svc1)
    db_session.commit()

    svc2 = Service(name="duplicate-test")
    db_session.add(svc2)
    with pytest.raises(Exception):
        db_session.commit()


def test_seed_dependencies_graph(db_session, seed_dependencies):
    from sqlalchemy import select

    from backend.app.models.services import ServiceDependency

    deps = db_session.execute(select(ServiceDependency)).scalars().all()
    assert len(deps) == 5
    dep_names = set()
    for d in deps:
        up = db_session.execute(select(Service.name).where(Service.id == d.upstream_id)).scalar()
        down = db_session.execute(
            select(Service.name).where(Service.id == d.downstream_id)
        ).scalar()
        dep_names.add((up, down))

    assert ("api-gateway", "auth-service") in dep_names
    assert ("checkout-service", "payment-service") in dep_names
