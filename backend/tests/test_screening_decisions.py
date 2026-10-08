"""Trainer-approved hard-requirement policy; synthetic inputs and mocked providers."""
import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.schemas.screening import HardRequirementEvaluation, ScreeningDecisionResult, ScreeningInput
from app.services.screening_matching import ScreeningMatchingError, qualification_facts
from test_screening_matching import (
    FakeMatcher, attribute, criterion, educational_request, education_record,
    fact_refs, request, semantic_result,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Decision tests must not make provider calls.")
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


def scenario(spec):
    # spec contains (criterion ID, desired mocked evidence status, hard flag).
    supplied = request(criteria=tuple(criterion(identity, identifier=identity, hard=hard)
        for identity, status, hard in spec), skills=tuple(identity for identity, status, hard in spec
            if status == "supported") + ("Related synthetic skill",))
    fact = qualification_facts(supplied)[-1]
    responses = [semantic_result(identity, status,
        evidence=fact_refs((fact,)) if status == "ambiguous" else [])
        for identity, status, hard in spec if status != "supported"]
    return supplied, FakeMatcher(responses)


def screen(supplied, matcher):
    return asyncio.run(CandidateScreeningWorkflow(matcher).screen(supplied))


@pytest.mark.parametrize("spec,outcome,missing,ambiguous", [
    ((('python', 'supported', True), ('fastapi', 'supported', True)), "eligible", (), ()),
    ((('docker', 'not_found', True),), "excluded", ('docker',), ()),
    ((('docker', 'not_found', True), ('postgresql', 'not_found', True)), "excluded", ('docker', 'postgresql'), ()),
    ((('web', 'ambiguous', True),), "insufficient_evidence", (), ('web',)),
    ((('web', 'ambiguous', True), ('docker', 'not_found', True)), "excluded", ('docker',), ('web',)),
    ((('python', 'supported', True), ('docker', 'not_found', False)), "eligible", (), ()),
    ((('python', 'supported', True), ('web', 'ambiguous', False)), "eligible", (), ()),
    ((('docker', 'not_found', False),), "eligible", (), ()),
    ((('web', 'ambiguous', False),), "eligible", (), ()),
])
def test_hard_requirement_policy(spec, outcome, missing, ambiguous):
    supplied, matcher = scenario(spec)
    result = screen(supplied, matcher)
    assert result.status == "decision_complete" and result.screening_decision == outcome
    assert result.unmet_hard_requirement_ids == missing
    assert result.ambiguous_hard_requirement_ids == ambiguous
    assert tuple(r.criterion_id for r in result.exclusion_reasons) == missing
    assert result.job_reference == supplied.job_reference and result.upload_id == supplied.upload_id
    for reason in result.exclusion_reasons:
        assert reason.code == "hard_requirement_not_demonstrated"
        assert reason.message == "Hard requirement was not demonstrated in the parsed CV."
        assert set(reason.model_dump()) == {"criterion_id", "code", "message"}
    assert result.matching_result.screening_decision is None
    assert all(not m.evidence for m in result.matching_result.matches if m.match_status == "not_found")


@pytest.mark.parametrize("status", ["source_unavailable", "parsing_failed"])
def test_source_failure_bypasses_evaluation_and_never_excludes(status):
    matcher = FakeMatcher(error=AssertionError("Matching must not run"))
    result = screen(request(status=status), matcher)
    assert result.status == "source_unavailable" and result.screening_decision is None
    assert result.matching_result.parsing_status == status and not result.matching_result.matches
    assert not result.unmet_hard_requirement_ids and not result.exclusion_reasons
    assert not matcher.calls


@pytest.mark.parametrize("code", ["semantic_not_configured", "semantic_provider_failed",
    "invalid_semantic_response", "semantic_input_limit"])
def test_matching_failure_never_excludes(code):
    supplied, _ = scenario((('web', 'ambiguous', True),))
    result = screen(supplied, FakeMatcher(error=ScreeningMatchingError(code)))
    assert result.status == "matching_failed" and result.screening_decision is None
    assert result.matching_result.error_code == code
    assert not result.matching_result.matches and not result.exclusion_reasons
    assert not result.unmet_hard_requirement_ids and not result.ambiguous_hard_requirement_ids


def test_invalid_provider_evidence_is_operational_failure_not_exclusion():
    supplied, _ = scenario((('web', 'ambiguous', True),))
    matcher = FakeMatcher([semantic_result('web', evidence=[{"fact_id": "fact:9999", "value": "Invented"}])])
    result = screen(supplied, matcher)
    assert result.status == "matching_failed" and result.screening_decision is None
    assert result.matching_result.error_code == "invalid_semantic_response"


def test_record_group_safeguard_prevents_ambiguous_education_passing():
    supplied = educational_request((education_record("Bachelor's", "History"),
        education_record("Master's", "Computer Science")))
    facts = qualification_facts(supplied)
    matcher = FakeMatcher([semantic_result(evidence=fact_refs((facts[0], facts[3])))])
    result = screen(supplied, matcher)
    assert result.screening_decision == "insufficient_evidence"
    assert result.ambiguous_hard_requirement_ids == ("c1",)
    assert not result.exclusion_reasons
    assert result.matching_result.matches[0].match_status == "ambiguous"


def test_original_evidence_and_operation_contracts_preserved():
    supplied = request()
    supplied.qualifications.skills[0] = attribute("Python", 2, "ocr")
    matcher = FakeMatcher(error=AssertionError("Exact match should bypass Groq"))
    workflow = CandidateScreeningWorkflow(matcher)
    prepared = asyncio.run(workflow.prepare(supplied))
    matched = asyncio.run(workflow.match(supplied))
    screened = asyncio.run(workflow.screen(supplied))
    assert prepared.status == "ready_for_matching" and prepared.screening_decision is None
    assert matched.status == "matching_complete" and matched.screening_decision is None
    assert screened.screening_decision == "eligible"
    assert screened.matching_result == matched
    assert screened.matching_result.matches[0].evidence[0].source == supplied.qualifications.skills[0].source
    assert not matcher.calls


def test_screen_reuses_one_matching_call_without_decision_call():
    supplied, matcher = scenario((('web', 'ambiguous', True), ('docker', 'not_found', True)))
    result = screen(supplied, matcher)
    assert len(matcher.calls) == 1
    assert [c.criterion_id for c in matcher.calls[0][0]] == ['web', 'docker']
    assert result.screening_decision == "excluded"


@pytest.mark.parametrize("spec,node", [
    ((('python', 'supported', True),), 'build_eligible_result'),
    ((('docker', 'not_found', True),), 'build_excluded_result'),
    ((('web', 'ambiguous', True),), 'build_insufficient_evidence_result'),
])
def test_actual_graph_routes_to_outcome_node(spec, node):
    supplied, matcher = scenario(spec)
    async def execute():
        return [update async for update in CandidateScreeningWorkflow(matcher).graph.astream(
            {"request": supplied, "operation": "screen"}, stream_mode="updates")]
    updates = asyncio.run(execute())
    names = [next(iter(u)) for u in updates]
    assert names[-3:] == ['build_matching_result', 'evaluate_hard_requirements', node]
    assert len(matcher.calls) <= 1


@pytest.mark.parametrize("status", ["source_unavailable", "parsing_failed", "provider_failure"])
def test_actual_failure_route_skips_hard_evaluation(status):
    supplied = request(status=status) if status != "provider_failure" else request(
        criteria=(criterion("Web services"),))
    matcher = FakeMatcher(error=ScreeningMatchingError("semantic_provider_failed"))
    async def execute():
        return [update async for update in CandidateScreeningWorkflow(matcher).graph.astream(
            {"request": supplied, "operation": "screen"}, stream_mode="updates")]
    names = [next(iter(u)) for u in asyncio.run(execute())]
    assert names[-1] == 'build_no_decision_result'
    assert 'evaluate_hard_requirements' not in names


@pytest.mark.parametrize("status", ['source_unavailable', 'parsing_failed'])
def test_evaluator_rejects_incomplete_matching(status):
    matching = asyncio.run(CandidateScreeningWorkflow(FakeMatcher()).match(request(status=status)))
    with pytest.raises(ValueError, match="complete validated matching"):
        HardRequirementEvaluation.from_matching_result(matching)


def test_matching_failure_cannot_be_evaluated_as_missing():
    matching = asyncio.run(CandidateScreeningWorkflow(FakeMatcher(error=ScreeningMatchingError(
        "semantic_provider_failed"))).match(request(criteria=(criterion("Web services"),))))
    with pytest.raises(ValueError, match="complete validated matching"):
        HardRequirementEvaluation.from_matching_result(matching)


@pytest.mark.parametrize("changes", [
    {"screening_decision": "eligible"}, {"unmet_hard_requirement_ids": ()},
    {"exclusion_reasons": ()}, {"score": 99}, {"ranking": 1}, {"contact": {}},
    {"status": "matching_failed"}, {"job_reference": "TT-JOB-FFFFFFFFFFFFFFFF"},
])
def test_decision_contract_rejects_inconsistent_or_unrelated_fields(changes):
    supplied, matcher = scenario((('docker', 'not_found', True),))
    result = screen(supplied, matcher)
    with pytest.raises(ValidationError):
        ScreeningDecisionResult.model_validate({**result.model_dump(), **changes})


def test_input_cannot_supply_unverified_verdict_or_matching_flags():
    supplied = request().model_dump()
    for field in ('screening_decision', 'eligible', 'exclude', 'matching_result', 'hard_evaluation'):
        with pytest.raises(ValidationError):
            ScreeningInput.model_validate({**supplied, field: True})


def test_operational_result_cannot_be_forged_into_exclusion():
    result = screen(request(status='parsing_failed'), FakeMatcher())
    with pytest.raises(ValidationError):
        ScreeningDecisionResult.model_validate({**result.model_dump(), 'screening_decision': 'excluded'})


def test_parsed_empty_qualifications_follow_missing_hard_evidence_policy():
    supplied = request(skills=())
    matcher = FakeMatcher(error=AssertionError("No facts require no provider interpretation"))
    workflow = CandidateScreeningWorkflow(matcher)
    assert asyncio.run(workflow.prepare(supplied)).status == 'ready_for_matching'
    assert asyncio.run(workflow.match(supplied)).matches[0].match_status == 'not_found'
    result = asyncio.run(workflow.screen(supplied))
    assert result.screening_decision == 'excluded' and result.unmet_hard_requirement_ids == ('c1',)
    assert not matcher.calls


@pytest.mark.parametrize("outcome,missing,ambiguous", [
    ('eligible', ('missing',), ()), ('excluded', (), ('uncertain',)),
    ('excluded', ('missing', 'missing'), ()), ('excluded', ('same',), ('same',)),
])
def test_intermediate_evaluation_rejects_contradictory_results(outcome, missing, ambiguous):
    with pytest.raises(ValidationError):
        HardRequirementEvaluation(outcome=outcome, unmet_hard_requirement_ids=missing,
            ambiguous_hard_requirement_ids=ambiguous)
