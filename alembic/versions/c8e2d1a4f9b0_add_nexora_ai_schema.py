"""add_nexora_ai_schema

Revision ID: c8e2d1a4f9b0
Revises: b7df9a78bd2e
Create Date: 2026-11-28 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8e2d1a4f9b0"
down_revision: Union[str, Sequence[str], None] = "b7df9a78bd2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Nexora AI tables and enable pgvector when running on PostgreSQL."""
    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_conversations_id", "ai_conversations", ["id"], unique=False)
    op.create_index("ix_ai_conversations_organization_id", "ai_conversations", ["organization_id"], unique=False)
    op.create_index("ix_ai_conversations_user_id", "ai_conversations", ["user_id"], unique=False)

    op.create_table(
        "ai_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_messages_id", "ai_messages", ["id"], unique=False)
    op.create_index("ix_ai_messages_conversation_id", "ai_messages", ["conversation_id"], unique=False)
    op.create_index("ix_ai_messages_organization_id", "ai_messages", ["organization_id"], unique=False)
    op.create_index("ix_ai_messages_user_id", "ai_messages", ["user_id"], unique=False)

    op.create_table(
        "ai_message_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["ai_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_message_feedback_id", "ai_message_feedback", ["id"], unique=False)
    op.create_index("ix_ai_message_feedback_message_id", "ai_message_feedback", ["message_id"], unique=False)
    op.create_index("ix_ai_message_feedback_user_id", "ai_message_feedback", ["user_id"], unique=False)
    op.create_index("ix_ai_message_feedback_organization_id", "ai_message_feedback", ["organization_id"], unique=False)

    op.create_table(
        "ai_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="hr_policy"),
        sa.Column("visibility", sa.String(length=40), nullable=False, server_default="organization"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_documents_id", "ai_documents", ["id"], unique=False)
    op.create_index("ix_ai_documents_organization_id", "ai_documents", ["organization_id"], unique=False)
    op.create_index("ix_ai_documents_uploaded_by", "ai_documents", ["uploaded_by"], unique=False)
    op.create_index("ix_ai_documents_category", "ai_documents", ["category"], unique=False)
    op.create_index("ix_ai_documents_visibility", "ai_documents", ["visibility"], unique=False)
    op.create_index("ix_ai_documents_status", "ai_documents", ["status"], unique=False)
    op.create_index("ix_ai_documents_checksum", "ai_documents", ["checksum"], unique=False)

    op.create_table(
        "ai_document_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["ai_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_document_chunks_id", "ai_document_chunks", ["id"], unique=False)
    op.create_index("ix_ai_document_chunks_document_id", "ai_document_chunks", ["document_id"], unique=False)
    op.create_index("ix_ai_document_chunks_organization_id", "ai_document_chunks", ["organization_id"], unique=False)

    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("request_type", sa.String(length=40), nullable=False, server_default="chat"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="success"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_logs_id", "ai_usage_logs", ["id"], unique=False)
    op.create_index("ix_ai_usage_logs_organization_id", "ai_usage_logs", ["organization_id"], unique=False)
    op.create_index("ix_ai_usage_logs_user_id", "ai_usage_logs", ["user_id"], unique=False)
    op.create_index("ix_ai_usage_logs_created_at", "ai_usage_logs", ["created_at"], unique=False)

    op.create_table(
        "ai_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=True),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_status", sa.String(length=30), nullable=False, server_default="success"),
        sa.Column("ip_address", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_audit_logs_id", "ai_audit_logs", ["id"], unique=False)
    op.create_index("ix_ai_audit_logs_organization_id", "ai_audit_logs", ["organization_id"], unique=False)
    op.create_index("ix_ai_audit_logs_user_id", "ai_audit_logs", ["user_id"], unique=False)
    op.create_index("ix_ai_audit_logs_action", "ai_audit_logs", ["action"], unique=False)
    op.create_index("ix_ai_audit_logs_created_at", "ai_audit_logs", ["created_at"], unique=False)

    op.create_table(
        "ai_provider_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("active_provider", sa.String(length=50), nullable=False, server_default="gemini"),
        sa.Column("active_model", sa.String(length=100), nullable=False, server_default="gemini-2.5-flash"),
        sa.Column("embedding_model", sa.String(length=100), nullable=False, server_default="text-embedding-004"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allow_general_chat", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_rag", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_tools", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("max_tokens_per_request", sa.Integer(), nullable=False, server_default="2048"),
        sa.Column("daily_user_token_limit", sa.Integer(), nullable=False, server_default="50000"),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
    )
    op.create_index("ix_ai_provider_configs_id", "ai_provider_configs", ["id"], unique=False)

    # Enable pgvector and add vector column + HNSW index on PostgreSQL when available
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        has_vector = bind.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).scalar()
        if has_vector:
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
            op.execute("ALTER TABLE ai_document_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector(768)")
            op.execute(
                "CREATE INDEX IF NOT EXISTS ix_ai_document_chunks_embedding_vector "
                "ON ai_document_chunks USING hnsw (embedding_vector vector_cosine_ops)"
            )


def downgrade() -> None:
    """Drop Nexora AI tables."""
    op.drop_table("ai_provider_configs")
    op.drop_table("ai_audit_logs")
    op.drop_table("ai_usage_logs")
    op.drop_table("ai_document_chunks")
    op.drop_table("ai_documents")
    op.drop_table("ai_message_feedback")
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
