import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base
from backend.app.models.compat import CompatUUID


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(CompatUUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    upstream_deps: Mapped[list["ServiceDependency"]] = relationship(
        "ServiceDependency",
        foreign_keys="ServiceDependency.upstream_id",
        back_populates="upstream",
    )
    downstream_deps: Mapped[list["ServiceDependency"]] = relationship(
        "ServiceDependency",
        foreign_keys="ServiceDependency.downstream_id",
        back_populates="downstream",
    )


class ServiceDependency(Base):
    __tablename__ = "service_dependencies"

    upstream_id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID,
        ForeignKey("services.id", ondelete="CASCADE"),
        primary_key=True,
    )
    downstream_id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID,
        ForeignKey("services.id", ondelete="CASCADE"),
        primary_key=True,
    )

    upstream: Mapped["Service"] = relationship(
        "Service", foreign_keys=[upstream_id], back_populates="upstream_deps"
    )
    downstream: Mapped["Service"] = relationship(
        "Service", foreign_keys=[downstream_id], back_populates="downstream_deps"
    )
