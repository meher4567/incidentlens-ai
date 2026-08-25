"""Tests for aggregation, detection, alerting, dedup, and clustering services."""

import uuid
from datetime import datetime, timedelta, timezone

from backend.app.models.alerts import Alert, DeduplicatedAlert
from backend.app.models.anomalies import Anomaly, AnomalyDetector
from backend.app.models.incidents import Incident
from backend.app.models.logs import LogLevel, RawLog


def _insert_log(
    db_session, service_id, timestamp, level, latency_ms=100, trace_id=None, msg="test"
):
    log = RawLog(
        service_id=service_id,
        timestamp=timestamp,
        level=level,
        message=msg,
        request_id=uuid.uuid4(),
        trace_id=trace_id,
        latency_ms=latency_ms,
        status_code=500 if level == LogLevel.ERROR else 200,
    )
    db_session.add(log)
    return log


class TestAggregationBasics:
    def test_mad_zscore_computation(self, db_session):
        from backend.app.services.detection import compute_mad_zscore

        z = compute_mad_zscore(500, 100, 20)
        assert z is not None
        assert z > 0
        assert abs(z - 0.6745 * 400 / 20) < 0.001

    def test_mad_no_division_by_zero(self, db_session):
        from backend.app.services.detection import compute_mad_zscore

        z = compute_mad_zscore(500, 100, 0)
        assert z is None

    def test_baselines_minimum_windows(self, db_session, seed_services):
        from backend.app.services.aggregation import _compute_baselines

        t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        baselines = _compute_baselines(db_session, seed_services["api-gateway"].id, t0, 60)
        # All None when no history
        assert baselines["baseline_request_count_median"] is None


class TestAnomalyTypeMapping:
    def test_error_rate_spike(self, db_session):
        from backend.app.services.alerting import _derive_anomaly_type

        assert _derive_anomaly_type("error_rate", 5.0) == "error_rate_spike"

    def test_traffic_drop(self, db_session):
        from backend.app.services.alerting import _derive_anomaly_type

        assert _derive_anomaly_type("request_count", -3.0) == "traffic_drop"

    def test_latency_spike(self, db_session):
        from backend.app.services.alerting import _derive_anomaly_type

        assert _derive_anomaly_type("p95_latency_ms", 4.5) == "latency_spike"


class TestAlertBatching:
    def test_debounce_sees_new_alerts_with_autoflush_disabled(self, db_session, seed_services):
        from backend.app.services.alerting import process_new_anomalies

        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for minute in range(3):
            db_session.add(
                Anomaly(
                    service_id=seed_services["payment-service"].id,
                    metric="p95_latency_ms",
                    window_start=t0 + timedelta(minutes=minute),
                    window_size_seconds=60,
                    detector=AnomalyDetector.MAD,
                    score=5.0,
                    observed_value=500.0,
                    baseline_value=100.0,
                    severity="HIGH",
                )
            )
        db_session.commit()

        assert process_new_anomalies(db_session) == 3
        alerts = db_session.query(Alert).all()
        assert len(alerts) == 1
        assert len(alerts[0].anomaly_ids) == 3


class TestMetricWindowAggregation:
    def test_compute_metrics(self, db_session, seed_services):
        from backend.app.services.aggregation import _compute_metrics_for_window

        t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(seconds=60)

        _insert_log(
            db_session,
            seed_services["api-gateway"].id,
            t0 + timedelta(seconds=10),
            LogLevel.INFO,
            latency_ms=100,
        )
        _insert_log(
            db_session,
            seed_services["api-gateway"].id,
            t0 + timedelta(seconds=20),
            LogLevel.ERROR,
            latency_ms=500,
        )
        _insert_log(
            db_session,
            seed_services["api-gateway"].id,
            t0 + timedelta(seconds=30),
            LogLevel.INFO,
            latency_ms=200,
        )
        db_session.commit()

        metrics = _compute_metrics_for_window(db_session, seed_services["api-gateway"].id, t0, t1)
        assert metrics["request_count"] == 3
        assert metrics["error_count"] == 1
        assert metrics["error_rate"] is not None
        assert abs(metrics["error_rate"] - 1 / 3) < 0.001
        assert metrics["p50_latency_ms"] == 150 or metrics["p50_latency_ms"] == 200
        assert metrics["p95_latency_ms"] >= 200


