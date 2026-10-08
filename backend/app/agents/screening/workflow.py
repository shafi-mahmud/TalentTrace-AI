"""Preparation, hybrid evidence matching and deterministic screening routing."""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.schemas.screening import (
    HardRequirementEvaluation, MatchingErrorCode, QualificationFact, RequirementContext, RequirementMatch,
    ScreeningDecisionResult, ScreeningExclusionReason,
    ScreeningCriterion, ScreeningInput, ScreeningMatchingResult, ScreeningPreparationResult,
    SemanticMatchingResponse,
)
from app.integrations.llm.screening import GroqSemanticRequirementMatcher, SemanticRequirementMatcher
from app.services.screening_matching import (
    ScreeningMatchingError, deterministic_matches, qualification_facts, validate_semantic_matches,
)


class ScreeningWorkflowState(TypedDict, total=False):
    operation: Literal["prepare", "match", "screen"]
    request: ScreeningInput
    requirement_context: RequirementContext
    source_readiness: Literal["ready", "unavailable"]
    facts: tuple[QualificationFact, ...]
    deterministic_results: tuple[RequirementMatch, ...]
    unresolved_criteria: tuple[ScreeningCriterion, ...]
    semantic_response: SemanticMatchingResponse
    validated_matches: tuple[RequirementMatch, ...]
    matching_error: MatchingErrorCode
    matching_result: ScreeningMatchingResult
    hard_evaluation: HardRequirementEvaluation
    result: ScreeningPreparationResult | ScreeningMatchingResult | ScreeningDecisionResult


