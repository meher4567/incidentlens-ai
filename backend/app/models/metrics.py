import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class MetricWindow(Base):
    __tablename__ = "metric_windows"
    __table_args__ = (
        UniqueConstraint(
            "service_id", "window_start", "window_size_seconds", name="uq_metric_window"
        ),
        Index("ix_metric_windows_start_size", "window_start", "window_size_seconds"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id"), nullable=False
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_size_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    request_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_rate: Mapped[Optional[float]] = mapped_column(Numeric(6, 4), nullable=True)
    p50_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    p95_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    unique_messages: Mapped[int] = mapped_column(Integer, default=0)

    baseline_request_count_median: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    baseline_request_count_mad: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    baseline_error_rate_median: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    baseline_error_rate_mad: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    baseline_p95_latency_median: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    baseline_p95_latency_mad: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)

    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Set when watermark grace expires"
    )
