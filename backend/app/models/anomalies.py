import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base
from backend.app.models.compat import CompatBigInteger


class AnomalyDetector(str, PyEnum):
    MAD = "MAD"
    ISOLATION_FOREST = "ISOLATION_FOREST"


class Anomaly(Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "metric",
            "window_start",
            "window_size_seconds",
            "detector",
            name="uq_anomaly",
        ),
        Index("ix_anomalies_detector_created", "detector", "created_at"),
    )

    id: Mapped[int] = mapped_column(CompatBigInteger(), primary_key=True, autoincrement=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_size_seconds: Mapped[int] = mapped_column(nullable=False)
    detector: Mapped[AnomalyDetector] = mapped_column(
        SAEnum(AnomalyDetector, name="anomaly_detector"), nullable=False
    )
    score: Mapped[float] = mapped_column(Numeric, nullable=False)
    observed_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    baseline_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