class TestRCAFeatures:
    def test_extract_features_is_earliest(self, db_session, seed_services):
        import networkx as nx

        from backend.app.services.root_cause import extract_features

        G = nx.DiGraph()
        for up_name, down_name in [
            ("api-gateway", "auth-service"),
            ("api-gateway", "checkout-service"),
        ]:
            G.add_edge(seed_services[up_name].id, seed_services[down_name].id)

        # Create an incident
        inc = Incident(
            start_time=datetime.now(timezone.utc),
            severity="HIGH",
            affected_services=[
                seed_services["api-gateway"].id,
                seed_services["auth-service"].id,
            ],
        )
        db_session.add(inc)
        db_session.commit()

        features = extract_features(db_session, inc, seed_services["api-gateway"].id, G)
        # No alerts yet, so all features should be 0
        assert features["is_earliest"] == 0.0
        assert features["alert_count"] == 0.0


class TestDeduplication:
    def test_same_service_rule(self, db_session, seed_services):
        from backend.app.services.deduplication import find_duplicates

        t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(minutes=1)

        alert1 = Alert(
            service_id=seed_services["payment-service"].id,
            anomaly_type="latency_spike",
            start_window=t0,
            end_window=t1,
            severity="HIGH",
            observed_value=500.0,
            baseline_value=100.0,
        )
        db_session.add(alert1)
        db_session.commit()

        alert2 = Alert(
            service_id=seed_services["payment-service"].id,
            anomaly_type="latency_spike",
            start_window=t0 + timedelta(minutes=2),
            end_window=t1 + timedelta(minutes=2),
            severity="HIGH",
            observed_value=600.0,
            baseline_value=100.0,
        )
        db_session.add(alert2)
        db_session.commit()

        duplicates = find_duplicates(db_session, alert2)
        assert len(duplicates) == 1
        assert duplicates[0].id == alert1.id

    def test_connected_component_is_idempotent(self, db_session, seed_services):
        from backend.app.services.deduplication import deduplicate_alerts

        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for minute in (0, 4, 8):
            db_session.add(
                Alert(
                    service_id=seed_services["payment-service"].id,
                    anomaly_type="latency_spike",
                    start_window=t0 + timedelta(minutes=minute),
                    end_window=t0 + timedelta(minutes=minute + 1),
                    severity="HIGH",
                    observed_value=500.0,
                    baseline_value=100.0,
                )
            )
        db_session.commit()

        assert deduplicate_alerts(db_session) == 2
        assert db_session.query(DeduplicatedAlert).count() == 2
        assert deduplicate_alerts(db_session) == 0
        assert db_session.query(DeduplicatedAlert).count() == 2


class TestClustering:
    def test_create_empty_incident(self, db_session, seed_services):
        from backend.app.services.clustering import cluster_alerts

        count = cluster_alerts(db_session)
        # No alerts should create 0 new incidents
        assert count >= 0

    def test_suppressed_alerts_remain_incident_evidence(self, db_session, seed_dependencies):
        from backend.app.models.incidents import IncidentAlert
        from backend.app.services.clustering import cluster_alerts

        services = seed_dependencies
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        canonical = Alert(
            service_id=services["checkout-service"].id,
            anomaly_type="latency_spike",
            start_window=start,
            end_window=start + timedelta(minutes=1),
            severity="HIGH",
            observed_value=500,
            baseline_value=100,
        )
        duplicate = Alert(
            service_id=services["payment-service"].id,
            anomaly_type="latency_spike",
            start_window=start,
            end_window=start + timedelta(minutes=1),
            severity="CRITICAL",
            observed_value=900,
            baseline_value=100,
        )
        db_session.add_all([canonical, duplicate])
        db_session.flush()
        db_session.add(
            DeduplicatedAlert(
                canonical_alert_id=canonical.id,
                duplicate_alert_id=duplicate.id,
                dedupe_reason="shared_trace_id",
            )
        )
        db_session.commit()

        assert cluster_alerts(db_session) == 1
        incident = db_session.query(Incident).one()
        assert set(incident.affected_services) == {
            services["checkout-service"].id,
            services["payment-service"].id,
        }
        assert incident.severity == "CRITICAL"
        assert db_session.query(IncidentAlert).count() == 2
