from __future__ import annotations

from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class KnowledgeDocument(Base):
    """One immutable source version in one logical knowledge collection.

    The design's `source` field is an opaque UUID, never a filesystem path.
    """

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint(
            "knowledge_type IN ('company_policy', 'technical_reference')",
            name="ck_document_collection",
        ),
        CheckConstraint("length(trim(title)) >= 2", name="ck_document_title"),
        CheckConstraint(
            "source_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'",
            name="ck_document_version",
        ),
        CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_document_hash"
        ),
        UniqueConstraint(
            "knowledge_type", "source", "source_version",
            name="uq_document_source_version",
        ),
        # Composite parent identity lets the FK also enforce collection isolation.
        UniqueConstraint("id", "knowledge_type", name="uq_document_id_collection"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    knowledge_type: Mapped[str] = mapped_column(String(32))
    source: Mapped[UUID] = mapped_column()
    source_version: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    content_sha256: Mapped[str] = mapped_column(String(64))
    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan",
        passive_deletes=True, lazy="raise",
    )


class KnowledgeChunk(Base):
    """A citation-bearing passage and its prepared local BGE vector."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "knowledge_type"],
            ["knowledge_documents.id", "knowledge_documents.knowledge_type"],
            ondelete="CASCADE", name="fk_chunk_document_collection",
        ),
        CheckConstraint(
            "knowledge_type IN ('company_policy', 'technical_reference')",
            name="ck_chunk_collection",
        ),
        CheckConstraint("chunk_index >= 0", name="ck_chunk_index"),
        CheckConstraint("token_count BETWEEN 1 AND 800", name="ck_chunk_tokens"),
        CheckConstraint(
            "length(trim(chunk_text)) BETWEEN 1 AND 500000", name="ck_chunk_text"
        ),
        CheckConstraint(
            "chunk_sha256 ~ '^[0-9a-f]{64}$'", name="ck_chunk_hash"
        ),
        CheckConstraint(
            "knowledge_type <> 'company_policy' OR citation_id ~ "
            "'^policy:[0-9a-f]{32}:[0-9a-f]{16}:[0-9a-f]{16}:[0-9]{4,}$'",
            name="ck_chunk_policy_citation",
        ),
        CheckConstraint(
            "embedding_model = 'BAAI/bge-small-en-v1.5'", name="ck_chunk_model"
        ),
        # JSONB is reserved for flexible heading context, not arbitrary metadata.
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object' "
            "AND metadata ? 'heading_paths' "
            "AND (metadata - 'heading_paths') = '{}'::jsonb "
            "AND jsonb_typeof(metadata -> 'heading_paths') = 'array'",
            name="ck_chunk_metadata",
        ),
        UniqueConstraint("citation_id", name="uq_chunk_citation"),
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column()
    knowledge_type: Mapped[str] = mapped_column(String(32))
    citation_id: Mapped[str] = mapped_column(String(180))
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_sha256: Mapped[str] = mapped_column(String(64))
    chunk_text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    # SQLAlchemy reserves `metadata`; the physical database column keeps that name.
    chunk_metadata: Mapped[dict[str, list[list[str]]]] = mapped_column("metadata", JSONB)
    embedding_model: Mapped[str] = mapped_column(String(200))
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks", lazy="raise")
