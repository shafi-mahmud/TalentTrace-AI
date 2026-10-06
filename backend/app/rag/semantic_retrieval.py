"""Semantic company-policy retrieval for one explicitly configured document."""

from __future__ import annotations

import asyncio
from uuid import UUID

from pydantic import ValidationError

from app.rag.embeddings import EmbeddingService
from app.rag.contracts import RetrievalMode
from app.rag.retrieval import PolicyRetrievalError, RetrievedPolicyChunk
from app.repositories.company_policy import CompanyPolicyRepository
from app.schemas.job_description import JobDescriptionGenerationRequest


def build_policy_search_query(request: JobDescriptionGenerationRequest) -> str:
    """Stable labeled recruiter requirements, with no summarization or truncation.

    The BGE adapter enforces its 512-token limit including its query instruction
    and special tokens. A long valid request can therefore fail retrieval safely.
    """
    if not isinstance(request, JobDescriptionGenerationRequest):
        raise PolicyRetrievalError("Validated job requirements are required for policy search.")
    try:
        # Request objects are mutable; validate again before building query text.
        request = JobDescriptionGenerationRequest.model_validate(request.model_dump(warnings=False))
        fields = (
            ("Job title", request.job_title),
            ("Role summary", request.role_summary),
            ("Responsibilities", "; ".join(request.responsibilities)),
            ("Required skills", "; ".join(request.required_skills)),
            ("Preferred skills", "; ".join(request.preferred_skills)),
            ("Department", request.department),
            ("Employment type", request.employment_type.value.replace("_", " ") if request.employment_type else None),
            ("Work arrangement", request.work_arrangement.value.replace("_", " ") if request.work_arrangement else None),
            ("Location", request.location),
            ("Seniority", request.seniority_level),
            ("Minimum experience years", str(request.minimum_experience_years) if request.minimum_experience_years is not None else None),
            ("Education", "; ".join(request.education_requirements)),
        )
        return "\n".join(f"{label}: {value}" for label, value in fields if value is not None and value != "")
    except (ValidationError, ValueError, TypeError):
        raise PolicyRetrievalError("Job requirements could not be prepared for policy search.") from None


class SemanticCompanyPolicyRetriever:
    """Request -> local query embedding -> one explicit document's exact search."""

    retrieval_mode: RetrievalMode = "semantic_bge_pgvector"

    def __init__(
        self,
        *,
        repository: CompanyPolicyRepository,
        embedding_service: EmbeddingService,
        document_id: UUID,
        top_k: int = 4,
    ) -> None:
        if not isinstance(document_id, UUID):
            raise PolicyRetrievalError("A valid company-policy document UUID is required.")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 5:
            raise PolicyRetrievalError("top_k must be an integer between 1 and 5.")
        self._repository = repository
        self._embedding_service = embedding_service
        self._document_id = document_id
        self._top_k = top_k

    async def retrieve(
        self, request: JobDescriptionGenerationRequest,
    ) -> tuple[RetrievedPolicyChunk, ...]:
        query = build_policy_search_query(request)
        try:
            # Loading/tokenizing/encoding is synchronous CPU work, so keep it off
            # the async event loop. The service adds the BGE instruction once.
            vector = await asyncio.to_thread(self._embedding_service.embed_query, query)
        except Exception:
            raise PolicyRetrievalError(
                "The local policy-search query could not be embedded; check model availability and the BGE token limit."
            ) from None
        try:
            return await self._repository.find_nearest_chunks(
                self._document_id, vector, top_k=self._top_k,
            )
        except PolicyRetrievalError:
            raise
        except Exception:
            raise PolicyRetrievalError("Semantic company-policy retrieval failed.") from None
