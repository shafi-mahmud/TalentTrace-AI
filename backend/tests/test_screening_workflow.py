"""Synthetic preparation-only graph tests; no provider or database required."""
import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.screening.workflow import CandidateScreeningWorkflow, ScreeningWorkflowState
from app.schemas.candidate_profile import (
    CandidateContact, CandidateProfile, CandidateQualifications, GroundedAttribute, SourceReference,
)
from app.schemas.screening import (
    RequirementContext, ScreeningCriterion, ScreeningInput, ScreeningPreparationResult,
)


def criterion(identifier="python", category="skill", hard=True):
    return ScreeningCriterion(criterion_id=identifier, category=category,
        description="Explicit synthetic job requirement", is_hard=hard)


def request(status="parsed", **updates):
    values = dict(job_reference="TT-JOB-0123456789ABCDEF", upload_id=uuid4(),
        parsing_status=status, qualifications=CandidateQualifications(
            education=[], work_history=[], skills=[]) if status == "parsed" else None,
        criteria=(criterion(), criterion("work", "experience", False),
            criterion("degree", "education", True)))
    values.update(updates)
    return ScreeningInput(**values)


def test_valid_input_and_category_context():
    supplied = request()
    result = asyncio.run(CandidateScreeningWorkflow().prepare(supplied))
    assert result.job_reference == supplied.job_reference
    assert result.upload_id == supplied.upload_id
    assert result.requirement_context == RequirementContext(skill_ids=("python",),
        experience_ids=("work",), education_ids=("degree",), hard_requirement_ids=("python", "degree"))
    assert result.screening_decision is None


@pytest.mark.parametrize("status,expected,branch", [
    ("parsed", "ready_for_matching", "build_ready_result"),
    ("source_unavailable", "source_unavailable", "build_source_unavailable_result"),
    ("parsing_failed", "source_unavailable", "build_source_unavailable_result"),
])
def test_real_graph_conditional_execution(status, expected, branch):
    workflow = CandidateScreeningWorkflow()
    async def execute():
        return [update async for update in workflow.graph.astream(
            {"request": request(status)}, stream_mode="updates")]
    updates = asyncio.run(execute())
    assert [next(iter(update)) for update in updates] == ["validate_screening_input",
        "prepare_requirement_context", "check_candidate_source", branch]
    result = updates[-1][branch]["result"]
    assert result.status == expected
    assert result.parsing_status == status
    assert result.screening_decision is None
    assert set(result.model_dump()) == {"job_reference", "upload_id", "status",
        "parsing_status", "requirement_context", "screening_decision"}
    assert workflow.graph.checkpointer is False


def test_empty_skills_not_exclusion_and_profile_compatibility():
    contact = CandidateContact(candidate_name=None, emails=[], phones=[], links=[], location=None)
    profile = CandidateProfile(upload_id=uuid4(), parsing_status="parsed", contact=contact,
        qualifications=CandidateQualifications(education=[], work_history=[], skills=[]))
    supplied = request(upload_id=profile.upload_id, parsing_status=profile.parsing_status,
        qualifications=profile.qualifications)
    result = asyncio.run(CandidateScreeningWorkflow().prepare(supplied))
    assert result.status == "ready_for_matching"
    assert result.screening_decision is None
    assert set(ScreeningWorkflowState.__annotations__) == {
        "operation", "request", "requirement_context", "source_readiness", "result",
        "facts", "deterministic_results", "unresolved_criteria", "semantic_response",
        "validated_matches", "matching_error"}
    assert "contact" not in supplied.model_dump()


def test_source_backed_qualifications_preserved_without_matching():
    supplied = request(qualifications=CandidateQualifications(education=[], work_history=[],
        skills=[GroundedAttribute(value="Python", source=SourceReference(
            kind="page", number=1, method="ocr"))]))
    async def execute():
        return await CandidateScreeningWorkflow().graph.ainvoke({"request": supplied})
    state = asyncio.run(execute())
    assert state["request"].qualifications == supplied.qualifications
    assert state["request"].qualifications.skills[0].source.method == "ocr"
    assert set(state) == {"request", "requirement_context", "source_readiness", "result"}
    assert state["result"].screening_decision is None