class CandidateScreeningWorkflow:
    def __init__(self, semantic_matcher: SemanticRequirementMatcher | None = None) -> None:
        self._semantic_matcher = semantic_matcher if semantic_matcher is not None else GroqSemanticRequirementMatcher()
        builder = StateGraph(ScreeningWorkflowState)
        builder.add_node("validate_screening_input", self._validate_screening_input)
        builder.add_node("prepare_requirement_context", self._prepare_requirement_context)
        builder.add_node("check_candidate_source", self._check_candidate_source)
        builder.add_node("build_ready_result", self._build_ready_result)
        builder.add_node("build_source_unavailable_result", self._build_source_unavailable_result)
        builder.add_node("match_direct_evidence", self._match_direct_evidence)
        builder.add_node("interpret_unresolved_requirements", self._interpret_unresolved_requirements)
        builder.add_node("validate_matching_evidence", self._validate_matching_evidence)
        builder.add_node("build_matching_result", self._build_matching_result)
        builder.add_node("evaluate_hard_requirements", self._evaluate_hard_requirements)
        builder.add_node("build_eligible_result", self._build_eligible_result)
        builder.add_node("build_excluded_result", self._build_excluded_result)
        builder.add_node("build_insufficient_evidence_result", self._build_insufficient_evidence_result)
        builder.add_node("build_no_decision_result", self._build_no_decision_result)
        builder.add_edge(START, "validate_screening_input")
        builder.add_edge("validate_screening_input", "prepare_requirement_context")
        builder.add_edge("prepare_requirement_context", "check_candidate_source")
        builder.add_conditional_edges("check_candidate_source", self._route_source, {
            "prepare": "build_ready_result",
            "match": "match_direct_evidence",
            "unavailable": "build_source_unavailable_result",
        })
        builder.add_edge("build_ready_result", END)
        builder.add_conditional_edges("build_source_unavailable_result", self._route_after_unavailable, {
            "no_decision": "build_no_decision_result", "end": END,
        })
        builder.add_conditional_edges("match_direct_evidence", self._route_unresolved, {
            "semantic": "interpret_unresolved_requirements", "validate": "validate_matching_evidence",
        })
        builder.add_edge("interpret_unresolved_requirements", "validate_matching_evidence")
        builder.add_edge("validate_matching_evidence", "build_matching_result")
        builder.add_conditional_edges("build_matching_result", self._route_after_matching, {
            "evaluate": "evaluate_hard_requirements", "no_decision": "build_no_decision_result", "end": END,
        })
        builder.add_conditional_edges("evaluate_hard_requirements", self._route_decision, {
            "eligible": "build_eligible_result", "excluded": "build_excluded_result",
            "insufficient_evidence": "build_insufficient_evidence_result",
        })
        for node in ("build_eligible_result", "build_excluded_result", "build_insufficient_evidence_result",
                "build_no_decision_result"):
            builder.add_edge(node, END)
        self.graph = builder.compile(checkpointer=False)

    async def prepare(self, request: ScreeningInput) -> ScreeningPreparationResult:
        final_state = await self.graph.ainvoke({"request": request})
        return ScreeningPreparationResult.model_validate(final_state["result"].model_dump())

    async def match(self, request: ScreeningInput) -> ScreeningMatchingResult:
        final_state = await self.graph.ainvoke({"request": request, "operation": "match"})
        return ScreeningMatchingResult.model_validate(final_state["result"].model_dump())

    async def screen(self, request: ScreeningInput) -> ScreeningDecisionResult:
        final_state = await self.graph.ainvoke({"request": request, "operation": "screen"})
        return ScreeningDecisionResult.model_validate(final_state["result"].model_dump(warnings=False))

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

    def _route_source(self, state: ScreeningWorkflowState) -> Literal["prepare", "match", "unavailable"]:
        if state["source_readiness"] == "unavailable":
            return "unavailable"
        return "prepare" if state.get("operation", "prepare") == "prepare" else "match"

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
        if state.get("operation") in {"match", "screen"}:
            request = state["request"]
            matching = ScreeningMatchingResult(job_reference=request.job_reference,
                upload_id=request.upload_id, parsing_status=request.parsing_status,
                requirement_context=state["requirement_context"], status="source_unavailable",
                matches=(), error_code=None)
            return {"result": matching, "matching_result": matching}
        return self._result(state, "source_unavailable")

    def _match_direct_evidence(self, state: ScreeningWorkflowState) -> dict:
        facts = qualification_facts(state["request"])
        results, unresolved = deterministic_matches(state["request"].criteria, facts)
        return {"facts": facts, "deterministic_results": results, "unresolved_criteria": unresolved}

    def _route_unresolved(self, state: ScreeningWorkflowState) -> Literal["semantic", "validate"]:
        return "semantic" if state["unresolved_criteria"] else "validate"

    async def _interpret_unresolved_requirements(self, state: ScreeningWorkflowState) -> dict:
        try:
            response = await self._semantic_matcher.match(state["unresolved_criteria"], state["facts"])
            return {"semantic_response": response}
        except ScreeningMatchingError as exc:
            return {"matching_error": exc.code}
        except Exception:
            return {"matching_error": "semantic_provider_failed"}

    def _validate_matching_evidence(self, state: ScreeningWorkflowState) -> dict:
        if state.get("matching_error"):
            return {"validated_matches": ()}
        try:
            semantic = validate_semantic_matches(state["semantic_response"], state["unresolved_criteria"],
                state["facts"]) if state["unresolved_criteria"] else ()
            by_id = {r.criterion_id: r for r in state["deterministic_results"] + semantic}
            return {"validated_matches": tuple(by_id[c.criterion_id] for c in state["request"].criteria)}
        except ScreeningMatchingError as exc:
            return {"matching_error": exc.code, "validated_matches": ()}

    def _build_matching_result(self, state: ScreeningWorkflowState) -> dict:
        request = state["request"]
        error = state.get("matching_error")
        matching = ScreeningMatchingResult(job_reference=request.job_reference,
            upload_id=request.upload_id, parsing_status=request.parsing_status,
            requirement_context=state["requirement_context"],
            status="matching_failed" if error else "matching_complete",
            matches=state["validated_matches"], error_code=error)
        return {"result": matching, "matching_result": matching}

    def _route_after_unavailable(self, state: ScreeningWorkflowState) -> Literal["no_decision", "end"]:
        return "no_decision" if state.get("operation") == "screen" else "end"

    def _route_after_matching(self, state: ScreeningWorkflowState) -> Literal["evaluate", "no_decision", "end"]:
        if state.get("operation") != "screen":
            return "end"
        return "evaluate" if state["matching_result"].status == "matching_complete" else "no_decision"

    def _evaluate_hard_requirements(self, state: ScreeningWorkflowState) -> dict:
        return {"hard_evaluation": HardRequirementEvaluation.from_matching_result(state["matching_result"])}

    def _route_decision(self, state: ScreeningWorkflowState) -> Literal["eligible", "excluded", "insufficient_evidence"]:
        return state["hard_evaluation"].outcome

    def _decision_result(self, state: ScreeningWorkflowState) -> dict:
        matching = state["matching_result"]
        evaluation = state.get("hard_evaluation")
        missing = evaluation.unmet_hard_requirement_ids if evaluation is not None else ()
        return {"result": ScreeningDecisionResult(job_reference=matching.job_reference,
            upload_id=matching.upload_id,
            status="decision_complete" if evaluation is not None else matching.status,
            screening_decision=evaluation.outcome if evaluation is not None else None,
            matching_result=matching, unmet_hard_requirement_ids=missing,
            ambiguous_hard_requirement_ids=evaluation.ambiguous_hard_requirement_ids if evaluation is not None else (),
            exclusion_reasons=tuple(ScreeningExclusionReason(criterion_id=identity) for identity in missing))}

    def _build_eligible_result(self, state: ScreeningWorkflowState) -> dict:
        return self._decision_result(state)

    def _build_excluded_result(self, state: ScreeningWorkflowState) -> dict:
        return self._decision_result(state)

    def _build_insufficient_evidence_result(self, state: ScreeningWorkflowState) -> dict:
        return self._decision_result(state)

    def _build_no_decision_result(self, state: ScreeningWorkflowState) -> dict:
        return self._decision_result(state)
