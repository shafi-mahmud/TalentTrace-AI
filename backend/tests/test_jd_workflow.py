import asyncio
from uuid import UUID

import pytest

from app.agents.jd.errors import GenerationProviderError
from app.agents.jd.workflow import JobDescriptionWorkflow
from app.integrations.llm.groq import JobDescriptionGenerationResult
from app.rag.chunking import chunk_company_policy
from app.rag.contracts import CompanyPolicySource
from app.rag.retrieval import RetrievedPolicyChunk, WhitespaceTokenCounter
from app.schemas.job_description import (
    GeneratedJobDescriptionDraft,
    JobDescriptionGenerationRequest,
)


def request_contract() -> JobDescriptionGenerationRequest:
    return JobDescriptionGenerationRequest(
        job_title="Backend Engineer",
        role_summary="Build and maintain secure backend services for TalentTrace AI.",
        responsibilities=["Develop well-tested FastAPI endpoints"],
        required_skills=["Python"],
    )


def retrieved_context() -> tuple[RetrievedPolicyChunk, ...]:
    source = CompanyPolicySource(
        source_id=UUID("c5d924d8-0ec6-4d50-b735-1aa0bd0aee71"),
        source_version="synthetic-test-v1",
        title="Trusted Synthetic Test Policy",
        text="# Equal Opportunity\n\nUse job-related and inclusive criteria.",
    )
    chunk = chunk_company_policy(source, WhitespaceTokenCounter())[0]
    return (RetrievedPolicyChunk(chunk=chunk, source=source.source_metadata()),)


def draft_with_citation(citation_id: str) -> GeneratedJobDescriptionDraft:
    return GeneratedJobDescriptionDraft(
        title="Backend Engineer",
        summary="Build reliable backend services using secure engineering practices.",
        responsibilities=["Develop well-tested FastAPI endpoints"],
        required_skills=["Python"],
        preferred_skills=[],
        qualifications=["Relevant professional experience or equivalent learning"],
        policy_citation_ids=[citation_id],
    )


class FakeRetriever:
    def __init__(
        self,
        context: tuple[RetrievedPolicyChunk, ...],
        events: list[str],
    ) -> None:
        self._context = context
        self._events = events

    async def retrieve(
        self,
        _request: JobDescriptionGenerationRequest,
    ) -> tuple[RetrievedPolicyChunk, ...]:
        self._events.append("retrieve")
        return self._context


class FakeGenerator:
    def __init__(
        self,
        draft: GeneratedJobDescriptionDraft,
        events: list[str],
    ) -> None:
        self._draft = draft
        self._events = events

    async def generate(
        self,
        _request: JobDescriptionGenerationRequest,
        policy_context: tuple[RetrievedPolicyChunk, ...],
    ) -> JobDescriptionGenerationResult:
        assert policy_context
        self._events.append("generate")
        return JobDescriptionGenerationResult(
            draft=self._draft,
            model="openai/gpt-oss-120b",
        )


def test_workflow_retrieves_generates_and_validates_trusted_citation() -> None:
    events: list[str] = []
    context = retrieved_context()
    citation_id = context[0].chunk.metadata.citation_id
    workflow = JobDescriptionWorkflow(
        FakeRetriever(context, events),
        FakeGenerator(draft_with_citation(citation_id), events),
    )

    response = asyncio.run(workflow.generate(request_contract()))

    assert events == ["retrieve", "generate"]
    assert response.status == "draft"
    assert response.human_review_required is True
    assert response.retrieval_mode == "deterministic_lexical_demo"
    assert response.grounding_citations[0].citation_id == citation_id
    assert response.grounding_citations[0].source_title == (
        "Trusted Synthetic Test Policy"
    )
    graph_nodes = set(workflow.graph.get_graph().nodes)
    assert {
        "retrieve_policy_context",
        "generate_draft",
        "validate_draft",
    }.issubset(graph_nodes)


def test_workflow_rejects_fabricated_model_citation() -> None:
    events: list[str] = []
    context = retrieved_context()
    fabricated_id = (
        "policy:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:bbbbbbbbbbbbbbbb:"
        "cccccccccccccccc:0000"
    )
    workflow = JobDescriptionWorkflow(
        FakeRetriever(context, events),
        FakeGenerator(draft_with_citation(fabricated_id), events),
    )

    with pytest.raises(GenerationProviderError):
        asyncio.run(workflow.generate(request_contract()))


def test_public_grounding_metadata_comes_from_retrieval_not_generation() -> None:
    context = retrieved_context()
    citation_id = context[0].chunk.metadata.citation_id
    workflow = JobDescriptionWorkflow(
        FakeRetriever(context, []),
        FakeGenerator(draft_with_citation(citation_id), []),
    )

    response = asyncio.run(workflow.generate(request_contract()))

    assert response.grounding_citations[0].source_title == context[0].source.title
    assert response.grounding_citations[0].heading_paths == (
        context[0].chunk.metadata.heading_paths
    )
