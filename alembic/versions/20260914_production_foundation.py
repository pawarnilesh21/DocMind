"""Accounts, durable ingestion, transactional vectors, and bounded requests.

Revision ID: 20260914_production
Revises: 03a5ad6ac405
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "20260914_production"
down_revision = "03a5ad6ac405"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table("rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False))
    op.create_index("ix_rate_limits_expires_at", "rate_limits", ["expires_at"])
    op.create_table("worker_heartbeats",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("seen_at", sa.DateTime(), nullable=False))
    for table in ("documents", "conversations"):
        op.add_column(table, sa.Column("owner_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(f"fk_{table}_owner", table, "users", ["owner_id"], ["id"])
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])
    op.add_column("documents", sa.Column("source_bytes", sa.LargeBinary(), nullable=True))
    op.add_column("documents", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("lease_token", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("lease_until", sa.DateTime(), nullable=True))
    op.add_column("documents", sa.Column("next_attempt_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_documents_status", "documents", ["status"])
    # Existing data remains intact, but cannot be served until explicitly claimed and reindexed.
    op.execute("UPDATE documents SET status = 'legacy'")
    op.add_column("document_chunks", sa.Column("embedding", Vector(768), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(), nullable=True))
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_unique_constraint("uq_document_chunk", "document_chunks", ["document_id", "chunk_index"])
    # Exact cosine search is used initially: unlike approximate filtering, it cannot
    # silently lose tenant-scoped matches. Add a measured index only after load evaluation.
    op.add_column("conversations", sa.Column("busy_token", sa.Uuid(), nullable=True))
    op.add_column("conversations", sa.Column("busy_until", sa.DateTime(), nullable=True))
    op.add_column("messages", sa.Column("request_id", sa.Uuid(), nullable=True))
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])
    op.create_unique_constraint("uq_message_request_role", "messages", ["conversation_id", "request_id", "role"])


def downgrade():
    raise RuntimeError("This migration contains account and vector data. Restore a verified backup to roll back.")
