"""initial schema

Revision ID: 001
Revises: None
Create Date: 2026-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Services
    op.create_table(
        "services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Service dependencies
    op.create_table(
        "service_dependencies",
        sa.Column("upstream_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("downstream_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
        sa.UniqueConstraint("upstream_id", "downstream_id", name="uq_service_dep"),
    )

    # Raw logs
    op.create_table(
        "raw_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, comment="Event time"),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), comment="Ingestion time"),
        sa.Column("level", postgresql.ENUM("DEBUG", "INFO", "WARN", "ERROR", "CRITICAL", name="log_level"), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_raw_logs_service_timestamp", "raw_logs", ["service_id", "timestamp"])
    op.create_index("ix_raw_logs_trace_id", "raw_logs", ["trace_id"])

    # Metric windows
    op.create_table(
        "metric_windows",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_size_seconds", sa.Integer, nullable=False),
        sa.Column("request_count", sa.Integer, default=0),
        sa.Column("error_count", sa.Integer, default=0),
        sa.Column("error_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("p50_latency_ms", sa.Integer, nullable=True),
        sa.Column("p95_latency_ms", sa.Integer, nullable=True),
        sa.Column("unique_messages", sa.Integer, default=0),
        sa.Column("baseline_request_count_median", sa.Numeric, nullable=True),
        sa.Column("baseline_request_count_mad", sa.Numeric, nullable=True),
        sa.Column("baseline_error_rate_median", sa.Numeric, nullable=True),
        sa.Column("baseline_error_rate_mad", sa.Numeric, nullable=True),
        sa.Column("baseline_p95_latency_median", sa.Numeric, nullable=True),
        sa.Column("baseline_p95_latency_mad", sa.Numeric, nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True, comment="Set when watermark grace expires"),
        sa.UniqueConstraint("service_id", "window_start", "window_size_seconds", name="uq_metric_window"),
    )
    op.create_index("ix_metric_windows_start_size", "metric_windows", ["window_start", "window_size_seconds"])

    # Anomalies
    op.create_table(
        "anomalies",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_size_seconds", sa.Integer, nullable=False),
        sa.Column("detector", postgresql.ENUM("MAD", "ISOLATION_FOREST", name="anomaly_detector"), nullable=False),
        sa.Column("score", sa.Numeric, nullable=False),
        sa.Column("observed_value", sa.Numeric, nullable=False),
        sa.Column("baseline_value", sa.Numeric, nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("service_id", "metric", "window_start", "window_size_seconds", "detector", name="uq_anomaly"),
    )

    # Alerts
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("anomaly_type", sa.String(64), nullable=False),
        sa.Column("start_window", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_window", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", postgresql.ENUM("MEDIUM", "HIGH", "CRITICAL", name="incident_severity"), nullable=False),
        sa.Column("observed_value", sa.Numeric, nullable=False),
        sa.Column("baseline_value", sa.Numeric, nullable=False),
        sa.Column("anomaly_ids", postgresql.ARRAY(sa.Integer), default=[]),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_alerts_service_start", "alerts", ["service_id", "start_window"])

    # Deduplicated alerts
    op.create_table(
        "deduplicated_alerts",
        sa.Column("canonical_alert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alerts.id"), primary_key=True),
        sa.Column("duplicate_alert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alerts.id"), primary_key=True),
        sa.Column("dedupe_reason", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Incidents
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("affected_services", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), default=[]),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_incidents_time_range", "incidents", ["start_time", "end_time"])

    # Incident alerts
    op.create_table(
        "incident_alerts",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), primary_key=True),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alerts.id"), primary_key=True),
        sa.Column("attached_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Incident root cause scores
    op.create_table(
        "incident_root_cause_scores",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), primary_key=True),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), primary_key=True),
        sa.Column("score", sa.Numeric, nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("feature_vector", postgresql.JSONB, nullable=True),
        sa.Column("feature_contributions", postgresql.JSONB, nullable=True),
    )

    # Incident truth
    op.create_table(
        "incident_truth",
        sa.Column("truth_incident_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("root_cause_service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("affected_service_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), default=[]),
        sa.Column("generator_run_id", postgresql.UUID(as_uuid=True), nullable=False),
    )

    # Watermark
    op.create_table(
        "watermark",
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), primary_key=True),
        sa.Column("last_closed_window_start", sa.DateTime(timezone=True), nullable=False),
    )

    # Internal metrics
    op.create_table(
        "internal_metrics",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("metric_name", sa.String(128), nullable=False),
        sa.Column("metric_value", sa.Numeric, nullable=False),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Model versions
    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False, server_default="1.0.0"),
        sa.Column("model_type", sa.String(64), nullable=False),
        sa.Column("service_name", sa.String(255), nullable=True),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("training_params", postgresql.JSONB, nullable=True),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
    )

    # Benchmark runs
    op.create_table(
        "benchmark_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("benchmark_name", sa.String(128), nullable=False),
        sa.Column("run_date", sa.String(10), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.String(1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("benchmark_runs")
    op.drop_table("model_versions")
    op.drop_table("internal_metrics")
    op.drop_table("watermark")
    op.drop_table("incident_truth")
    op.drop_table("incident_root_cause_scores")
    op.drop_table("incident_alerts")
    op.drop_table("incidents")
    op.drop_table("deduplicated_alerts")
    op.drop_table("alerts")
    op.drop_table("anomalies")
    op.drop_table("metric_windows")
    op.drop_table("raw_logs")
    op.drop_table("service_dependencies")
    op.drop_table("services")
    # Drop ENUM types
    op.execute("DROP TYPE IF EXISTS log_level")
    op.execute("DROP TYPE IF EXISTS anomaly_detector")
    op.execute("DROP TYPE IF EXISTS incident_severity")