"""align database constraints with ORM metadata

Revision ID: 005
Revises: 004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


REQUIRED_COLUMNS = [
    ("alerts", "anomaly_ids", postgresql.ARRAY(sa.Integer())),
    ("alerts", "created_at", sa.DateTime(timezone=True)),
    ("anomalies", "created_at", sa.DateTime(timezone=True)),
    ("benchmark_runs", "executed_at", sa.DateTime(timezone=True)),
    ("deduplicated_alerts", "created_at", sa.DateTime(timezone=True)),
    ("incident_alerts", "attached_at", sa.DateTime(timezone=True)),
    (
        "incident_truth",
        "affected_service_ids",
        postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
    ),
    (
        "incidents",
        "affected_services",
        postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
    ),
    ("incidents", "created_at", sa.DateTime(timezone=True)),
    ("internal_metrics", "recorded_at", sa.DateTime(timezone=True)),
    ("metric_windows", "request_count", sa.Integer()),
    ("metric_windows", "error_count", sa.Integer()),
    ("metric_windows", "unique_messages", sa.Integer()),
    ("model_versions", "trained_at", sa.DateTime(timezone=True)),
    ("raw_logs", "ingested_at", sa.DateTime(timezone=True)),
    ("services", "created_at", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    # Backfill defensive defaults before making ORM-required fields NOT NULL.
    op.execute("UPDATE alerts SET anomaly_ids = '{}' WHERE anomaly_ids IS NULL")
    op.execute(
        "UPDATE incident_truth SET affected_service_ids = '{}' "
        "WHERE affected_service_ids IS NULL"
    )
    op.execute("UPDATE incidents SET affected_services = '{}' WHERE affected_services IS NULL")
    op.execute("UPDATE metric_windows SET request_count = 0 WHERE request_count IS NULL")
    op.execute("UPDATE metric_windows SET error_count = 0 WHERE error_count IS NULL")
    op.execute("UPDATE metric_windows SET unique_messages = 0 WHERE unique_messages IS NULL")

    for table_name, column_name, existing_type in REQUIRED_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=existing_type,
            nullable=False,
        )

def downgrade() -> None:
    for table_name, column_name, existing_type in REQUIRED_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=existing_type,
            nullable=True,
        )
