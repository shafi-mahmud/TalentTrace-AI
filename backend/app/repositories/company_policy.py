from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from numbers import Real
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
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
from app.rag.retrieval import PolicyRetrievalError, RetrievedPolicyChunk


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
    """Persist prepared versions and query one explicit version, without model calls.

    Existing versions are never overwritten. Re-ingestion violates the unique
    constraint and rolls back; a changed document needs a new source_version.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_nearest_chunks(
        self,
        document_id: UUID,
        query_vector: Sequence[float],
        *,
        top_k: int = 4,
    ) -> tuple[RetrievedPolicyChunk, ...]:
        """Exact cosine search in one company-policy document, never all versions.

        No embeddings or arbitrary JSON metadata are returned. This is a vector
        query boundary, not request-to-embedding orchestration or a JD retriever.
        """
        if not isinstance(document_id, UUID):
            raise PolicyRetrievalError("A valid company-policy document UUID is required.")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 5:
            raise PolicyRetrievalError("top_k must be an integer between 1 and 5.")
        try:
            vector = _validate_embedding(query_vector)
        except PolicyPersistenceError:
            raise PolicyRetrievalError("Query vector must be finite, normalized and have 384 dimensions.") from None

        source_query = select(
            KnowledgeDocument.source, KnowledgeDocument.source_version,
            KnowledgeDocument.title, KnowledgeDocument.content_sha256,
        ).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.knowledge_type == COMPANY_POLICY_COLLECTION,
        )
        distance = KnowledgeChunk.embedding.cosine_distance(vector)
        chunk_query = select(
            KnowledgeChunk.citation_id, KnowledgeChunk.chunk_index,
            KnowledgeChunk.chunk_sha256, KnowledgeChunk.chunk_text,
            KnowledgeChunk.token_count, KnowledgeChunk.chunk_metadata,
        ).where(
            KnowledgeChunk.document_id == document_id,
            KnowledgeChunk.knowledge_type == COMPANY_POLICY_COLLECTION,
            KnowledgeChunk.embedding_model == BGE_MODEL_NAME,
            # Zero/corrupt stored vectors have no usable cosine distance.
            distance >= 0, distance <= 2,
        ).order_by(
            distance.asc(), KnowledgeChunk.chunk_index.asc(),
            KnowledgeChunk.citation_id.asc(),
        ).limit(top_k)
        try:
            async with self._session_factory() as session:
                source_row = (await session.execute(source_query)).mappings().one_or_none()
                if source_row is None:
                    raise PolicyRetrievalError("Company-policy document was not found.")
                rows = (await session.execute(chunk_query)).mappings().all()
        except PolicyRetrievalError:
            raise
        except Exception:
            # Keep driver, connection and session-construction failures controlled
            # too. This catch covers only database I/O, not input/output validation.
            raise PolicyRetrievalError("Company-policy database retrieval failed.") from None
        if not rows:
            raise PolicyRetrievalError("No usable company-policy chunks are available for this document.")
        try:
            source = PolicySourceMetadata(
                source_id=source_row["source"], source_version=source_row["source_version"],
                title=source_row["title"], content_sha256=source_row["content_sha256"],
            )
            results = []
            fingerprint = hashlib.sha256(source.source_version.encode("utf-8")).hexdigest()[:16]
            for row in rows:
                metadata = row["chunk_metadata"]
                if not isinstance(metadata, dict) or set(metadata) != {"heading_paths"}:
                    raise ValueError("Invalid stored metadata.")
                chunk = PolicyChunk(
                    text=row["chunk_text"],
                    metadata=PolicyChunkMetadata(
                        citation_id=row["citation_id"], source_id=source.source_id,
                        source_version=source.source_version,
                        source_content_sha256=source.content_sha256,
                        chunk_index=row["chunk_index"], chunk_sha256=row["chunk_sha256"],
                        token_count=row["token_count"], heading_paths=metadata["heading_paths"],
                    ),
                )
                expected = (
                    f"policy:{source.source_id.hex}:{fingerprint}:"
                    f"{source.content_sha256[:16]}:{chunk.metadata.chunk_index:04d}"
                )
                if chunk.metadata.citation_id != expected or chunk.metadata.chunk_sha256 != chunk_sha256(chunk.text):
                    raise ValueError("Invalid stored chunk identity.")
                results.append(RetrievedPolicyChunk(source=source, chunk=chunk))
            return tuple(results)
        except (ValueError, TypeError, KeyError):
            raise PolicyRetrievalError("Stored company-policy context is invalid.") from None

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
