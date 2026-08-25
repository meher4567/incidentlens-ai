"""add operational query indexes

Revision ID: 004
Revises: 003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_raw_logs_ingested_at", "raw_logs", ["ingested_at"])
    op.create_index(
        "ix_anomalies_detector_created",
        "anomalies",
        ["detector", "created_at"],
    )
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])
    op.create_index("ix_incidents_created_at", "incidents", ["created_at"])
    op.create_index("ix_incidents_closed_at", "incidents", ["closed_at"])


def downgrade() -> None:
    op.drop_index("ix_incidents_closed_at", table_name="incidents")
    op.drop_index("ix_incidents_created_at", table_name="incidents")
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_index("ix_anomalies_detector_created", table_name="anomalies")
    op.drop_index("ix_raw_logs_ingested_at", table_name="raw_logs")
