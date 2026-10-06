from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from numbers import Real
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import KnowledgeChunk, KnowledgeDocument
from app.rag.contracts import (
    COMPANY_POLICY_COLLECTION,
    PolicyChunk,
    PolicyChunkMetadata,
    PolicySourceMetadata,
    chunk_sha256,
)
from app.rag.embeddings import BGE_EMBEDDING_DIMENSION, BGE_MODEL_NAME


class PolicyPersistenceError(ValueError):
    """Controlled persistence failure; never includes policy text or credentials."""


def _validate_embedding(values: Sequence[float]) -> list[float]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise PolicyPersistenceError("Embedding must be a numeric sequence.")
    if len(values) != BGE_EMBEDDING_DIMENSION:
        raise PolicyPersistenceError("Embedding must have exactly 384 dimensions.")
    if any(isinstance(value, bool) or not isinstance(value, Real) for value in values):
        raise PolicyPersistenceError("Embedding must contain finite numbers.")
    try:
        vector = [float(value) for value in values]
    except (OverflowError, TypeError, ValueError):
        raise PolicyPersistenceError("Embedding must contain finite numbers.") from None
    if not all(math.isfinite(value) for value in vector):
        raise PolicyPersistenceError("Embedding must contain finite numbers.")
    # Prepared BGE vectors are already normalized; persistence must not alter them.
    if not math.isclose(math.hypot(*vector), 1.0, rel_tol=1e-5, abs_tol=1e-5):
        raise PolicyPersistenceError("Embedding must be normalized and non-zero.")
    return vector


class CompanyPolicyRepository:
    """Write a complete prepared source version, without retrieval or model calls.

    Existing versions are never overwritten. Re-ingestion violates the unique
    constraint and rolls back; a changed document needs a new source_version.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_source_version(
        self,
        source: PolicySourceMetadata,
        chunks: Sequence[PolicyChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> UUID:
        # Revalidate even frozen objects: model_copy/model_construct can bypass
        # Pydantic validation. All failures are sanitized before entering a session.
        if not isinstance(source, PolicySourceMetadata):
            raise PolicyPersistenceError("Validated company-policy metadata is required.")
        if set(vars(source)) - set(PolicySourceMetadata.model_fields):
            raise PolicyPersistenceError("Undeclared source metadata is not allowed.")
        if (
            isinstance(chunks, (str, bytes)) or not isinstance(chunks, Sequence)
            or isinstance(embeddings, (str, bytes)) or not isinstance(embeddings, Sequence)
        ):
            raise PolicyPersistenceError("Policy chunks and embeddings must be sequences.")
        try:
            source = PolicySourceMetadata.model_validate(source.model_dump())
            if not chunks or len(chunks) != len(embeddings):
                raise PolicyPersistenceError("Provide one embedding for each policy chunk.")
            if any(
                not isinstance(chunk, PolicyChunk)
                or not isinstance(chunk.metadata, PolicyChunkMetadata)
                for chunk in chunks
            ):
                raise PolicyPersistenceError("Validated policy chunks are required.")
            if any(
                set(vars(chunk)) - set(PolicyChunk.model_fields)
                or set(vars(chunk.metadata)) - set(PolicyChunkMetadata.model_fields)
                for chunk in chunks
            ):
                raise PolicyPersistenceError("Undeclared chunk metadata is not allowed.")
            prepared = [PolicyChunk.model_validate(chunk.model_dump()) for chunk in chunks]
        except ValidationError:
            raise PolicyPersistenceError("Invalid company-policy source or chunk metadata.") from None

        document = KnowledgeDocument(
            id=uuid4(), knowledge_type=COMPANY_POLICY_COLLECTION,
            source=source.source_id, source_version=source.source_version,
            title=source.title, content_sha256=source.content_sha256,
        )
        version_fingerprint = hashlib.sha256(source.source_version.encode("utf-8")).hexdigest()[:16]
        rows = []
        for index, (chunk, embedding) in enumerate(zip(prepared, embeddings, strict=True)):
            metadata = chunk.metadata
            expected_citation = (
                f"policy:{source.source_id.hex}:{version_fingerprint}:"
                f"{source.content_sha256[:16]}:{index:04d}"
            )
            if (
                metadata.collection != COMPANY_POLICY_COLLECTION
                or metadata.source_id != source.source_id
                or metadata.source_version != source.source_version
                or metadata.source_content_sha256 != source.content_sha256
                or metadata.chunk_index != index
                or metadata.citation_id != expected_citation
                or metadata.chunk_sha256 != chunk_sha256(chunk.text)
                or not chunk.text.strip()
            ):
                raise PolicyPersistenceError("Chunk identity does not match its source version and order.")
            rows.append(KnowledgeChunk(
                id=uuid4(), document_id=document.id,
                knowledge_type=COMPANY_POLICY_COLLECTION,
                citation_id=metadata.citation_id, chunk_index=index,
                chunk_sha256=metadata.chunk_sha256, chunk_text=chunk.text,
                token_count=metadata.token_count,
                chunk_metadata={"heading_paths": [list(path) for path in metadata.heading_paths]},
                embedding_model=BGE_MODEL_NAME, embedding=_validate_embedding(embedding),
            ))
        document.chunks = rows

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    session.add(document)  # Cascades to every prepared chunk.
                    await session.flush()  # Surface constraint failures before commit.
        except IntegrityError:
            raise PolicyPersistenceError("Policy source version or chunk conflicts with stored data.") from None
        except SQLAlchemyError:
            raise PolicyPersistenceError("Policy source version could not be stored.") from None
        return document.id
