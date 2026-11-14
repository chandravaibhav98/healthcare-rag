"""User escalations on query_log (Phase 6): escalated_at, escalation_note, and an index
on request_id (escalations look rows up by the X-Request-ID the user saw).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("query_log") as batch:
        batch.add_column(sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("escalation_note", sa.Text(), nullable=True))
        batch.create_index("ix_query_log_request_id", ["request_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("query_log") as batch:
        batch.drop_index("ix_query_log_request_id")
        batch.drop_column("escalation_note")
        batch.drop_column("escalated_at")
