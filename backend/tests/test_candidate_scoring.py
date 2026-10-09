"""F2 synthetic evidence only; real screening contracts, no provider calls."""
import pytest
from pydantic import ValidationError

from app.schemas.candidate_score import ScoringWeights
from app.schemas.screening import ScreeningDecisionResult
from app.services.candidate_scoring import score_candidate
from test_screening_ranking import decision, REFERENCE


def scored(statuses, categories=None, hard=False, weights=None):
    result, criteria = decision(statuses, 1, hard=hard)
    if categories:
        criteria = tuple(c.model_copy(update={"category": category}) for c, category in zip(criteria, categories))
        payload = result.model_dump()
        context = payload["matching_result"]["requirement_context"]
        for category in ("skill", "experience", "education"):
            context[f"{category}_ids"] = tuple(c.criterion_id for c in criteria if c.category == category)
        result = ScreeningDecisionResult.model_validate(payload)
    before = result.model_dump()
    output = score_candidate(result, job_reference=REFERENCE, criteria=criteria, weights=weights)
    assert result.model_dump() == before
    return output, result, criteria


@pytest.mark.parametrize("values", [{"skill": 60}, {"skill": -1, "experience": 81, "education": 20},
    {"skill": 101, "experience": 0, "education": 0}, {"skill": 50.0}, {"skill": True}, {"extra": 1}])
def test_invalid_weights(values):
    with pytest.raises(ValidationError):
        ScoringWeights(**values)


def test_all_dimensions_breakdown_and_original_provenance():
    score, original, _ = scored(["supported", "not_found", "supported", "not_found"],
        ["skill", "skill", "experience", "education"])
    assert score.status == "scored" and score.score == 55
    assert [d.coverage_percent for d in score.dimensions] == [50, 100, 0]
    assert [d.weighted_points for d in score.dimensions] == [25, 30, 0]
    assert score.dimensions[0].matches[0].evidence == original.matching_result.matches[0].evidence
    assert score.dimensions[0].matches[1].evidence == ()
    assert score.screening_decision == "eligible"


@pytest.mark.parametrize("status,expected", [("supported", 100), ("not_found", 0)])
def test_boundaries_and_custom_weights(status, expected):
    output, _, _ = scored([status], weights=ScoringWeights(skill=100, experience=0, education=0))
    assert output.score == expected
    assert output.dimensions[1].coverage_percent is None
    assert output.dimensions[1].weighted_points == 0


def test_rounding_and_repeatability():
    output, result, criteria = scored(["supported", "not_found", "not_found"],
        weights=ScoringWeights(skill=100, experience=0, education=0))
    assert output.score == 33.33
    assert score_candidate(result, job_reference=REFERENCE, criteria=criteria, weights=output.weights) == output


@pytest.mark.parametrize("statuses,hard,reason", [(["supported"], False, "missing_dimension_criteria"),
    (["ambiguous"], False, "uncertain_evidence"), (["not_found"], True, "not_eligible"),
    (["ambiguous"], True, "not_eligible")])
def test_missing_uncertain_or_excluded_evidence_has_no_score(statuses, hard, reason):
    output, original, _ = scored(statuses, hard=hard)
    assert output.status == "not_evaluated" and output.reason == reason
    assert output.score is None and output.dimensions == ()
    assert output.screening_decision == original.screening_decision


@pytest.mark.parametrize("status", ["source_unavailable", "parsing_failed", "parsed"])
def test_processing_failures_do_not_score(status):
    from test_screening_matching import request, FakeMatcher
    from test_screening_decisions import screen
    supplied = request(status=status, skills=("Unrelated",))
    result = screen(supplied, FakeMatcher(error=RuntimeError("Synthetic failure")))
    output = score_candidate(result, job_reference=result.job_reference, criteria=supplied.criteria)
    assert output.reason == "screening_incomplete" and output.score is None
    assert output.screening_decision is None


def test_revalidates_weights_results_and_job_identity():
    output, result, criteria = scored(["supported"], weights=ScoringWeights(skill=100, experience=0, education=0))
    with pytest.raises(ValueError):
        score_candidate(result, job_reference="TT-JOB-FFFFFFFFFFFFFFFF", criteria=criteria)
    with pytest.raises(ValidationError):
        score_candidate(result, job_reference=REFERENCE, criteria=criteria,
            weights=output.weights.model_copy(update={"skill": 99}))
    with pytest.raises(ValueError):
        score_candidate(result, job_reference=REFERENCE, criteria=(criteria[0].model_copy(update={"category": "education"}),))


def test_semantic_support_uses_same_points_and_source_references():
    from test_screening_matching import request, FakeMatcher, fact_refs, semantic_result
    from test_screening_decisions import scenario, screen
    from app.services.screening_matching import qualification_facts
    supplied, _ = scenario((("skill-0", "supported", False),))
    supplied = supplied.model_copy(update={"qualifications": request(skills=("Django",)).qualifications})
    facts = qualification_facts(supplied)
    result = screen(supplied, FakeMatcher([semantic_result("skill-0", evidence=fact_refs((facts[0],)))]))
    output = score_candidate(result, job_reference=REFERENCE, criteria=supplied.criteria,
        weights=ScoringWeights(skill=100, experience=0, education=0))
    assert output.score == 100 and output.dimensions[0].matches[0].match_method == "semantic"
    assert output.dimensions[0].matches[0].evidence[0].source == facts[0].source


def test_fabricated_breakdowns_and_totals_are_rejected():
    from app.schemas.candidate_score import CandidateScore, DimensionScore
    output, _, _ = scored(["supported", "not_found"], weights=ScoringWeights(skill=100, experience=0, education=0))
    data = output.model_dump()
    data["score"] = 100
    with pytest.raises(ValidationError):
        CandidateScore.model_validate(data)
    dimension = output.dimensions[0].model_dump()
    dimension["supported_count"] = 2
    with pytest.raises(ValidationError):
        DimensionScore.model_validate(dimension)
    data = output.model_dump()
    data["dimensions"] = [data["dimensions"][0]] * 3
    with pytest.raises(ValidationError):
        CandidateScore.model_validate(data)
