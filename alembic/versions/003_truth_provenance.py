"""add reproducible incident-truth provenance

Revision ID: 003
Revises: 002
Create Date: 2026-08-20 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "incident_truth",
        sa.Column("split", sa.String(length=16), nullable=False, server_default="training"),
    )
    op.add_column(
        "incident_truth",
        sa.Column(
            "affected_metric",
            sa.String(length=64),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "incident_truth",
        sa.Column("seed", sa.Integer(), nullable=False, server_default="42"),
    )
    op.add_column(
        "incident_truth",
        sa.Column(
            "scenario_version",
            sa.String(length=32),
            nullable=False,
            server_default="1.0",
        ),
    )
    op.create_index(
        "ix_incident_truth_run_split",
        "incident_truth",
        ["generator_run_id", "split"],
    )
    for column in ("split", "affected_metric", "seed", "scenario_version"):
        op.alter_column("incident_truth", column, server_default=None)


def downgrade() -> None:
    op.drop_index("ix_incident_truth_run_split", table_name="incident_truth")
    op.drop_column("incident_truth", "scenario_version")
    op.drop_column("incident_truth", "seed")
    op.drop_column("incident_truth", "affected_metric")
    op.drop_column("incident_truth", "split")
