"""track aggregation watermarks per window size

Revision ID: 002
Revises: 001
Create Date: 2026-06-04 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "watermark",
        sa.Column(
            "window_size_seconds",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )
    op.drop_constraint("watermark_pkey", "watermark", type_="primary")
    op.create_primary_key(
        "watermark_pkey",
        "watermark",
        ["service_id", "window_size_seconds"],
    )
    op.alter_column("watermark", "window_size_seconds", server_default=None)


def downgrade() -> None:
    op.drop_constraint("watermark_pkey", "watermark", type_="primary")
    op.execute("DELETE FROM watermark WHERE window_size_seconds <> 60")
    op.create_primary_key("watermark_pkey", "watermark", ["service_id"])
    op.drop_column("watermark", "window_size_seconds")
