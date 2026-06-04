import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class Watermark(Base):
    __tablename__ = "watermark"

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id"), primary_key=True
    )
    window_size_seconds: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_closed_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
