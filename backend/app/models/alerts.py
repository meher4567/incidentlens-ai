import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class IncidentSeverity(str, PyEnum):
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_service_start", "service_id", "start_window"),
        Index("ix_alerts_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id"), nullable=False
    )
    anomaly_type: Mapped[str] = mapped_column(String(64), nullable=False)
    start_window: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_window: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(
        SAEnum(IncidentSeverity, name="incident_severity"), nullable=False
    )
    observed_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    baseline_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    anomaly_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class DeduplicatedAlert(Base):
    __tablename__ = "deduplicated_alerts"

    canonical_alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id"), primary_key=True
    )
    duplicate_alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id"), primary_key=True
    )
    dedupe_reason: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
