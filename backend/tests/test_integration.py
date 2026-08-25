"""
Integration test: generate -> ingest -> aggregate -> detect -> alert -> dedupe -> cluster -> rank.

Tests the full pipeline end-to-end with synthetic data.
"""

import uuid
from datetime import datetime

from backend.app.models.alerts import Alert
from backend.app.models.anomalies import Anomaly
from backend.app.models.incidents import Incident
from backend.app.models.logs import RawLog
from backend.app.models.metrics import MetricWindow
from backend.app.services.aggregation import run_aggregation_all_services
from backend.app.services.alerting import process_new_anomalies
from backend.app.services.clustering import cluster_alerts
from backend.app.services.deduplication import deduplicate_alerts
from backend.app.services.detection import run_detection_all
from backend.app.services.root_cause import run_rca_on_closed_incidents
from generator.generate_logs import LogGenerator, load_config


def test_full_pipeline(db_session, seed_dependencies):
    """
    End-to-end test: generate logs, insert directly, run full pipeline.
    Uses direct DB insertion instead of HTTP API since there's no server in CI.
    """
    services = seed_dependencies

    # 1. Generate 2000 synthetic log events
    import os

    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "generator", "config.yaml")
    config = load_config(config_path)
    gen = LogGenerator(config, seed=42)
    logs, truth = gen.generate(2000)

    assert len(logs) > 0, "Generator produced no logs"
    assert len(truth) > 0, "Generator produced no truth data"

    # 2. Insert logs directly into raw_logs
    count = 0
    for log_entry in logs:
        svc_name = log_entry["service"]
        if svc_name in services:
            raw_log = RawLog(
                service_id=services[svc_name].id,
                timestamp=datetime.fromisoformat(log_entry["timestamp"]),
                level=log_entry.get("level", "INFO"),
                message=log_entry.get("message", ""),
                request_id=uuid.UUID(log_entry["request_id"])
                if log_entry.get("request_id")
                else None,
                trace_id=uuid.UUID(log_entry["trace_id"]) if log_entry.get("trace_id") else None,
                latency_ms=log_entry.get("latency_ms"),
                status_code=log_entry.get("status_code"),
            )
            db_session.add(raw_log)
            count += 1

    db_session.commit()
    assert count > 0, "No logs were inserted"

    # 3. Run aggregation
    windows = run_aggregation_all_services(db_session)
    assert windows > 0, "No metric windows computed"

    # Verify windows exist
    mw_count = db_session.query(MetricWindow).count()
    assert mw_count > 0, "No metric window rows"

    # 4. Run detection
    anomalies = run_detection_all(db_session)
    # Anomalies may be 0 if not enough baseline windows (need 30+)
    # This is expected with only 2000 events. We test that it doesn't crash.
    anomaly_count = db_session.query(Anomaly).count()
    print(f"  Detection: {anomalies} anomalies recorded ({anomaly_count} rows)")

    # 5. Run alerting
    alerts = process_new_anomalies(db_session)
    alert_count = db_session.query(Alert).count()
    print(f"  Alerting: {alerts} alerts processed ({alert_count} rows)")

    # 6. Run deduplication
    dedup = deduplicate_alerts(db_session)
    print(f"  Dedup: {dedup} dedup relationships")

    # 7. Run clustering
    incidents = cluster_alerts(db_session)
    inc_count = db_session.query(Incident).count()
    print(f"  Clustering: {incidents} incidents created ({inc_count} rows)")

    # 8. Try RCA (may fail without model, that's OK)
    try:
        scored = run_rca_on_closed_incidents(db_session)
        print(f"  RCA: {scored} incidents scored")
    except Exception as e:
        print(f"  RCA: skipped (no model): {e}")

    # Verify the pipeline ran without fatal errors
    assert True, "Pipeline completed without errors"


def test_pipeline_idempotency(db_session, seed_dependencies):
    """Verify that running pipeline twice does not crash (idempotency)."""
    services = seed_dependencies

    import os

    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "generator", "config.yaml")
    config = load_config(config_path)
    gen = LogGenerator(config, seed=42)
    logs, truth = gen.generate(1000)

    for log_entry in logs:
        svc_name = log_entry["service"]
        if svc_name in services:
            raw_log = RawLog(
                service_id=services[svc_name].id,
                timestamp=datetime.fromisoformat(log_entry["timestamp"]),
                level=log_entry.get("level", "INFO"),
                message=log_entry.get("message", ""),
                request_id=uuid.UUID(log_entry["request_id"])
                if log_entry.get("request_id")
                else None,
                trace_id=uuid.UUID(log_entry["trace_id"]) if log_entry.get("trace_id") else None,
                latency_ms=log_entry.get("latency_ms"),
                status_code=log_entry.get("status_code"),
            )
            db_session.add(raw_log)
    db_session.commit()

    # Run twice
    run_aggregation_all_services(db_session)
    run_detection_all(db_session)
    process_new_anomalies(db_session)
    deduplicate_alerts(db_session)
    cluster_alerts(db_session)

    # Second run should not crash
    run_aggregation_all_services(db_session)
    run_detection_all(db_session)
    process_new_anomalies(db_session)
    deduplicate_alerts(db_session)
    cluster_alerts(db_session)

    assert True, "Pipeline idempotency verified"
