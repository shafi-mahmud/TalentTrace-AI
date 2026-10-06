from __future__ import annotations

from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agents.jd.errors import GenerationProviderError
from app.integrations.llm.groq import (
    GroqJobDescriptionGenerator,
    JobDescriptionGenerationResult,
    JobDescriptionGenerator,
)
from app.rag.retrieval import (
    CompanyPolicyRetriever,
    RetrievedPolicyChunk,
    create_demo_company_policy_retriever,
)
from app.schemas.job_description import (
    GeneratedJobDescriptionDraft,
    JobDescriptionGenerationRequest,
    JobDescriptionGenerationResponse,
    PolicyGroundingCitation,
)


class JobDescriptionWorkflowState(TypedDict, total=False):
    request: JobDescriptionGenerationRequest
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
    ) -> JobDescriptionGenerationResponse:
        final_state = await self.graph.ainvoke({"request": request})
        response = final_state.get("response")
        if not isinstance(response, JobDescriptionGenerationResponse):
            raise GenerationProviderError(
                "The job-description workflow produced no validated response."
            )
        return response

    async def _retrieve_policy_context(
        self,
        state: JobDescriptionWorkflowState,
    ) -> dict[str, Any]:
        retrieved = await self._retriever.retrieve(state["request"])
        return {"retrieved_policy_chunks": retrieved}

    async def _generate_draft(
        self,
        state: JobDescriptionWorkflowState,
    ) -> dict[str, Any]:
        result: JobDescriptionGenerationResult = await self._generator.generate(
            state["request"],
            state["retrieved_policy_chunks"],
        )
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
            response = JobDescriptionGenerationResponse(
                provider=state["provider"],
                model=state["model"],
                job_description=state["generated_draft"],
                grounding_citations=citations,
            )
        except ValidationError:
            raise GenerationProviderError(
                "The generated draft could not be assembled safely."
            ) from None
        return {"response": response}


@lru_cache(maxsize=1)
def get_job_description_workflow() -> JobDescriptionWorkflow:
    """Build the reusable demo workflow without checkpointing or persistence."""

    return JobDescriptionWorkflow(
        retriever=create_demo_company_policy_retriever(),
        generator=GroqJobDescriptionGenerator(),
    )
