"""Create versioned knowledge documents and citation-bearing vector chunks.

Revision ID: 0001_company_policy_knowledge
Revises: None
"""

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_company_policy_knowledge"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL must already have the pgvector extension binaries installed.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_type", sa.String(32), nullable=False),
        sa.Column("source", sa.Uuid(), nullable=False),
        sa.Column("source_version", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "knowledge_type IN ('company_policy', 'technical_reference')",
            name="ck_document_collection",
        ),
        sa.CheckConstraint("length(trim(title)) >= 2", name="ck_document_title"),
        sa.CheckConstraint(
            "source_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'",
            name="ck_document_version",
        ),
        sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_document_hash"),
        sa.UniqueConstraint(
            "knowledge_type", "source", "source_version", name="uq_document_source_version"
        ),
        sa.UniqueConstraint("id", "knowledge_type", name="uq_document_id_collection"),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_type", sa.String(32), nullable=False),
        sa.Column("citation_id", sa.String(180), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_sha256", sa.String(64), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["document_id", "knowledge_type"],
            ["knowledge_documents.id", "knowledge_documents.knowledge_type"],
            ondelete="CASCADE", name="fk_chunk_document_collection",
        ),
        sa.CheckConstraint(
            "knowledge_type IN ('company_policy', 'technical_reference')",
            name="ck_chunk_collection",
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_chunk_index"),
        sa.CheckConstraint("token_count BETWEEN 1 AND 800", name="ck_chunk_tokens"),
        sa.CheckConstraint(
            "length(trim(chunk_text)) BETWEEN 1 AND 500000", name="ck_chunk_text"
        ),
        sa.CheckConstraint("chunk_sha256 ~ '^[0-9a-f]{64}$'", name="ck_chunk_hash"),
        sa.CheckConstraint(
            "knowledge_type <> 'company_policy' OR citation_id ~ "
            "'^policy:[0-9a-f]{32}:[0-9a-f]{16}:[0-9a-f]{16}:[0-9]{4,}$'",
            name="ck_chunk_policy_citation",
        ),
        sa.CheckConstraint(
            "embedding_model = 'BAAI/bge-small-en-v1.5'", name="ck_chunk_model"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object' AND metadata ? 'heading_paths' "
            "AND (metadata - 'heading_paths') = '{}'::jsonb "
            "AND jsonb_typeof(metadata -> 'heading_paths') = 'array'",
            name="ck_chunk_metadata",
        ),
        sa.UniqueConstraint("citation_id", name="uq_chunk_citation"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    # Keep the extension: it may be shared by unrelated PostgreSQL tables.
