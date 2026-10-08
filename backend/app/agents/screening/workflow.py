"""Initial bounded Screening graph; matching and decisions are future nodes."""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.schemas.screening import (
    RequirementContext, ScreeningInput, ScreeningPreparationResult,
)


class ScreeningWorkflowState(TypedDict, total=False):
    request: ScreeningInput
    requirement_context: RequirementContext
    source_readiness: Literal["ready", "unavailable"]
    result: ScreeningPreparationResult


class CandidateScreeningWorkflow:
    def __init__(self) -> None:
        builder = StateGraph(ScreeningWorkflowState)
        builder.add_node("validate_screening_input", self._validate_screening_input)
        builder.add_node("prepare_requirement_context", self._prepare_requirement_context)
        builder.add_node("check_candidate_source", self._check_candidate_source)
        builder.add_node("build_ready_result", self._build_ready_result)
        builder.add_node("build_source_unavailable_result", self._build_source_unavailable_result)
        builder.add_edge(START, "validate_screening_input")
        builder.add_edge("validate_screening_input", "prepare_requirement_context")
        builder.add_edge("prepare_requirement_context", "check_candidate_source")
        builder.add_conditional_edges("check_candidate_source", self._route_source, {
            "ready": "build_ready_result",
            "unavailable": "build_source_unavailable_result",
        })
        builder.add_edge("build_ready_result", END)
        builder.add_edge("build_source_unavailable_result", END)
        self.graph = builder.compile(checkpointer=False)

    async def prepare(self, request: ScreeningInput) -> ScreeningPreparationResult:
        final_state = await self.graph.ainvoke({"request": request})
        return ScreeningPreparationResult.model_validate(final_state["result"].model_dump())

    def _validate_screening_input(self, state: ScreeningWorkflowState) -> dict:
        # Revalidate nested values too: upstream models contain mutable lists.
        request = ScreeningInput.model_validate(state["request"].model_dump(warnings=False))
        return {"request": request}

    def _prepare_requirement_context(self, state: ScreeningWorkflowState) -> dict:
        criteria = state["request"].criteria
        return {"requirement_context": RequirementContext(
            skill_ids=tuple(c.criterion_id for c in criteria if c.category == "skill"),
            experience_ids=tuple(c.criterion_id for c in criteria if c.category == "experience"),
            education_ids=tuple(c.criterion_id for c in criteria if c.category == "education"),
            hard_requirement_ids=tuple(c.criterion_id for c in criteria if c.is_hard),
        )}

    def _check_candidate_source(self, state: ScreeningWorkflowState) -> dict:
        request = state["request"]
        ready = request.parsing_status == "parsed" and request.qualifications is not None
        return {"source_readiness": "ready" if ready else "unavailable"}

    def _route_source(self, state: ScreeningWorkflowState) -> Literal["ready", "unavailable"]:
        return state["source_readiness"]

    def _result(self, state: ScreeningWorkflowState,
                status: Literal["ready_for_matching", "source_unavailable"]) -> dict:
        request = state["request"]
        return {"result": ScreeningPreparationResult(
            job_reference=request.job_reference, upload_id=request.upload_id,
            status=status, parsing_status=request.parsing_status,
            requirement_context=state["requirement_context"],
        )}

    def _build_ready_result(self, state: ScreeningWorkflowState) -> dict:
        return self._result(state, "ready_for_matching")

    def _build_source_unavailable_result(self, state: ScreeningWorkflowState) -> dict:
        return self._result(state, "source_unavailable")
