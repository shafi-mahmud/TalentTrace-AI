from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agents.jd.errors import (
    GenerationProviderError,
    MissingGenerationConfigurationError,
)
from app.core.config import ConfigurationError, settings
from app.db.session import create_database_engine, create_database_session_factory
from app.integrations.llm.groq import (
    GroqJobDescriptionGenerator,
    JobDescriptionGenerationResult,
    JobDescriptionGenerator,
)
from app.rag.retrieval import (
    CompanyPolicyRetriever,
    RetrievedPolicyChunk,
)
from app.rag.embeddings import BGEEmbeddingService
from app.rag.semantic_retrieval import SemanticCompanyPolicyRetriever
from app.repositories.company_policy import CompanyPolicyRepository
from app.schemas.job_description import (
    GeneratedJobDescriptionDraft,
    JobDescriptionGenerationRequest,
    JobDescriptionGenerationResponse,
    PolicyGroundingCitation,
)

logger = logging.getLogger(__name__)


class JobDescriptionWorkflowState(TypedDict, total=False):
    request: JobDescriptionGenerationRequest
    diagnostic_id: str | None
    retrieved_policy_chunks: tuple[RetrievedPolicyChunk, ...]
    generated_draft: GeneratedJobDescriptionDraft
    provider: str
    model: str
    response: JobDescriptionGenerationResponse


class JobDescriptionWorkflow:
    """Bounded retrieve, generate, and validate workflow for JD drafts."""

    def __init__(
        self,
        retriever: CompanyPolicyRetriever,
        generator: JobDescriptionGenerator,
    ) -> None:
        self._retriever = retriever
        self._generator = generator

        builder = StateGraph(JobDescriptionWorkflowState)
        builder.add_node("retrieve_policy_context", self._retrieve_policy_context)
        builder.add_node("generate_draft", self._generate_draft)
        builder.add_node("validate_draft", self._validate_draft)
        builder.add_edge(START, "retrieve_policy_context")
        builder.add_edge("retrieve_policy_context", "generate_draft")
        builder.add_edge("generate_draft", "validate_draft")
        builder.add_edge("validate_draft", END)
        self.graph = builder.compile(checkpointer=False)

    async def generate(
        self,
        request: JobDescriptionGenerationRequest,
        *,
        diagnostic_id: str | None = None,
    ) -> JobDescriptionGenerationResponse:
        try:
            final_state = await self.graph.ainvoke({"request": request, "diagnostic_id": diagnostic_id})
        except Exception as error:
            logger.warning(
                "talenttrace_failure correlation_id=%s stage=langgraph_execution "
                "category=workflow_node_failed exception_class=%s",
                diagnostic_id or "unavailable", type(error).__name__,
            )
            raise
        response = final_state.get("response")
        if not isinstance(response, JobDescriptionGenerationResponse):
            logger.warning(
                "talenttrace_failure correlation_id=%s stage=response_assembly "
                "category=validated_response_missing exception_class=GenerationProviderError",
                diagnostic_id or "unavailable",
            )
            raise GenerationProviderError(
                "The job-description workflow produced no validated response."
            )
        return response

    async def _retrieve_policy_context(
        self,
        state: JobDescriptionWorkflowState,
    ) -> dict[str, Any]:
        try:
            retrieved = await self._retriever.retrieve(state["request"])
        except Exception as error:
            logger.warning(
                "talenttrace_failure correlation_id=%s stage=policy_retrieval "
                "category=policy_context_unavailable exception_class=%s",
                state.get("diagnostic_id") or "unavailable", type(error).__name__,
            )
            raise
        return {"retrieved_policy_chunks": retrieved}

    async def _generate_draft(
        self,
        state: JobDescriptionWorkflowState,
    ) -> dict[str, Any]:
        try:
            result: JobDescriptionGenerationResult = await self._generator.generate(
                state["request"],
                state["retrieved_policy_chunks"],
            )
        except Exception as error:
            logger.warning(
                "talenttrace_failure correlation_id=%s stage=structured_generation "
                "category=generator_failed exception_class=%s",
                state.get("diagnostic_id") or "unavailable", type(error).__name__,
            )
            raise
        return {
            "generated_draft": result.draft,
            "provider": result.provider,
            "model": result.model,
        }

    async def _validate_draft(
        self,
        state: JobDescriptionWorkflowState,
    ) -> dict[str, Any]:
        retrieved_by_citation = {
            item.chunk.metadata.citation_id: item
            for item in state["retrieved_policy_chunks"]
        }
        citation_ids = state["generated_draft"].policy_citation_ids
        unknown_citations = set(citation_ids).difference(retrieved_by_citation)
        if unknown_citations:
            logger.warning(
                "talenttrace_failure correlation_id=%s stage=citation_validation "
                "category=unknown_citation exception_class=GenerationProviderError",
                state.get("diagnostic_id") or "unavailable",
            )
            raise GenerationProviderError(
                "The generated draft referenced unavailable policy context."
            )

        citations = [
            PolicyGroundingCitation(
                citation_id=citation_id,
                source_title=retrieved_by_citation[citation_id].source.title,
                heading_paths=(
                    retrieved_by_citation[citation_id].chunk.metadata.heading_paths
                ),
            )
            for citation_id in citation_ids
        ]
        try:
            from app.rag.screening_policy import policy_screening_suggestions
            response = JobDescriptionGenerationResponse(
                policy_screening_suggestions=policy_screening_suggestions(state["request"], state["retrieved_policy_chunks"]),
                retrieval_mode=self._retriever.retrieval_mode,
                provider=state["provider"],
                model=state["model"],
                job_description=state["generated_draft"],
                grounding_citations=citations,
            )
        except ValidationError as error:
            logger.warning(
                "talenttrace_failure correlation_id=%s stage=response_assembly "
                "category=response_schema_invalid exception_class=%s",
                state.get("diagnostic_id") or "unavailable", type(error).__name__,
            )
            raise GenerationProviderError(
                "The generated draft could not be assembled safely."
            ) from None
        return {"response": response}


@lru_cache(maxsize=1)
def get_job_description_workflow() -> JobDescriptionWorkflow:
    """Build the semantic workflow lazily; never select a policy implicitly."""

    if settings.database_url is None or settings.company_policy_document_id is None:
        raise MissingGenerationConfigurationError(
            "Semantic job-description generation is not configured."
        )
    try:
        engine = create_database_engine(settings)
    except ConfigurationError:
        raise MissingGenerationConfigurationError(
            "Semantic job-description generation is not configured."
        ) from None
    repository = CompanyPolicyRepository(create_database_session_factory(engine))
    return JobDescriptionWorkflow(
        retriever=SemanticCompanyPolicyRetriever(
            repository=repository,
            embedding_service=BGEEmbeddingService(),
            document_id=settings.company_policy_document_id,
        ),
        generator=GroqJobDescriptionGenerator(configuration=settings),
    )
