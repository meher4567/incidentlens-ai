import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class IncidentTruth(Base):
    __tablename__ = "incident_truth"

    truth_incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    root_cause_service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    affected_service_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
    generator_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
