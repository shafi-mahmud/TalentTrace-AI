"""Prepared plain-text policy ingestion; no uploads, paths, or version lifecycle."""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.rag.chunking import chunk_company_policy_for_semantic_retrieval
from app.rag.contracts import CompanyPolicySource
from app.rag.embeddings import BGEEmbeddingService
from app.repositories.company_policy import CompanyPolicyRepository, PolicyPersistenceError


class CompanyPolicyIngestionError(RuntimeError):
    """A stage-specific controlled failure without policy or database details."""


async def ingest_company_policy_source(
    source: CompanyPolicySource,
    *,
    embedding_service: BGEEmbeddingService,
    repository: CompanyPolicyRepository,
) -> UUID:
    """Semantic chunks -> document vectors -> one atomic stored source version."""
    try:
        chunks = await asyncio.to_thread(
            chunk_company_policy_for_semantic_retrieval, source,
            embedding_service=embedding_service,
        )
    except Exception:
        raise CompanyPolicyIngestionError("Semantic policy chunking/tokenization failed.") from None
    try:
        vectors = await asyncio.to_thread(
            embedding_service.embed_documents, [chunk.text for chunk in chunks],
        )
        if len(vectors) != len(chunks):
            raise CompanyPolicyIngestionError("Document embedding failed: expected one vector per chunk.")
    except CompanyPolicyIngestionError:
        raise
    except Exception:
        raise CompanyPolicyIngestionError("Policy document embedding failed.") from None
    try:
        return await repository.save_source_version(source.source_metadata(), chunks, vectors)
    except PolicyPersistenceError as error:
        if str(error) == "Policy source version or chunk conflicts with stored data.":
            raise CompanyPolicyIngestionError(
                "Policy persistence failed: this source version or chunk identity already exists or conflicts with stored data."
            ) from None
        raise CompanyPolicyIngestionError("Policy persistence failed.") from None
    except Exception:
        raise CompanyPolicyIngestionError("Policy persistence failed.") from None