def test_only_hard_and_non_hard_classes_and_stable_input_order():
    supplied = request(criteria=(criterion("z", hard=False), criterion("a", hard=True),
        criterion("m", hard=False)))
    result = asyncio.run(CandidateScreeningWorkflow().prepare(supplied))
    assert result.requirement_context.skill_ids == ("z", "a", "m")
    assert result.requirement_context.hard_requirement_ids == ("a",)


def test_workflow_has_no_database_or_rag_dependencies():
    import ast
    import inspect
    from app.agents.screening import workflow
    imports = [node.module for node in ast.walk(ast.parse(inspect.getsource(workflow)))
        if isinstance(node, ast.ImportFrom)]
    assert not any(module.startswith(("app.db", "app.rag", "app.repositories")) for module in imports)


@pytest.mark.parametrize("updates", [
    {"criteria": ()}, {"criteria": tuple(criterion(str(i)) for i in range(51))},
    {"criteria": (criterion("same"), criterion("SAME"))},
    {"job_reference": "BACKEND-AI-001"}, {"upload_id": "not-a-uuid"},
    {"parsing_status": "eligible"}, {"qualifications": None},
    {"contact": {}}, {"candidate_name": "Synthetic Person"}, {"email": "demo@example.invalid"},
    {"phone": "+15550101234"}, {"gender": "unknown"}, {"raw_cv_text": "Private marker"},
    {"score": 90}, {"model": "custom"},
])
def test_invalid_input_rejected(updates):
    with pytest.raises(ValidationError):
        request(**updates)


@pytest.mark.parametrize("status", ["source_unavailable", "parsing_failed"])
def test_failed_source_cannot_carry_qualifications(status):
    with pytest.raises(ValidationError):
        request(status, qualifications=CandidateQualifications(education=[], work_history=[], skills=[]))


@pytest.mark.parametrize("field,value", [
    ("criterion_id", ""), ("criterion_id", "x" * 65), ("criterion_id", "../file"),
    ("category", "priority"), ("description", "   "), ("description", "x" * 501),
    ("description", "bad\x00text"), ("description", "bad\ntext"),
    ("description", "bad\u202etext"), ("is_hard", "true"), ("is_hard", 1),
    ("priority", "medium"),
])
def test_invalid_criterion(field, value):
    values = criterion().model_dump()
    values[field] = value
    with pytest.raises(ValidationError):
        ScreeningCriterion(**values)


def test_description_normalizes_without_inventing_values():
    supplied = criterion().model_dump()
    supplied["description"] = "  Python experience  "
    assert ScreeningCriterion(**supplied).description == "Python experience"


def test_nested_contact_and_protected_fields_rejected():
    values = request().model_dump()
    for field in ("contact", "name", "email", "age", "gender", "raw_text"):
        invalid = {**values, "qualifications": {**values["qualifications"], field: "marker"}}
        with pytest.raises(ValidationError):
            ScreeningInput.model_validate(invalid)


def test_revalidation_rejects_mutated_upstream_qualification_list():
    supplied = request()
    supplied.qualifications.skills.append({"value": "invented", "source": {}})
    with pytest.raises(ValidationError):
        asyncio.run(CandidateScreeningWorkflow().prepare(supplied))


@pytest.mark.parametrize("changes", [
    {"screening_decision": "eligible"}, {"screening_decision": "excluded"},
    {"screening_decision": "insufficient_evidence"}, {"score": 1},
    {"matching_results": []}, {"status": "eligible"}, {"status": "source_unavailable"},
])
def test_output_cannot_fabricate_decisions_scores_or_matches(changes):
    result = asyncio.run(CandidateScreeningWorkflow().prepare(request()))
    with pytest.raises(ValidationError):
        ScreeningPreparationResult.model_validate({**result.model_dump(), **changes})


@pytest.mark.parametrize("updates", [
    {"skill_ids": ()}, {"experience_ids": ("python",)},
    {"hard_requirement_ids": ("unknown",)}, {"hard_requirement_ids": ("python", "python")},
])
def test_intermediate_context_validation(updates):
    values = dict(skill_ids=("python",), experience_ids=(), education_ids=(),
        hard_requirement_ids=("python",))
    with pytest.raises(ValidationError):
        RequirementContext(**{**values, **updates})
