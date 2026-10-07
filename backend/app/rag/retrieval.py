from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.rag.chunking import ChunkingConfig, chunk_company_policy
from app.rag.contracts import (
    COMPANY_POLICY_COLLECTION,
    CompanyPolicySource,
    PolicyChunk,
    PolicySourceMetadata,
    RetrievalMode,
)
from app.schemas.job_description import JobDescriptionGenerationRequest


DEMO_POLICY_PATH = Path(__file__).resolve().parent / "demo_company_policy.md"
DEMO_POLICY_SOURCE_ID = UUID("6c3edcb7-1a63-4fee-b535-b6155efdbf42")
DEMO_POLICY_TITLE = "Synthetic Demo Company Policy"
DEMO_POLICY_SOURCE_VERSION = "synthetic-demo-v1"
MAX_DEMO_RETRIEVAL_RESULTS = 4

_TERM_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "build",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "role",
    "the",
    "to",
    "with",
}


class PolicyRetrievalError(RuntimeError):
    """Raised when safe company-policy context cannot be retrieved."""


class RetrievedPolicyChunk(BaseModel):
    """A policy chunk paired with validated, trusted source metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk: PolicyChunk
    source: PolicySourceMetadata

    @model_validator(mode="after")
    def source_must_match_chunk(self) -> "RetrievedPolicyChunk":
        metadata = self.chunk.metadata
        if (
            metadata.collection != COMPANY_POLICY_COLLECTION
            or self.source.collection != COMPANY_POLICY_COLLECTION
            or metadata.source_id != self.source.source_id
            or metadata.source_version != self.source.source_version
            or metadata.source_content_sha256 != self.source.content_sha256
        ):
            raise ValueError("Retrieved chunk does not match its company-policy source.")
        return self


class CompanyPolicyRetriever(Protocol):
    """Replaceable interface for company-policy retrieval implementations."""

    retrieval_mode: RetrievalMode

    async def retrieve(
        self,
        request: JobDescriptionGenerationRequest,
    ) -> tuple[RetrievedPolicyChunk, ...]:
        """Return bounded, citation-bearing company-policy context."""


class WhitespaceTokenCounter:
    """Small deterministic counter used only by the non-vector demo adapter."""

    def count_tokens(self, text: str) -> int:
        return len(text.split())


class DeterministicLexicalCompanyPolicyRetriever:
    """Rank demo policy chunks by deterministic lexical overlap."""

    retrieval_mode: RetrievalMode = "deterministic_lexical_demo"

    def __init__(
        self,
        source: CompanyPolicySource,
        chunks: tuple[PolicyChunk, ...],
        *,
        top_k: int = MAX_DEMO_RETRIEVAL_RESULTS,
    ) -> None:
        if not 1 <= top_k <= MAX_DEMO_RETRIEVAL_RESULTS:
            raise ValueError(
                f"top_k must be between 1 and {MAX_DEMO_RETRIEVAL_RESULTS}."
            )
        if not chunks:
            raise PolicyRetrievalError("No usable company-policy chunks are available.")

        source_metadata = source.source_metadata()
        try:
            self._chunks = tuple(
                RetrievedPolicyChunk(chunk=chunk, source=source_metadata)
                for chunk in chunks
            )
        except ValueError as error:
            raise PolicyRetrievalError(
                "Policy retrieval received invalid company-policy context."
            ) from error
        self._top_k = top_k

    async def retrieve(
        self,
        request: JobDescriptionGenerationRequest,
    ) -> tuple[RetrievedPolicyChunk, ...]:
        query_terms = _request_terms(request)
        scored_candidates = [
            (_relevance_score(query_terms, retrieved.chunk), retrieved)
            for retrieved in self._chunks
        ]
        ranked = sorted(
            (candidate for candidate in scored_candidates if candidate[0] > 0),
            key=lambda candidate: (
                -candidate[0],
                candidate[1].chunk.metadata.chunk_index,
                candidate[1].chunk.metadata.citation_id,
            ),
        )
        selected = tuple(retrieved for _, retrieved in ranked[: self._top_k])
        if not selected:
            raise PolicyRetrievalError(
                "No positively relevant company-policy context is available."
            )
        return selected


def load_demo_company_policy_source() -> CompanyPolicySource:
    """Load only the fixed, explicitly synthetic demo policy source."""
    try:
        return CompanyPolicySource(
            source_id=DEMO_POLICY_SOURCE_ID,
            source_version=DEMO_POLICY_SOURCE_VERSION,
            title=DEMO_POLICY_TITLE,
            text=DEMO_POLICY_PATH.read_text(encoding="utf-8"),
        )
    except (OSError, ValueError):
        raise PolicyRetrievalError("Synthetic company-policy context is unavailable.") from None


def create_demo_company_policy_retriever(
    *,
    top_k: int = MAX_DEMO_RETRIEVAL_RESULTS,
) -> DeterministicLexicalCompanyPolicyRetriever:
    """Build the explicitly synthetic, non-vector demo retriever."""

    try:
        source = load_demo_company_policy_source()
        chunks = chunk_company_policy(
            source,
            WhitespaceTokenCounter(),
            ChunkingConfig(chunk_size_tokens=500, overlap_tokens=50),
        )
    except (OSError, ValueError) as error:
        raise PolicyRetrievalError(
            "Synthetic company-policy context is unavailable."
        ) from error

    return DeterministicLexicalCompanyPolicyRetriever(
        source,
        chunks,
        top_k=top_k,
    )


def _request_terms(request: JobDescriptionGenerationRequest) -> set[str]:
    values: list[str] = []
    field_labels = {
        "responsibilities": "responsibilities",
        "required_skills": "required skills",
        "preferred_skills": "preferred skills",
        "education_requirements": "qualifications education",
        "minimum_experience_years": "experience years",
        "employment_type": "employment",
        "work_arrangement": "work arrangement",
    }
    for field_name, value in request.model_dump(
        mode="json", exclude_none=True
    ).items():
        if value == []:
            continue
        if field_name in field_labels:
            values.append(field_labels[field_name])
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value))
    return _terms(" ".join(values))


def _terms(text: str) -> set[str]:
    return {
        term
        for term in _TERM_PATTERN.findall(text.casefold())
        if len(term) > 1 and term not in _STOP_WORDS
    }


def _relevance_score(query_terms: set[str], chunk: PolicyChunk) -> int:
    body_counts = Counter(_TERM_PATTERN.findall(chunk.text.casefold()))
    heading_terms = _terms(
        " ".join(
            heading
            for path in chunk.metadata.heading_paths
            for heading in path
        )
    )
    return sum(
        min(body_counts[term], 3) + (3 if term in heading_terms else 0)
        for term in query_terms
    )
