"""Overall coverage is additive; graph decisions and ranks remain authoritative."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.batch_screening import BatchScreeningItem, overall_requirement_coverage
from app.services.screening_ranking import rank_eligible_candidates
from test_screening_decisions import scenario, screen
from test_screening_matching import FakeMatcher, request


@pytest.mark.parametrize("statuses,coverage", [
    (("supported", "supported", "supported"), "met"),
    (("supported", "not_found", "not_found"), "partially_met"),
    (("not_found", "not_found", "not_found"), "unmet"),
    (("supported", "ambiguous", "not_found"), "uncertain"),
    (("ambiguous", "ambiguous", "ambiguous"), "uncertain"),
])
def test_coverage_and_response_consistency(statuses, coverage):
    supplied, matcher = scenario(tuple((f"c{i}", status, False) for i, status in enumerate(statuses)))
    result = screen(supplied, matcher)
    before = result.model_dump()
    assert overall_requirement_coverage(result) == coverage
    item = BatchScreeningItem(upload_id=result.upload_id, result=result, error_code=None, overall_coverage=coverage)
    assert item.model_dump()["overall_coverage"] == coverage
    assert result.model_dump() == before
    assert result.screening_decision == "eligible"
    for incorrect in {"met", "partially_met", "unmet", "uncertain", "not_evaluated"} - {coverage}:
        with pytest.raises(ValidationError):
            BatchScreeningItem(upload_id=result.upload_id, result=result, error_code=None, overall_coverage=incorrect)


@pytest.mark.parametrize("source", ["source_unavailable", "parsing_failed", "provider"])
def test_failures_are_not_evaluated(source):
    supplied = request(status=source if source != "provider" else "parsed", skills=("Unrelated",))
    result = screen(supplied, FakeMatcher(error=RuntimeError("Synthetic failure")))
    assert overall_requirement_coverage(result) == "not_evaluated"
    assert result.screening_decision is None
    assert BatchScreeningItem(upload_id=result.upload_id, result=result, error_code=None,
                             overall_coverage="not_evaluated")


def test_unexpected_processing_failure_is_not_evaluated():
    assert overall_requirement_coverage(None) == "not_evaluated"
    assert BatchScreeningItem(upload_id=uuid4(), result=None, error_code="screening_processing_failed", overall_coverage="not_evaluated")


def test_partial_coverage_does_not_override_mandatory_exclusion():
    supplied, matcher = scenario((("python", "supported", True), ("fastapi", "not_found", True)))
    result = screen(supplied, matcher)
    assert overall_requirement_coverage(result) == "partially_met"
    assert result.screening_decision == "excluded" and result.unmet_hard_requirement_ids == ("fastapi",)
    assert rank_eligible_candidates([result], job_reference=result.job_reference, criteria=supplied.criteria) == []


def test_zero_support_preferred_criteria_remain_eligible_with_equal_zero_ranks():
    supplied, matcher = scenario((("docker", "not_found", False),))
    a = screen(supplied, matcher)
    b = screen(supplied.model_copy(update={"upload_id": uuid4()}), matcher)
    before = rank_eligible_candidates([a, b], job_reference=a.job_reference, criteria=supplied.criteria)
    assert overall_requirement_coverage(a) == overall_requirement_coverage(b) == "unmet"
    assert a.screening_decision == b.screening_decision == "eligible"
    assert all(r["rank"] == 1 and r["tied"] and r["supported_count"] == 0 for r in before)
    assert before == rank_eligible_candidates([a, b], job_reference=a.job_reference, criteria=supplied.criteria)


def test_uncertain_overall_coverage_preserves_hard_requirement_precedence():
    supplied, matcher = scenario((("python", "ambiguous", True), ("docker", "not_found", True)))
    result = screen(supplied, matcher)
    assert overall_requirement_coverage(result) == "uncertain"
    assert result.screening_decision == "excluded"
    assert result.unmet_hard_requirement_ids == ("docker",)
    assert result.ambiguous_hard_requirement_ids == ("python",)
