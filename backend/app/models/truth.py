import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class IncidentTruth(Base):
    __tablename__ = "incident_truth"
    __table_args__ = (Index("ix_incident_truth_run_split", "generator_run_id", "split"),)

    truth_incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    split: Mapped[str] = mapped_column(String(16), nullable=False, default="training")
    affected_metric: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    root_cause_service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    affected_service_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
    generator_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    scenario_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
