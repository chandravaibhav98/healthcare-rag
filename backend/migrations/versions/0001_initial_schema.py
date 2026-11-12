"""Initial schema (Phase 5): users, refresh tokens, query log, reviews, eval runs,
index versions, audit log and versioned runtime config.

Revision ID: 0001
Revises:
Create Date: 2026-11-12 07:09:55.473814
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# JSON on SQLite, JSONB on PostgreSQL (mirrors app.db.base.JSONType; migrations never
# import application types, so they keep working when the models change later).
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "index_versions",
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("manifest", JSON_TYPE, nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("version", name=op.f("pk_index_versions")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('user', 'reviewer', 'admin')", name=op.f("ck_users_role")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "app_config",
        sa.Column("version", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("values", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("comment", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_app_config_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("version", name=op.f("pk_app_config")),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=254), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("details", JSON_TYPE, nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_log_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_log_action"), ["action"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_log_actor_id"), ["actor_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_log_created_at"), ["created_at"], unique=False)

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("split", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("triggered_by", sa.Uuid(), nullable=True),
        sa.Column("index_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scorecard", JSON_TYPE, nullable=True),
        sa.Column("summary", JSON_TYPE, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name=op.f("ck_eval_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by"],
            ["users.id"],
            name=op.f("fk_eval_runs_triggered_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
    )
    with op.batch_alter_table("eval_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_eval_runs_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_eval_runs_status"), ["status"], unique=False)

    op.create_table(
        "query_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("redactions", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("signals", JSON_TYPE, nullable=False),
        sa.Column("citations", JSON_TYPE, nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("candidate_answer", sa.Text(), nullable=True),
        sa.Column("topics", JSON_TYPE, nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("index_version", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('validated', 'needs_review')", name=op.f("ck_query_log_status")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_query_log_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_query_log")),
    )
    with op.batch_alter_table("query_log", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_query_log_created_at"), ["created_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_query_log_index_version"), ["index_version"], unique=False
        )
        batch_op.create_index(
            "ix_query_log_status_created_at", ["status", "created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_query_log_user_id"), ["user_id"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("jti", name=op.f("pk_refresh_tokens")),
    )
    with op.batch_alter_table("refresh_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_refresh_tokens_family_id"), ["family_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_refresh_tokens_user_id"), ["user_id"], unique=False)

    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("corrected_citations", JSON_TYPE, nullable=False),
        sa.Column("promote_to_gold", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "verdict IN ('approve', 'reject', 'correct')", name=op.f("ck_reviews_verdict")
        ),
        sa.ForeignKeyConstraint(
            ["query_id"],
            ["query_log.id"],
            name=op.f("fk_reviews_query_id_query_log"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name=op.f("fk_reviews_reviewer_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
        sa.UniqueConstraint("query_id", name=op.f("uq_reviews_query_id")),
    )


def downgrade() -> None:
    op.drop_table("reviews")
    with op.batch_alter_table("refresh_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_refresh_tokens_user_id"))
        batch_op.drop_index(batch_op.f("ix_refresh_tokens_family_id"))

    op.drop_table("refresh_tokens")
    with op.batch_alter_table("query_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_query_log_user_id"))
        batch_op.drop_index("ix_query_log_status_created_at")
        batch_op.drop_index(batch_op.f("ix_query_log_index_version"))
        batch_op.drop_index(batch_op.f("ix_query_log_created_at"))

    op.drop_table("query_log")
    with op.batch_alter_table("eval_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_eval_runs_status"))
        batch_op.drop_index(batch_op.f("ix_eval_runs_created_at"))

    op.drop_table("eval_runs")
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_log_created_at"))
        batch_op.drop_index(batch_op.f("ix_audit_log_actor_id"))
        batch_op.drop_index(batch_op.f("ix_audit_log_action"))

    op.drop_table("audit_log")
    op.drop_table("app_config")
    op.drop_table("users")
    op.drop_table("index_versions")
