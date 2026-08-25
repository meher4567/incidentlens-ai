"""
ML metadata tables: model versions and benchmark runs.

model_versions tracks every trained model artifact (IF per-service, RCA ranker).
benchmark_runs stores results of benchmark executions with structured metrics.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0.0")
    model_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # isolation_forest, rca_ranker
    service_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # per-service IF
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    training_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # training_data: dict with keys like n_samples, n_features, contamination, date_range


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    benchmark_name: Mapped[str] = mapped_column(String(128), nullable=False)
    run_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="completed"
    )  # completed, failed
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # metrics stored as JSON: {metric_name: value, ...}
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
